"""SPF / DKIM / DMARC checker via DNS TXT lookups.

Read-only. Never blocks. Provides a diagnostic view for the Impostazioni email UI.
"""
from __future__ import annotations
import asyncio
from typing import List, Dict, Any

import dns.resolver
import dns.exception


DEFAULT_DKIM_SELECTORS = ["default", "google", "selector1", "selector2", "siteground", "sg"]


def _lookup_txt(name: str, timeout: float = 5.0) -> List[str]:
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answers = resolver.resolve(name, "TXT")
        return ["".join([b.decode("utf-8", "replace") if isinstance(b, bytes) else str(b) for b in r.strings])
                for r in answers]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN,
            dns.exception.Timeout, dns.resolver.NoNameservers):
        return []
    except Exception:  # noqa: BLE001
        return []


async def check_domain(domain: str, dkim_selectors: List[str] | None = None) -> Dict[str, Any]:
    dkim_selectors = dkim_selectors or DEFAULT_DKIM_SELECTORS
    loop = asyncio.get_event_loop()

    spf_records = await loop.run_in_executor(None, _lookup_txt, domain)
    spf_hits = [r for r in spf_records if r.lower().startswith("v=spf1")]
    dmarc_records = await loop.run_in_executor(None, _lookup_txt, f"_dmarc.{domain}")
    dmarc_hits = [r for r in dmarc_records if r.lower().startswith("v=dmarc1")]

    dkim_results = []
    for sel in dkim_selectors:
        txt = await loop.run_in_executor(None, _lookup_txt, f"{sel}._domainkey.{domain}")
        hit = next((r for r in txt if "v=dkim1" in r.lower() or "p=" in r.lower()), None)
        dkim_results.append({"selector": sel, "found": bool(hit), "value": hit[:200] if hit else None})
    any_dkim = any(d["found"] for d in dkim_results)

    return {
        "domain": domain,
        "spf": {
            "found": bool(spf_hits),
            "value": (spf_hits[0][:400] if spf_hits else None),
            "all_records": spf_records[:5],
            "status_message": "OK" if spf_hits else "Nessun record SPF v=spf1 trovato",
        },
        "dkim": {
            "found": any_dkim,
            "checked_selectors": dkim_selectors,
            "results": dkim_results,
            "status_message": "OK" if any_dkim else "Nessun record DKIM trovato con i selettori standard",
        },
        "dmarc": {
            "found": bool(dmarc_hits),
            "value": (dmarc_hits[0][:400] if dmarc_hits else None),
            "status_message": "OK" if dmarc_hits else "Nessun record DMARC v=DMARC1 trovato",
        },
    }
