"""M3.3.4 — Abstract rate limiter with Redis (primary) and in-memory fallback.

Rules:
- Provider selected by REDIS_URL env var.
- If REDIS_URL is set and reachable → Redis provider (compatible with Upstash / Redis Cloud).
- If REDIS_URL is absent AND APP_ENV in {development, test} → in-memory fallback allowed.
- In staging/production, if Redis is required-and-unavailable → provider MUST fail (fail-closed).

The service exposes:
- ``get_limiter()`` → returns a singleton RateLimiter.
- ``check(scope, key, limit, window)`` → returns (allowed, retry_after_seconds, current_count).
- ``incr(scope, key, window)`` → atomically increments counter and returns count.
- ``get(scope, key)`` → returns current count (for informational headers).
- ``set_lock(scope, key, ttl)`` / ``get_lock`` — used for cooldowns.
- ``is_ready(strict=True)`` → True when Redis is available (or when non-strict + dev).

Keys are always hashed identifiers (sha256[:16]); callers must NEVER pass raw tokens/emails.
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import time
from collections import defaultdict, deque
from typing import Optional, Tuple, Dict, Deque
from app.config import settings, is_dev_or_test, is_prod_like

logger = logging.getLogger("rate_limiter")

try:
    import redis.asyncio as aioredis  # redis>=5
except Exception:  # pragma: no cover
    aioredis = None  # type: ignore


# ------------------------- Key helpers -------------------------
def hkey(*parts: str) -> str:
    """Deterministic short hash of arbitrary identifier parts (never store raw)."""
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def rl_key(scope: str, ident_hash: str) -> str:
    return f"rl:{scope}:{ident_hash}"


def lock_key(scope: str, ident_hash: str) -> str:
    return f"lk:{scope}:{ident_hash}"


# ------------------------- Base provider -------------------------
class RateLimiterProvider:
    name: str = "abstract"
    ready: bool = False

    async def check_and_incr(self, scope: str, ident_hash: str, limit: int, window_sec: int) -> Tuple[bool, int, int]:
        """Return (allowed, retry_after_sec, current_count)."""
        raise NotImplementedError

    async def get_count(self, scope: str, ident_hash: str) -> int:
        raise NotImplementedError

    async def set_lock(self, scope: str, ident_hash: str, ttl_sec: int) -> bool:
        """Return True if lock acquired, False if already exists."""
        raise NotImplementedError

    async def get_lock_ttl(self, scope: str, ident_hash: str) -> int:
        """Return remaining TTL of the lock, 0 if not present."""
        raise NotImplementedError

    async def clear(self, scope: str, ident_hash: str) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        pass


# ------------------------- Redis provider -------------------------
class RedisRateLimiter(RateLimiterProvider):
    name = "redis"

    def __init__(self, url: str):
        if not aioredis:
            raise RuntimeError("redis library not installed")
        self._client = aioredis.from_url(url, encoding="utf-8", decode_responses=True,
                                          socket_connect_timeout=2.0, socket_timeout=2.0)
        self.ready = False

    async def _ping(self) -> bool:
        try:
            await self._client.ping()
            self.ready = True
            return True
        except Exception as e:
            logger.error(f"[rate_limiter] Redis PING failed: {e}")
            self.ready = False
            return False

    async def check_and_incr(self, scope: str, ident_hash: str, limit: int, window_sec: int) -> Tuple[bool, int, int]:
        k = rl_key(scope, ident_hash)
        try:
            pipe = self._client.pipeline()
            pipe.incr(k)
            pipe.expire(k, window_sec, nx=True)
            pipe.ttl(k)
            count, _, ttl = await pipe.execute()
            count = int(count)
            ttl = int(ttl) if ttl and ttl > 0 else window_sec
        except Exception as e:
            logger.error(f"[rate_limiter] Redis error on {k}: {e}")
            self.ready = False
            raise
        if count > limit:
            return (False, ttl, count)
        return (True, 0, count)

    async def get_count(self, scope: str, ident_hash: str) -> int:
        try:
            v = await self._client.get(rl_key(scope, ident_hash))
            return int(v) if v else 0
        except Exception:
            return 0

    async def set_lock(self, scope: str, ident_hash: str, ttl_sec: int) -> bool:
        try:
            ok = await self._client.set(lock_key(scope, ident_hash), "1", ex=ttl_sec, nx=True)
            return bool(ok)
        except Exception as e:
            logger.error(f"[rate_limiter] set_lock error: {e}")
            self.ready = False
            raise

    async def get_lock_ttl(self, scope: str, ident_hash: str) -> int:
        try:
            ttl = await self._client.ttl(lock_key(scope, ident_hash))
            return int(ttl) if ttl and ttl > 0 else 0
        except Exception:
            return 0

    async def clear(self, scope: str, ident_hash: str) -> None:
        try:
            await self._client.delete(rl_key(scope, ident_hash), lock_key(scope, ident_hash))
        except Exception:
            pass

    async def close(self) -> None:
        try:
            await self._client.aclose()  # type: ignore[attr-defined]
        except Exception:
            try:
                await self._client.close()
            except Exception:
                pass


# ------------------------- In-memory provider (dev/test only) -------------------------
class InMemoryRateLimiter(RateLimiterProvider):
    """SINGLE-PROCESS ONLY. NOT for production. Explicitly gated by APP_ENV."""
    name = "memory"

    def __init__(self):
        self._counts: Dict[str, Deque[float]] = defaultdict(deque)
        self._locks: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        self.ready = True

    async def check_and_incr(self, scope: str, ident_hash: str, limit: int, window_sec: int) -> Tuple[bool, int, int]:
        now = time.time()
        k = rl_key(scope, ident_hash)
        async with self._lock:
            q = self._counts[k]
            while q and (now - q[0]) > window_sec:
                q.popleft()
            if len(q) >= limit:
                retry = int(window_sec - (now - q[0])) + 1
                return (False, max(retry, 1), len(q))
            q.append(now)
            return (True, 0, len(q))

    async def get_count(self, scope: str, ident_hash: str) -> int:
        return len(self._counts.get(rl_key(scope, ident_hash), []))

    async def set_lock(self, scope: str, ident_hash: str, ttl_sec: int) -> bool:
        now = time.time()
        k = lock_key(scope, ident_hash)
        async with self._lock:
            existing = self._locks.get(k)
            if existing and existing > now:
                return False
            self._locks[k] = now + ttl_sec
            return True

    async def get_lock_ttl(self, scope: str, ident_hash: str) -> int:
        now = time.time()
        k = lock_key(scope, ident_hash)
        exp = self._locks.get(k)
        if not exp or exp <= now:
            return 0
        return int(exp - now)

    async def clear(self, scope: str, ident_hash: str) -> None:
        async with self._lock:
            self._counts.pop(rl_key(scope, ident_hash), None)
            self._locks.pop(lock_key(scope, ident_hash), None)


# ------------------------- Singleton bootstrap -------------------------
_instance: Optional[RateLimiterProvider] = None
_init_lock = asyncio.Lock()


async def get_limiter() -> RateLimiterProvider:
    """Return the singleton rate limiter. Initializes lazily.

    In prod-like envs, we do NOT silently fallback to in-memory. If Redis is
    unavailable, the provider remains `ready=False` and callers must fail-closed
    for sensitive scopes.
    """
    global _instance
    if _instance and _instance.ready:
        return _instance
    async with _init_lock:
        if _instance and _instance.ready:
            return _instance
        # Redis if URL configured
        if settings.REDIS_URL and aioredis is not None:
            try:
                r = RedisRateLimiter(settings.REDIS_URL)
                ok = await r._ping()
                if ok:
                    _instance = r
                    return _instance
                # Not ready — decide fallback
                if is_dev_or_test():
                    logger.warning("[rate_limiter] Redis configured but unreachable — falling back to in-memory (dev only)")
                    _instance = InMemoryRateLimiter()
                    return _instance
                # prod-like: keep the not-ready redis so is_ready(sensitive)=False
                _instance = r
                return _instance
            except Exception as e:
                logger.error(f"[rate_limiter] Redis init failed: {e}")
                if is_dev_or_test():
                    _instance = InMemoryRateLimiter()
                    return _instance
                # In prod, expose a not-ready dummy so sensitive scopes fail-closed
                dummy = RateLimiterProvider()
                dummy.ready = False
                _instance = dummy
                return dummy
        # No REDIS_URL: only allowed in dev/test
        if is_dev_or_test():
            _instance = InMemoryRateLimiter()
            return _instance
        # prod-like without REDIS_URL → fail-closed dummy
        dummy = RateLimiterProvider()
        dummy.ready = False
        _instance = dummy
        return dummy


async def limiter_ready_for_sensitive() -> bool:
    """True only when we can safely handle OTP/signature/etc.

    - In dev/test: always True (in-memory or redis).
    - In prod-like: only True if Redis is up (`.ready == True` and Redis provider).
    """
    limiter = await get_limiter()
    if is_dev_or_test():
        return True
    return isinstance(limiter, RedisRateLimiter) and limiter.ready


# ------------------------- High level helpers -------------------------
class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int, scope: str):
        super().__init__(f"rate_limited:{scope}")
        self.retry_after = retry_after
        self.scope = scope
