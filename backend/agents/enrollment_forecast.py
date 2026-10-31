"""Poisson-Gamma enrollment forecasting with uncertainty. Deterministic, stdlib only.

Each site's accrual rate gets a Gamma posterior (weak prior + observed
enrollments/months); Monte Carlo over the summed rate yields time-to-target
percentiles. Seeded RNG keeps every run reproducible.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional


def forecast(
    sites: List[Dict[str, Any]],
    target_enrollment: int,
    enrolled_so_far: int = 0,
    deadline_months: Optional[float] = None,
    simulations: int = 20000,
    seed: int = 42,
) -> Dict[str, Any]:
    """Forecast months to target with p10/p50/p90 credible bounds."""
    remaining = max(0, target_enrollment - enrolled_so_far)
    if remaining == 0 or not sites:
        out: Dict[str, Any] = {"p10": 0.0, "p50": 0.0, "p90": 0.0, "mean": 0.0,
                "simulations": simulations, "seed": seed}
        if deadline_months is not None:
            out["prob_by_deadline"] = 1.0
        return out
    rng = random.Random(seed)
    times: List[float] = []
    for _ in range(simulations):
        total = 0.0
        for s in sites:
            months = max(0.0, float(s.get("months_observed", 0) or 0))
            shape = 2.0 + float(s.get("accrual", 0) or 0) * months
            rate = 1.0 + months
            total += rng.gammavariate(max(shape, 0.01), max(rate, 0.01))
        times.append(remaining / total if total > 1e-9 else 9999.0)
    times.sort()
    pick = lambda p: times[min(len(times) - 1, int(p * len(times)))]
    out = {"p10": round(pick(0.1), 1), "p50": round(pick(0.5), 1),
           "p90": round(pick(0.9), 1),
           "mean": round(sum(times) / len(times), 1),
           "simulations": simulations, "seed": seed}
    if deadline_months is not None:
        out["prob_by_deadline"] = round(
            sum(1 for t in times if t <= deadline_months) / len(times), 3)
    return out
