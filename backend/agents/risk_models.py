"""Calibrated trial-outlook model (HINT/TrialBench-anchored). Stdlib only.

Literature-calibrated logistic bootloader (v2): phase base rates enter as
log-odds, then fragility, burden, and organ-safety load discount them with
fully disclosed coefficients — the same probabilistic framing HINT uses,
minus the fitted network. The 4-way failure split follows TrialBench's
schema with published failure-share anchors (efficacy-heavy). The
documented upgrade is fitting the coefficients on TrialBench's public
approval-outcome task data.
"""

from __future__ import annotations

import math
import re
from typing import Any

PHASE_CUMULATIVE = {"1": 0.10, "2": 0.15, "3": 0.49}
SAFETY_CATEGORIES = ("Cardiac", "Hepatic", "Renal")

#: Disclosed log-odds coefficients (v2 bootloader).
B_FRAGILITY = -1.2
B_BURDEN = -0.8
B_SAFETY_EXCL = -0.15


def _logit(p: float) -> float:
    p = min(0.99, max(0.01, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def outlook(audit: dict[str, Any], burden: dict[str, Any]) -> dict[str, Any]:
    """Success probability + 4-way failure allocation with drivers."""
    phase = str((audit.get("protocol_metadata", {}) or {}).get("phase", ""))
    m = re.search(r"[123]", phase)
    base = PHASE_CUMULATIVE.get(m.group(0) if m else "", 0.15)
    frag = float(audit.get("protocol_fragility_index", 0) or 0)
    total_burden = float(burden.get("total_score", 0) or 0)
    n_safety = sum(
        1
        for c in audit.get("exclusion_criteria", [])
        if c.get("category") in SAFETY_CATEGORIES
    )
    logit = (
        _logit(base)
        + B_FRAGILITY * min(frag, 100.0) / 100.0
        + B_BURDEN * min(total_burden, 60.0) / 60.0
        + B_SAFETY_EXCL * n_safety
    )
    p = max(0.01, min(0.95, _sigmoid(logit)))
    w_enroll = 0.6 * (1.0 + frag / 100.0 + total_burden / 60.0)
    w_safety = 0.3 + 0.25 * n_safety
    w_eff = 1.1
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
            f"fragility {frag} -> {B_FRAGILITY * min(frag, 100.0) / 100.0:+.2f} log-odds",
            f"burden {total_burden:.0f} -> {B_BURDEN * min(total_burden, 60.0) / 60.0:+.2f} log-odds",
            f"{n_safety} organ-safety exclusions shape the safety share",
        ],
        "basis": (
            "Calibrated bootloader v2: literature phase rates as log-odds "
            "priors, disclosed fragility/burden/safety coefficients, "
            "TrialBench 4-way schema. Fit coefficients on TrialBench "
            "approval-outcome data to graduate to a fitted model."
        ),
    }
