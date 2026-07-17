#!/usr/bin/env python3
"""Pre-commit secret scanner for Infissi Express Cloud.

Blocks accidental commit of:
- password / secret / token / api_key literals ("...")
- Bearer tokens starting with sk-, eyJ (JWT), ghp_/gho_/ghu_ (GitHub), etc.
- The literal `Admin!YYYY` weak-seed pattern used historically
- AWS access keys, private RSA/DSA/EC keys, .pem material

Design decisions:
- Runs only on files staged for commit (unless invoked with --all)
- Skips vendor directories, virtualenvs, lockfiles and .env files themselves
  (those live outside version control by policy)
- Prints ONLY the file:line + a short redacted excerpt — never the raw secret
- Non-zero exit blocks the commit; explicit override with SECRETS_SCAN_SKIP=1
  is logged loudly.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[1]

# --- Directories / files excluded from scanning ----------------------
EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".cache", "coverage", ".pytest_cache",
    "yarn.lock", "package-lock.json",
}
EXCLUDE_SUFFIXES = {
    ".lock", ".map", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".gif",
    ".pdf", ".zip", ".tar", ".gz", ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".wav", ".webm",
}
# Env files are managed out-of-band and MUST live only on the pod / CI secrets.
EXCLUDE_BASENAMES = {".env", ".env.local", ".env.production", ".env.test"}
# Files that are legit examples/templates and must never contain real secrets
# (but may reference the *names* of env variables). Handled specially.
TEMPLATE_FILES = {".env.example", ".env.sample", "env.example", "README.md"}
# Documentation folders / helper scripts that intentionally reference legacy
# seed credentials for onboarding. We scan them BUT keep the allowlist below.
DOC_ALLOWLIST = {"memory/test_credentials.md"}


# --- Regex patterns --------------------------------------------------
# Each entry: (label, compiled regex, description)
def _rx(pat: str, flags: int = 0) -> "re.Pattern[str]":
    return re.compile(pat, flags)


PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    # Weak seed passwords like "Admin!2025" / "Tenant#Admin!2026Ok" / "Platform#Owner_2026!"
    ("weak-seed-password",
     _rx(r"['\"](?:Admin|Tenant|Platform|Super|Owner|Root)[!#_@][A-Za-z0-9!#_@$%\-]{4,}['\"]")),
    # password = "..." / password: "..."  (min 6 chars, ignoring dict-key `password: null`)
    ("password-literal",
     _rx(r"""(?i)\b(password|passwd|pwd|pass)\s*[:=]\s*['"](?!\{|\$\{|<|\.\.\.|None|null|true|false|test|xxx|\*+)[^'"]{6,}['"]""")),
    # secret / api_key / token / access_key = "..."   (excluding env lookups)
    ("secret-literal",
     _rx(r"""(?i)\b(secret|api[_-]?key|access[_-]?key|private[_-]?key|token)\s*[:=]\s*['"](?!\{|\$\{|<|\.\.\.|None|null|true|false|test|xxx|\*+)[A-Za-z0-9_\-]{12,}['"]""")),
    # Explicit AWS / GH / OpenAI / Stripe tokens
    ("aws-access-key", _rx(r"\bAKIA[0-9A-Z]{16}\b")),
    ("stripe-live-key", _rx(r"\bsk_live_[A-Za-z0-9]{20,}\b")),
    ("openai-key", _rx(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("gh-token", _rx(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("jwt", _rx(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("private-key-header",
     _rx(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----")),
    # Bearer tokens hardcoded in curl / requests
    ("bearer-hardcoded",
     _rx(r"""(?i)Authorization\s*[:=]\s*['"]Bearer\s+[A-Za-z0-9_\-\.]{20,}['"]""")),
]

# Per-file allowlist for individual matches that are known false positives.
# Keys are project-relative paths. Values are regexes of lines to allow.
FILE_LEVEL_ALLOWLIST: dict[str, List["re.Pattern[str]"]] = {
    "memory/test_credentials.md": [
        _rx(r"Admin!2025"),  # documented seed used only by internal dev tenant
    ],
    "backend/scripts/provision_owner.py": [],  # scanned normally
}


# --- Helpers ---------------------------------------------------------
def _staged_files() -> List[Path]:
    """Return files staged for commit that are text-like."""
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    files: List[Path] = []
    for line in out.stdout.splitlines():
        p = ROOT / line.strip()
        if p.is_file():
            files.append(p)
    return files


def _all_repo_files() -> List[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return [ROOT / ln for ln in out.stdout.splitlines() if (ROOT / ln).is_file()]


def _should_skip(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        # Path lives outside the repository root — nothing to skip against
        # (allow scanner to inspect the raw file, useful for ad-hoc runs).
        return False
    parts = set(rel.parts)
    if parts & EXCLUDE_DIRS:
        return True
    if rel.name in EXCLUDE_BASENAMES:
        return True
    if rel.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    # This scanner itself defines patterns — allow them
    if rel == Path("scripts/scan_secrets.py"):
        return True
    return False


def _redact(match: str, keep: int = 4) -> str:
    if len(match) <= keep * 2:
        return "*" * len(match)
    return f"{match[:keep]}…{'*' * (len(match) - keep * 2)}…{match[-keep:]}"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError):
        return ""


def _line_allowlisted(rel_str: str, line: str) -> bool:
    for allowed in FILE_LEVEL_ALLOWLIST.get(rel_str, []):
        if allowed.search(line):
            return True
    return False


def scan_files(files: Iterable[Path]) -> List[Tuple[Path, int, str, str]]:
    findings: List[Tuple[Path, int, str, str]] = []
    for f in files:
        if _should_skip(f):
            continue
        text = _read_text(f)
        if not text:
            continue
        try:
            rel_str = str(f.relative_to(ROOT))
        except ValueError:
            rel_str = str(f)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _line_allowlisted(rel_str, line):
                continue
            for label, rx in PATTERNS:
                m = rx.search(line)
                if not m:
                    continue
                findings.append((f, lineno, label, _redact(m.group(0))))
                break  # one match per line is enough
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Block accidental secret commits.")
    parser.add_argument("--all", action="store_true",
                        help="Scan the whole repo (not just staged files).")
    parser.add_argument("paths", nargs="*",
                        help="Optional explicit files to scan (used by pre-commit).")
    args = parser.parse_args()

    if os.environ.get("SECRETS_SCAN_SKIP") == "1":
        print("[scan_secrets] SECRETS_SCAN_SKIP=1 — SCAN BYPASSED (do not use in CI).",
              file=sys.stderr)
        return 0

    if args.paths:
        files = [Path(p).resolve() for p in args.paths if Path(p).is_file()]
    elif args.all:
        files = _all_repo_files()
    else:
        try:
            files = _staged_files()
        except subprocess.CalledProcessError:
            print("[scan_secrets] Not a git repo — falling back to --all", file=sys.stderr)
            files = _all_repo_files()

    findings = scan_files(files)
    if not findings:
        return 0

    print("\n" + "=" * 72, file=sys.stderr)
    print("SECRET SCAN — commit BLOCKED", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    for path, lineno, label, redacted in findings:
        try:
            rel = path.relative_to(ROOT)
        except ValueError:
            rel = path
        print(f"  {rel}:{lineno}  [{label}]  {redacted}", file=sys.stderr)
    print("-" * 72, file=sys.stderr)
    print(
        f"{len(findings)} suspected secret(s) detected.\n"
        "Move the value to an environment variable and reference it via os.environ.\n"
        "For test files use `tests._creds` (backend/tests/_creds.py).\n"
        "If truly a false positive, add an entry to FILE_LEVEL_ALLOWLIST in this script.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
