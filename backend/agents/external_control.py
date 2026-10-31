"""External control cohort builder (illustrative). Deterministic, stdlib only.

Builds a comparator pool from real-world-like FHIR bundles by relaxing
explicitly listed criteria, then reports comparability (mix of pool vs
strictly matched cohort via the diversity planner) and a pre-specified
methods note suitable as documentation scaffolding. Relaxations are always
named — a silent pool is not a control arm.
"""

from __future__ import annotations

from typing import Any, Dict, List

try:
    from backend.agents.cohort_matcher import evaluate_patient, patient_id
    from backend.agents.diversity_planner import plan_diversity
except ImportError:  # fallback: run with backend/ as cwd
    from agents.cohort_matcher import evaluate_patient, patient_id  # type: ignore[no-redef]
    from agents.diversity_planner import plan_diversity  # type: ignore[no-redef]


def _hard_fails(ev: Dict[str, Any]) -> int:
    fails = sum(1 for e in ev.get("inclusion_evaluations", [])
                if not e["passed"] and not e["missing_data"])
    return fails + sum(1 for e in ev.get("exclusion_evaluations", []) if e["triggered"])


def build_external_control(
    criteria: Dict[str, Any], bundles: List[Dict[str, Any]], relax_ids: List[str]
) -> Dict[str, Any]:
    """Build pool + near-miss set under explicitly relaxed criteria."""
    relaxed = {
        "inclusion_criteria": [c for c in criteria.get("inclusion_criteria", [])
                               if c.get("id") not in relax_ids],
        "exclusion_criteria": [c for c in criteria.get("exclusion_criteria", [])
                               if c.get("id") not in relax_ids],
    }
    pool, near_miss, strict_ids = [], [], []
    for b in bundles:
        strict = evaluate_patient(criteria, b)
        if strict["overall_status"] == "ELIGIBLE":
            strict_ids.append(patient_id(b))
        relaxed_ev = evaluate_patient(relaxed, b)
        entry = {"patient_id": patient_id(b),
                 "strict_status": strict["overall_status"],
                 "relaxed_status": relaxed_ev["overall_status"],
                 "match_percentage": relaxed_ev["match_percentage"]}
        if relaxed_ev["overall_status"] == "ELIGIBLE":
            pool.append(entry)
        elif _hard_fails(relaxed_ev) <= 1:
            near_miss.append(entry)
    pool_bundles = [b for b in bundles
                    if patient_id(b) in {p["patient_id"] for p in pool}]
    strict_bundles = [b for b in bundles if patient_id(b) in set(strict_ids)]
    methods = (
        f"External control pool built by relaxing {len(relax_ids)} criteria "
        f"({', '.join(relax_ids) if relax_ids else 'none'}). Pool n={len(pool)}; "
        f"strict-match n={len(strict_ids)}; near-miss n={len(near_miss)} "
        "(<=1 hard fail under relaxed rules). Pre-specified caveats: relaxed "
        "criteria may introduce selection bias; real-world measurement timing "
        "differs from protocol windows; transportability to the trial population "
        "must be justified per endpoint before any regulatory use.")
    return {"relaxed_criteria": relax_ids, "pool": pool, "near_miss": near_miss,
            "comparability": {
                "pool_mix": plan_diversity(pool_bundles)["dimensions"] if pool_bundles else {},
                "strict_mix": plan_diversity(strict_bundles)["dimensions"] if strict_bundles else {},
            },
            "methods_note": methods}
