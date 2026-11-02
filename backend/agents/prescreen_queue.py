"""Prescreen workup queue: ranked daily list for coordinators.

Composes evaluate_cohort output with forensic failure weights: every
missing-data item scores 1 point plus its historical fail/missing rate,
so the queue chases the labs that unblock the most patients first.
REVIEW_REQUIRED rows lead; ELIGIBLE rows follow by ascending match;
INELIGIBLE rows appear only as near-misses (exactly one hard fail).
Deterministic, stdlib only.
"""

from __future__ import annotations

from typing import Any

from backend.agents.real_data import genes_in_text


def _missing_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for kind in ("inclusion_evaluations", "exclusion_evaluations"):
        for e in result.get(kind, []) or []:
            if e.get("missing_data"):
                out.append(
                    {
                        "criterion_id": str(e.get("criterion_id", "?")),
                        "evidence": str(e.get("clinical_evidence_found", "")),
                    }
                )
    return out


def _hard_fails(result: dict[str, Any]) -> list[str]:
    fails = [
        str(e.get("criterion_id", "?"))
        for e in result.get("inclusion_evaluations", []) or []
        if not e.get("passed") and not e.get("missing_data")
    ]
    fails += [
        str(e.get("criterion_id", "?"))
        for e in result.get("exclusion_evaluations", []) or []
        if e.get("triggered")
    ]
    return fails


def rank_prescreen(
    matching_results: list[dict[str, Any]],
    drivers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rank a coordinator worklist over cohort match results."""
    weight = {
        str(d.get("criterion_id", "?")): float(d.get("rate", 0) or 0) / 100.0
        for d in drivers or []
    }
    rows = []
    for r in matching_results:
        status = str(r.get("overall_status", ""))
        missing = _missing_items(r)
        fails = _hard_fails(r)
        near_miss = status == "INELIGIBLE" and len(fails) == 1
        if status not in ("REVIEW_REQUIRED", "ELIGIBLE") and not near_miss:
            continue
        score = sum(1.0 + weight.get(m["criterion_id"], 0.0) for m in missing)
        if near_miss:
            score = sum(1.0 + weight.get(c, 0.0) for c in fails)
        gene_text = " ".join(
            [m["criterion_id"] + " " + m["evidence"] for m in missing]
            + (r.get("physician_action_items", []) or [])
        )
        rows.append(
            {
                "patient_id": str(r.get("patient_id", "?")),
                "status": status,
                "match_percentage": r.get("match_percentage"),
                "missing_items": [
                    {**m, "weight": round(weight.get(m["criterion_id"], 0.0), 3)}
                    for m in missing
                ],
                "n_missing": len(missing),
                "hard_fails": fails,
                "near_miss": near_miss,
                "priority_score": round(score, 2),
                "genes": genes_in_text(gene_text),
                "action_items": r.get("physician_action_items", []) or [],
            }
        )
    rows.sort(
        key=lambda x: (
            0 if x["status"] == "REVIEW_REQUIRED" or x["near_miss"] else 1,
            -x["priority_score"],
            -(x.get("match_percentage") or 0) if x["status"] == "ELIGIBLE" else 0,
        )
    )
    return {
        "rows": rows,
        "summary": {
            "n_review": sum(1 for x in rows if x["status"] == "REVIEW_REQUIRED"),
            "n_eligible": sum(1 for x in rows if x["status"] == "ELIGIBLE"),
            "n_near_miss": sum(1 for x in rows if x["near_miss"]),
        },
        "basis": (
            "Missing-data items score 1 point plus their historical "
            "fail/missing rate, so the queue chases the labs that unblock "
            "the most patients first. Near-miss = one hard fail away."
        ),
    }
