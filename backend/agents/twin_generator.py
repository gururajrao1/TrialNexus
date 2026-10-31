"""Seeded synthetic twin generator for eligibility stress-testing. Stdlib only.

Jitters numeric FHIR observations ±15% with a seeded RNG to explore how
sensitive eligibility is to measurement variation. Design exploration only:
twins are not evidence of efficacy or safety.
"""

from __future__ import annotations

import copy
import random
from typing import Any, Dict, List

try:
    from backend.agents.cohort_matcher import evaluate_patient
except ImportError:  # fallback: run with backend/ as cwd
    from agents.cohort_matcher import evaluate_patient  # type: ignore[no-redef]


def make_twins(bundle: Dict[str, Any], n: int, seed: int = 7,
               jitter: float = 0.15) -> List[Dict[str, Any]]:
    """Clone a bundle n times with jittered numeric observations."""
    rng = random.Random(seed)
    twins = []
    for i in range(max(0, min(n, 500))):
        t = copy.deepcopy(bundle)
        for e in t.get("entry", []):
            r = e.get("resource", {}) if isinstance(e, dict) else {}
            if r.get("resourceType") != "Observation":
                continue
            vq = r.get("valueQuantity")
            if isinstance(vq, dict) and isinstance(vq.get("value"), (int, float)):
                vq["value"] = round(vq["value"] * (1 + rng.uniform(-jitter, jitter)), 1)
        base = str(bundle.get("id") or "twin")
        t["id"] = f"{base}-twin-{i + 1}"
        for e in t.get("entry", []):
            r = e.get("resource", {}) if isinstance(e, dict) else {}
            if r.get("resourceType") == "Patient":
                r["id"] = t["id"]
        twins.append(t)
    return twins


def twin_distribution(criteria: Dict[str, Any], bundle: Dict[str, Any],
                      n: int = 100, seed: int = 7) -> Dict[str, Any]:
    """Eligibility distribution of n twins against structured criteria."""
    counts = {"ELIGIBLE": 0, "INELIGIBLE": 0, "REVIEW_REQUIRED": 0}
    for t in make_twins(bundle, n, seed):
        ev = evaluate_patient(criteria, t)
        counts[ev["overall_status"]] = counts.get(ev["overall_status"], 0) + 1
    total = max(1, sum(counts.values()))
    return {"n": total, "seed": seed, "counts": counts,
            "eligible_pct": round(100.0 * counts["ELIGIBLE"] / total, 1),
            "note": ("Design exploration only: twins probe measurement "
                     "sensitivity, never efficacy or safety.")}
