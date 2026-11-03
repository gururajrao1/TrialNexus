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

import json
import math
import re
from pathlib import Path
from typing import Any

from backend.config import FITTED_OUTLOOK

PHASE_CUMULATIVE = {"1": 0.10, "2": 0.15, "3": 0.49}
SAFETY_CATEGORIES = ("Cardiac", "Hepatic", "Renal")

#: Disclosed log-odds coefficients (v2 bootloader).
B_FRAGILITY = -1.2
B_BURDEN = -0.8
B_SAFETY_EXCL = -0.15


def fitted_coefficients(
    path: Path | str = FITTED_OUTLOOK,
) -> dict[str, Any] | None:
    """Load user-fitted LR coefficients. Fail-closed: None on any problem.

    The file is written by scripts/fit_outlook.py after the operator
    obtains gated tabular data; it is git-ignored and never ships.
    """
    try:
        doc = json.loads(Path(path).read_text())
        weights = doc["weights"]
        return {
            "fragility": float(weights["fragility"]),
            "burden": float(weights["burden"]),
            "safety_excl": float(weights["safety_excl"]),
            "bias": float(weights.get("bias", 0.0)),
            "source": str(doc.get("trained_on", "user-fitted")),
            "auc": doc.get("test_auc"),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None


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
    f_frag = min(frag, 100.0) / 100.0
    f_burden = min(total_burden, 60.0) / 60.0
    fitted = fitted_coefficients(FITTED_OUTLOOK)
    if fitted is not None:
        logit = (
            fitted["bias"]
            + fitted["fragility"] * f_frag
            + fitted["burden"] * f_burden
            + fitted["safety_excl"] * n_safety
        )
        coeff_note = (
            f"fitted coefficients ({fitted['source']}, test AUC {fitted['auc']})"
        )
    else:
        logit = (
            _logit(base)
            + B_FRAGILITY * f_frag
            + B_BURDEN * f_burden
            + B_SAFETY_EXCL * n_safety
        )
        coeff_note = "bootloader priors (no fitted file present)"
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
            coeff_note,
        ],
        "basis": (
            "Calibrated bootloader v2: literature phase rates as log-odds "
            "priors, disclosed fragility/burden/safety coefficients, "
            "TrialBench 4-way schema. Fitted coefficients load from "
            "data/fitted/outlook_lr.json when present (see "
            "scripts/fit_outlook.py); otherwise priors apply."
        ),
    }
