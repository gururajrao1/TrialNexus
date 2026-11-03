"""Poisson-Gamma enrollment forecasting with uncertainty. Deterministic, stdlib only.

Each site's accrual rate gets a Gamma posterior (weak prior + observed
enrollments/months); Monte Carlo over the summed rate yields time-to-target
percentiles. Seeded RNG keeps every run reproducible.
"""

from __future__ import annotations

import random
from typing import Any


def forecast(
    sites: list[dict[str, Any]],
    target_enrollment: int,
    enrolled_so_far: int = 0,
    deadline_months: float | None = None,
    simulations: int = 20000,
    seed: int = 42,
) -> dict[str, Any]:
    """Forecast months to target with p10/p50/p90 credible bounds."""
    remaining = max(0, target_enrollment - enrolled_so_far)
    if remaining == 0 or not sites:
        out: dict[str, Any] = {
            "p10": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "mean": 0.0,
            "simulations": simulations,
            "seed": seed,
        }
        if deadline_months is not None:
            out["prob_by_deadline"] = 1.0
        return out
    rng = random.Random(seed)
    times: list[float] = []
    for _ in range(simulations):
        total = 0.0
        for s in sites:
            months = max(0.0, float(s.get("months_observed", 0) or 0))
            shape = 2.0 + float(s.get("accrual", 0) or 0) * months
            rate = 1.0 + months
            total += rng.gammavariate(max(shape, 0.01), max(rate, 0.01))
        times.append(remaining / total if total > 1e-9 else 9999.0)
    times.sort()

    def pick(p: float) -> float:
        return times[min(len(times) - 1, int(p * len(times)))]

    out = {
        "p10": round(pick(0.1), 1),
        "p50": round(pick(0.5), 1),
        "p90": round(pick(0.9), 1),
        "mean": round(sum(times) / len(times), 1),
        "simulations": simulations,
        "seed": seed,
    }
    if deadline_months is not None:
        out["prob_by_deadline"] = round(
            sum(1 for t in times if t <= deadline_months) / len(times), 3
        )
    return out


def _posterior_mean(enrolled: list[float]) -> float:
    """Posterior-mean monthly rate under the Gamma(2, 1) prior."""
    n = len(enrolled)
    if n == 0:
        return 0.0
    return (2.0 + sum(enrolled)) / (1.0 + n)


def backtest_accrual(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Temporal validation of the Gamma-Poisson accrual model.

    Expanding-window hindcast: for each site, predict every month from
    the months before it using the same Gamma(2, 1) posterior the
    forecast uses, then score against what actually enrolled. No new
    data, no fitted weights — the model's own history grades it.
    """
    by_site: dict[str, list[float]] = {}
    order: dict[str, list[str]] = {}
    for r in rows:
        try:
            sid = str(r["site_id"])
            by_site.setdefault(sid, []).append(float(r.get("enrolled", 0) or 0))
            order.setdefault(sid, []).append(str(r.get("month", "")))
        except (KeyError, TypeError, ValueError):
            continue
    sites = []
    errors: list[float] = []
    for sid in sorted(by_site):
        vals = by_site[sid]
        months = order[sid]
        preds = []
        for k in range(1, len(vals)):
            pred = _posterior_mean(vals[:k])
            err = abs(pred - vals[k])
            errors.append(err)
            preds.append(
                {
                    "month": months[k],
                    "predicted": round(pred, 2),
                    "actual": vals[k],
                    "abs_err": round(err, 2),
                }
            )
        if preds:
            sites.append({"site_id": sid, "predictions": preds})
    mae = sum(errors) / len(errors) if errors else 0.0
    return {
        "n_sites": len(sites),
        "n_predictions": len(errors),
        "mae": round(mae, 2),
        "sites": sites,
        "basis": (
            "Expanding-window hindcast: each month predicted from prior "
            "months under the same Gamma(2, 1) posterior as the forecast; "
            "MAE in patients/month."
        ),
    }


def site_priors_from_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Empirical-Bayes inputs: per-site accrual + months from observed metrics.

    Turns the site_metrics history into the observed half of each site's
    Gamma posterior, replacing assumed run-rates with measured ones.
    """
    by_site: dict[str, list[float]] = {}
    for r in rows:
        try:
            by_site.setdefault(str(r["site_id"]), []).append(float(r["enrolled"]))
        except (KeyError, TypeError, ValueError):
            continue
    return {
        sid: {
            "accrual": round(sum(vals) / len(vals), 3),
            "months_observed": float(len(vals)),
        }
        for sid, vals in by_site.items()
        if vals
    }
