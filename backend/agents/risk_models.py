"""Transparent trial-outlook heuristics (HINT/TrialBench-inspired). Stdlib only.

Two readouts from audit + burden features:
- success_probability: P(eventual approval | current phase), calibrated to
  literature phase-transition rates, discounted by fragility and burden.
- failure_breakdown: TrialBench's 4-way schema (success, enrollment,
  safety, efficacy failure) with hand-set, fully disclosed weights.
A bootloader, not a fitted model: the documented upgrade path is fitting
on HINT's public data (futianfan/clinicaltrialoutcomeprediction).
"""

from __future__ import annotations

import re
from typing import Any

PHASE_CUMULATIVE = {"1": 0.10, "2": 0.15, "3": 0.49}
SAFETY_CATEGORIES = ("Cardiac", "Hepatic", "Renal")


def outlook(audit: dict[str, Any], burden: dict[str, Any]) -> dict[str, Any]:
    """Success probability + 4-way failure allocation with drivers."""
    phase = str((audit.get("protocol_metadata", {}) or {}).get("phase", ""))
    m = re.search(r"[123]", phase)
    base = PHASE_CUMULATIVE.get(m.group(0) if m else "", 0.15)
    frag = float(audit.get("protocol_fragility_index", 0) or 0)
    total_burden = float(burden.get("total_score", 0) or 0)
    frag_disc = 1.0 - min(frag, 100.0) / 100.0 * 0.5
    burden_disc = 1.0 - min(total_burden, 60.0) / 100.0 * 0.3
    p = max(0.01, min(0.95, base * frag_disc * burden_disc))
    n_safety = sum(
        1
        for c in audit.get("exclusion_criteria", [])
        if c.get("category") in SAFETY_CATEGORIES
    )
    w_enroll = frag / 100.0 + total_burden / 60.0 + 0.2
    w_safety = 0.3 + 0.25 * n_safety
    w_eff = 0.6
    w_sum = w_enroll + w_safety + w_eff
    fail = 1.0 - p
    return {
        "success_probability": round(p, 3),
        "failure_breakdown": {
            "success": round(p, 3),
            "enrollment_failure": round(fail * w_enroll / w_sum, 3),
            "safety_failure": round(fail * w_safety / w_sum, 3),
            "efficacy_failure": round(fail * w_eff / w_sum, 3),
        },
        "drivers": [
            f"Phase base rate {base:.0%} (literature cumulative-to-approval)",
            f"fragility discount x{frag_disc:.2f} (index {frag})",
            f"burden discount x{burden_disc:.2f} (score {total_burden})",
            f"{n_safety} organ-safety exclusions shape the safety share",
        ],
        "basis": (
            "Heuristic bootloader: phase base rates x fragility/burden "
            "discounts; 4-way schema follows TrialBench. Fit on HINT "
            "public data to graduate from heuristic to model."
        ),
    }
