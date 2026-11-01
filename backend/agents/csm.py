"""Centralized statistical monitoring (TransCelerate-style CSM). Stdlib only.

Cross-site outlier screens over pooled monthly metrics: robust z-scores
(median/MAD, SD fallback), exact Poisson tests for count KRIs (flags
both suspiciously high AND low counts — under-reported SAEs matter),
and funnel-plot 95%/99.8% control limits. Digit-preference analysis is
deliberately excluded: it needs row-level vitals/ECG feeds this app
does not ingest.
"""

from __future__ import annotations

import math
from typing import Any

Z_FLAG = 3.0
P_FLAG = 0.01


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def robust_z(x: float, peers: list[float]) -> float:
    """Robust z via median/MAD; SD fallback; 0 when no variation."""
    if len(peers) < 3:
        return 0.0
    med = _median(peers)
    mad = _median([abs(v - med) for v in peers]) * 1.4826
    if mad > 0:
        return (x - med) / mad
    mean = sum(peers) / len(peers)
    var = sum((v - mean) ** 2 for v in peers) / len(peers)
    return (x - mean) / math.sqrt(var) if var > 0 else 0.0


def poisson_sf(k: int, lam: float) -> float:
    """P(X >= k) for Poisson(lam); exact sum. Guard lam<=0."""
    if lam <= 0:
        return 0.0 if k > 0 else 1.0
    return 1.0 - sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(k))


def poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) for Poisson(lam); exact sum."""
    if lam <= 0:
        return 1.0
    return sum(math.exp(-lam) * lam**i / math.factorial(i) for i in range(k + 1))


def funnel_flags(rate: float, n: float, pooled: float) -> str:
    """'out99' / 'out95' / 'in' vs normal-approx control limits."""
    if n <= 0:
        return "in"
    se = math.sqrt(max(pooled, 1e-9) * (1 - min(pooled, 1 - 1e-9)) / n)
    if se == 0:
        return "in"
    dev = abs(rate - pooled)
    if dev > 3.09 * se:
        return "out99"
    if dev > 1.96 * se:
        return "out95"
    return "in"


def csm_screen(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Screen pooled site metrics. rows: site_id, enrolled, screened,
    open_queries, deviations, sae (monthly; aggregated per site)."""
    agg: dict[str, dict[str, float]] = {}
    for r in rows:
        a = agg.setdefault(
            str(r.get("site_id", "?")),
            {"enrolled": 0, "screened": 0, "queries": 0, "dev": 0, "sae": 0},
        )
        a["enrolled"] += float(r.get("enrolled", 0) or 0)
        a["screened"] += float(r.get("screened", 0) or 0)
        a["queries"] += float(r.get("open_queries", 0) or 0)
        a["dev"] += float(r.get("deviations", 0) or 0)
        a["sae"] += float(r.get("sae", 0) or 0)
    tot_e = sum(a["enrolled"] for a in agg.values()) or 1.0
    tot_s = sum(a["screened"] for a in agg.values()) or 1.0
    pool = {
        "screen_fail": 1.0 - tot_e / tot_s,
        "query": sum(a["queries"] for a in agg.values()) / tot_e,
        "dev": sum(a["dev"] for a in agg.values()) / tot_e,
        "sae": sum(a["sae"] for a in agg.values()) / tot_e,
    }

    def rates(key: str) -> dict[str, float]:
        out = {}
        for sid, a in agg.items():
            if key == "screen_fail":
                out[sid] = 1.0 - a["enrolled"] / a["screened"] if a["screened"] else 0.0
            else:
                base = {"query": "queries", "dev": "dev", "sae": "sae"}[key]
                out[sid] = a[base] / a["enrolled"] if a["enrolled"] else 0.0
        return out

    sites = []
    for sid, a in sorted(agg.items()):
        signals = []
        for key in ("screen_fail", "query", "dev", "sae"):
            peer = list(rates(key).values())
            rate = rates(key)[sid]
            z = robust_z(rate, peer)
            if key == "screen_fail":
                n, lam = a["screened"], pool[key] * a["screened"]
                count = a["screened"] - a["enrolled"]
            else:
                base = {"query": "queries", "dev": "dev", "sae": "sae"}[key]
                n, lam, count = a["enrolled"], pool[key] * a["enrolled"], a[base]
            p_high = poisson_sf(int(count), lam)
            p_low = poisson_cdf(int(count), lam)
            funnel = funnel_flags(rate, n, pool[key])
            flag = abs(z) >= Z_FLAG or min(p_high, p_low) < P_FLAG or funnel == "out99"
            if not flag:
                direction = "-"
            elif rate > pool[key]:
                direction = "high"
            elif rate < pool[key]:
                direction = "low"
            else:
                direction = "high" if z >= 0 else "low"
            signals.append(
                {
                    "kri": key,
                    "rate": round(rate, 3),
                    "pooled": round(pool[key], 3),
                    "z": round(z, 2),
                    "p_high": round(p_high, 4),
                    "p_low": round(p_low, 4),
                    "funnel": funnel,
                    "direction": direction,
                    "flag": flag,
                }
            )
        sites.append(
            {
                "site_id": sid,
                "n_flagged": sum(1 for s in signals if s["flag"]),
                "signals": signals,
            }
        )
    sites.sort(key=lambda s: -s["n_flagged"])
    return {
        "sites": sites,
        "n_sites": len(agg),
        "basis": (
            "Robust z (|z|>=3), exact Poisson (p<0.01, high and low), "
            "funnel 99.8% limits. Digit preference needs row-level vitals "
            "and is out of scope for metric feeds."
        ),
    }
