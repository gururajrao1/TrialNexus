"""Reverse matching: rank protocols for one patient. Deterministic, stdlib only.

The patient-facing dual of cohort matching: given a single FHIR bundle,
score every available protocol and rank trials eligible-first. Reuses the
same evaluator, so site and patient views can never disagree.
"""

from __future__ import annotations

from typing import Any, Dict, List

from backend.agents.cohort_matcher import evaluate_patient, patient_id


def _top_reasons(ev: Dict[str, Any], limit: int = 2) -> List[str]:
    out: List[str] = []
    for e in ev.get("inclusion_evaluations", []):
        if not e["passed"] and len(out) < limit:
            tag = "missing data" if e["missing_data"] else "not met"
            out.append(f"{e['criterion_id']} {tag}: {e['clinical_evidence_found'][:90]}")
    for e in ev.get("exclusion_evaluations", []):
        if (e["triggered"] or e["missing_data"]) and len(out) < limit:
            tag = "needs review" if e["missing_data"] else "triggered"
            out.append(f"{e['criterion_id']} {tag}: {e['clinical_evidence_found'][:90]}")
    return out or ["Meets all evaluated criteria"]


def rank_trials(
    bundle: Dict[str, Any], protocols: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Rank protocols for one patient bundle (stable: protocol order breaks ties)."""
    order = {"ELIGIBLE": 0, "REVIEW_REQUIRED": 1, "INELIGIBLE": 2}
    ranked = []
    for p in protocols:
        ev = evaluate_patient(
            {"inclusion_criteria": p["criteria"].get("inclusion_criteria", []),
             "exclusion_criteria": p["criteria"].get("exclusion_criteria", [])},
            bundle)
        ranked.append({"protocol_id": p["id"], "title": p["title"], "phase": p["phase"],
                       "status": ev["overall_status"],
                       "match_percentage": ev["match_percentage"],
                       "top_reasons": _top_reasons(ev)})
    ranked.sort(key=lambda r: (order[r["status"]], -r["match_percentage"]))
    return {"patient_id": patient_id(bundle), "ranked": ranked}
