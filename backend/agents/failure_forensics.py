"""Screen-failure forensics over persisted match evaluations.

Aggregates which criteria fail, go missing, or trigger across every
stored cohort run: the evidence base for "why are we screen-failing?"
Deterministic, stdlib only. Input rows are stored evaluation rationales
(full per-patient match results).
"""

from __future__ import annotations

from typing import Any


def forensic_report(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(evaluations)
    inc: dict[str, dict[str, int]] = {}
    exc: dict[str, dict[str, int]] = {}
    for r in evaluations:
        for e in r.get("inclusion_evaluations", []):
            s = inc.setdefault(e["criterion_id"], {"n": 0, "failed": 0, "missing": 0})
            s["n"] += 1
            if not e["passed"]:
                s["failed"] += 1
            if e["missing_data"]:
                s["missing"] += 1
        for e in r.get("exclusion_evaluations", []):
            s = exc.setdefault(e["criterion_id"], {"n": 0, "triggered": 0})
            s["n"] += 1
            if e["triggered"]:
                s["triggered"] += 1

    def _rate(part: int, whole: int) -> float:
        return round(100.0 * part / whole, 1) if whole else 0.0

    inclusions = [
        {
            "criterion_id": cid,
            "n": s["n"],
            "fail_n": s["failed"],
            "fail_rate": _rate(s["failed"], s["n"]),
            "missing_n": s["missing"],
            "missing_rate": _rate(s["missing"], s["n"]),
        }
        for cid, s in sorted(inc.items())
    ]
    exclusions = [
        {
            "criterion_id": cid,
            "n": s["n"],
            "trigger_n": s["triggered"],
            "trigger_rate": _rate(s["triggered"], s["n"]),
        }
        for cid, s in sorted(exc.items())
    ]
    drivers = sorted(
        [
            {
                "criterion_id": c["criterion_id"],
                "kind": "inclusion fail",
                "rate": c["fail_rate"],
                "n": c["fail_n"],
            }
            for c in inclusions
        ]
        + [
            {
                "criterion_id": c["criterion_id"],
                "kind": "exclusion trigger",
                "rate": c["trigger_rate"],
                "n": c["trigger_n"],
            }
            for c in exclusions
        ],
        key=lambda d: (-d["rate"], d["criterion_id"]),
    )[:5]
    return {
        "n_evaluations": n,
        "inclusions": inclusions,
        "exclusions": exclusions,
        "top_drivers": drivers,
        "note": (
            "Rates over stored match runs. Small n is directional only; "
            "missing-heavy criteria point at data capture, fail-heavy ones "
            "at criterion stringency."
        ),
    }
