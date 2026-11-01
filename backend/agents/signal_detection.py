"""Pharmacovigilance signal detection: disproportionality statistics.

Implements the standard frequentist screeners over (suspect drug,
MedDRA preferred term) pairs: Proportional Reporting Ratio with
chi-squared (Evans et al. 2001 signal criteria: n >= 3, PRR >= 2,
chi2 >= 4) and Reporting Odds Ratio with 95% CI (signal when the
lower CI exceeds 1). A 0.5 continuity correction handles zero cells.

Small-trial honesty: with few records the engine reports WATCH /
INSUFFICIENT-COMPARATOR instead of manufacturing signals. Deterministic,
stdlib only.
"""

from __future__ import annotations

import math
from typing import Any

MIN_N = 3
MIN_PRR = 2.0
MIN_CHI2 = 4.0


def contingency(
    pairs: list[tuple[str, str]], drug: str, event: str
) -> tuple[float, float, float, float]:
    """2x2 counts (a, b, c, d) with 0.5 correction on any zero cell."""
    a = sum(1 for d, e in pairs if d == drug and e == event)
    b = sum(1 for d, e in pairs if d == drug and e != event)
    c = sum(1 for d, e in pairs if d != drug and e == event)
    d = sum(1 for d, e in pairs if d != drug and e != event)
    if min(a, b, c, d) == 0:
        a, b, c, d = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    return float(a), float(b), float(c), float(d)


def prr_chi2(a: float, b: float, c: float, d: float) -> tuple[float, float]:
    """Proportional reporting ratio + uncorrected chi-squared."""
    prr = (a / (a + b)) / (c / (c + d))
    n = a + b + c + d
    chi2 = n * (a * d - b * c) ** 2 / ((a + b) * (c + d) * (a + c) * (b + d))
    return prr, chi2


def ror_ci(a: float, b: float, c: float, d: float) -> tuple[float, float, float]:
    """Reporting odds ratio + Wald 95% confidence interval."""
    ror = (a / b) / (c / d)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    low = math.exp(math.log(ror) - 1.96 * se)
    high = math.exp(math.log(ror) + 1.96 * se)
    return ror, low, high


def detect_signals(triaged: list[dict[str, Any]]) -> dict[str, Any]:
    """Screen every (drug, preferred term) pair. Never raises on shape."""
    pairs = [
        (
            str(t.get("suspect_drug", "unknown") or "unknown"),
            str((t.get("meddra_classification", {}) or {}).get("preferred_term", "?")),
            str((t.get("meddra_classification", {}) or {}).get("soc", "?")),
        )
        for t in triaged
    ]
    drugs = sorted({d for d, _, _ in pairs if d != "unknown"})
    events = sorted({(e, s) for _, e, s in pairs})
    rows = []
    flat = [(x, y) for x, y, _ in pairs]
    for drug in drugs:
        for event, soc in events:
            n = sum(1 for x, y in flat if x == drug and y == event)
            a, b, c, d = contingency(flat, drug, event)
            prr, chi2 = prr_chi2(a, b, c, d)
            ror, low, high = ror_ci(a, b, c, d)
            evans = n >= MIN_N and prr >= MIN_PRR and chi2 >= MIN_CHI2
            ror_hit = low > 1.0
            if len(drugs) < 2:
                status = "insufficient-comparator"
            elif evans and ror_hit:
                status = "signal"
            elif prr >= MIN_PRR or chi2 >= MIN_CHI2:
                status = "watch"
            else:
                status = "monitored"
            rows.append(
                {
                    "drug": drug,
                    "event": event,
                    "soc": soc,
                    "n": n,
                    "prr": round(prr, 2),
                    "chi2": round(chi2, 2),
                    "ror": round(ror, 2),
                    "ror_ci": [round(low, 2), round(high, 2)],
                    "status": status,
                }
            )
    rows.sort(key=lambda r: (-r["prr"], r["drug"], r["event"]))
    return {
        "pairs": rows,
        "signals": [r for r in rows if r["status"] == "signal"],
        "watch": [r for r in rows if r["status"] == "watch"],
        "n_records": len(triaged),
        "n_drugs": len(drugs),
        "basis": (
            "Evans et al. 2001 (n>=3, PRR>=2, chi2>=4) plus ROR 95% CI "
            "lower>1; 0.5 continuity correction on zero cells. Needs >=2 "
            "distinct suspect drugs for a comparator; otherwise pairs report "
            "insufficient-comparator."
        ),
    }
