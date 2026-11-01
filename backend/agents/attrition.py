"""Trial-level attrition (dropout) predictor. Deterministic, stdlib only.

Literature-calibrated points model in the retention-toolkit / CT.gov
attrition-model spirit: baseline dropout ~18% (retention-toolkit mean
18.82%), trial demands (visits x burden, the duration proxy — duration
is the strongest published predictor) push it up, observed SAEs push it
up, and remote-capable visits (DCT) pull it down. Transparent points,
no fitted weights smuggled in: the documented upgrade is fitting the
coefficients on TrialBench's dropout-rate task data.
"""

from __future__ import annotations

from typing import Any

BASE_PCT = 18.0


def predict_attrition(
    burden: dict[str, Any],
    dct: dict[str, Any] | None = None,
    sae_count: int = 0,
) -> dict[str, Any]:
    """Expected dropout % with drivers and a heuristic interval."""
    visits = burden.get("visits", []) or []
    n_visits = len(visits)
    total = float(burden.get("total_score", 0) or 0)
    demands_pts = max(0, n_visits - 3) * 1.5 + total * 0.2
    safety_pts = max(0, int(sae_count)) * 2.0
    remote_n = int((dct or {}).get("remote_capable_n", 0) or 0)
    dct_relief = min(6.0, remote_n * 1.0)
    pct = min(60.0, max(5.0, BASE_PCT + demands_pts + safety_pts - dct_relief))
    drivers = [
        f"base {BASE_PCT:.0f}% (retention-toolkit CT.gov mean 18.82%)",
        f"trial demands +{demands_pts:.1f}pp ({n_visits} visits, burden {total:.0f})",
        f"safety load +{safety_pts:.1f}pp ({sae_count} SAEs)",
        f"DCT relief -{dct_relief:.1f}pp ({remote_n} remote-capable visits)",
    ]
    return {
        "dropout_pct": round(pct, 1),
        "interval_pct": [round(max(2.0, pct - 5), 1), round(min(70.0, pct + 5), 1)],
        "drivers": drivers,
        "basis": (
            "Bootloader points model: duration-proxy demands dominate "
            "(strongest published predictor), SAEs add, DCT subtracts. "
            "Fit coefficients on TrialBench dropout data to graduate."
        ),
    }
