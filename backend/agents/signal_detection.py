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
BH_MIN_PAIRS = 10
SHRINK_PRIOR = 0.5


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


def chi2_p(chi2: float) -> float:
    """Upper-tail p-value of a 1-df chi-squared statistic. Guards domain."""
    if chi2 <= 0:
        return 1.0
    return max(0.0, min(1.0, math.erfc(math.sqrt(chi2 / 2.0))))


def bh_adjust(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR q-values (monotone, capped at 1)."""
    m = len(p_values)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: p_values[i])
    qs = [0.0] * m
    running = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        k = m - rank + 1
        running = min(running, m / k * p_values[i])
        qs[i] = min(1.0, running)
    return qs


def ic_shrunk(a: float, b: float, c: float, d: float) -> float:
    """Fixed-prior information component (BCPNN-style, log2).

    Same corrected table throughout: expected count from corrected
    margins, then a fixed +0.5 pseudo-count on cell and expectation.
    Documented and fixed — no fitting, so it damps small-n PRR
    explosions without pretending to be a fitted MGPS model.
    """
    n = a + b + c + d
    if n <= 0:
        return 0.0
    exp_count = (a + b) * (a + c) / n
    return math.log2((a + SHRINK_PRIOR) / (exp_count + SHRINK_PRIOR))


def detect_signals(triaged: list[dict[str, Any]]) -> dict[str, Any]:
    """Screen every (drug, preferred term) pair. Never raises on shape.

    Comparator key is the RxNorm concept ID when the route layer attached
    one, so spelling variants of one drug screen as one drug; the raw
    spelling is preserved as drug_label.
    """
    pairs = [
        (
            str(t.get("rxcui") or t.get("suspect_drug", "unknown") or "unknown"),
            str((t.get("meddra_classification", {}) or {}).get("preferred_term", "?")),
            str((t.get("meddra_classification", {}) or {}).get("soc", "?")),
            str(t.get("suspect_drug", "unknown") or "unknown"),
        )
        for t in triaged
    ]
    drugs = sorted({d for d, _, _, _ in pairs if d != "unknown"})
    events = sorted({(e, s) for _, e, s, _ in pairs})
    labels = {}
    for d, _, _, lab in pairs:
        labels.setdefault(d, lab)
    rows = []
    flat = [(x, y) for x, y, _, _ in pairs]
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
                    "drug_label": labels.get(drug, drug),
                    "event": event,
                    "soc": soc,
                    "n": n,
                    "prr": round(prr, 2),
                    "chi2": round(chi2, 2),
                    "p_value": round(chi2_p(chi2), 4),
                    "q_value": None,
                    "ic": round(ic_shrunk(a, b, c, d), 2),
                    "ror": round(ror, 2),
                    "ror_ci": [round(low, 2), round(high, 2)],
                    "status": status,
                }
            )
    if len(drugs) >= 2 and len(rows) >= BH_MIN_PAIRS:
        qs = bh_adjust([r["p_value"] for r in rows])
        for r, q in zip(rows, qs):
            r["q_value"] = round(q, 4)
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
            "insufficient-comparator. BH-FDR q-values screen multiplicity on "
            ">=10 pairs (screening only, not confirmatory); fixed-prior IC "
            "damps small-n PRR without fitting."
        ),
    }
