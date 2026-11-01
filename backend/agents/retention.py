"""Dropout/retention risk: deterministic bootloader scorer.

Estimates per-patient discontinuation risk from visit burden, visit load,
and frailty proxies (age, ECOG, polypharmacy, comorbidity count) —
the consistently reported dropout drivers in retention literature.
Reports modifiable factors plus a what-if rescore with convertible
visits done remotely. Transparent points, no fitted weights.
Deterministic, stdlib only.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from backend.agents.cohort_matcher import observations, patient_age


def _bundle_facts(bundle: dict[str, Any], ref: date) -> dict[str, Any]:
    meds = sum(
        1
        for e in bundle.get("entry", [])
        if isinstance(e, dict)
        and (e.get("resource", {}) or {}).get("resourceType")
        in ("MedicationStatement", "MedicationRequest")
    )
    conds = sum(
        1
        for e in bundle.get("entry", [])
        if isinstance(e, dict)
        and (e.get("resource", {}) or {}).get("resourceType") == "Condition"
    )
    ecog = None
    for o in observations(bundle):
        if "ecog" in o["text"] or "performance" in o["text"]:
            try:
                ecog = int(float(o["value"]))
                break
            except (TypeError, ValueError):
                continue
    try:
        age = patient_age(bundle, ref)
    except (TypeError, ValueError):
        age = None
    return {"age": age, "ecog": ecog, "meds": meds, "conds": conds}


def retention_risk(
    burden: dict[str, Any],
    bundle: dict[str, Any],
    ref_date: date | None = None,
) -> dict[str, Any]:
    ref = ref_date or date(2025, 6, 1)
    facts = _bundle_facts(bundle, ref)
    visits = burden.get("visits", []) or []
    total = float(burden.get("total_score", 0) or 0)

    factors: list[dict[str, Any]] = []
    burden_pts = min(40, round(total * 1.2))
    factors.append(
        {
            "factor": f"Visit burden {total:g} across {len(visits)} visits",
            "points": burden_pts,
            "modifiable": True,
        }
    )
    visit_pts = min(20, len(visits) * 4)
    factors.append(
        {
            "factor": f"{len(visits)} on-site visits",
            "points": visit_pts,
            "modifiable": True,
        }
    )
    frailty = 0
    if facts["age"] is not None and facts["age"] >= 70:
        frailty += 8
        factors.append(
            {"factor": f"Age {facts['age']} ≥ 70", "points": 8, "modifiable": False}
        )
    if facts["ecog"] is not None and facts["ecog"] >= 2:
        frailty += 8
        factors.append(
            {"factor": f"ECOG {facts['ecog']} ≥ 2", "points": 8, "modifiable": False}
        )
    if facts["meds"] >= 5:
        frailty += 5
        factors.append(
            {
                "factor": f"Polypharmacy ({facts['meds']} meds)",
                "points": 5,
                "modifiable": False,
            }
        )
    if facts["conds"] >= 4:
        frailty += 4
        factors.append(
            {
                "factor": f"{facts['conds']} active conditions",
                "points": 4,
                "modifiable": False,
            }
        )
    score = min(100, burden_pts + visit_pts + frailty)

    convertible = [v for v in visits if v.get("convertible")]
    remote_relief = sum(float(v.get("score", 0) or 0) for v in convertible) * 0.5
    wi_total = max(0.0, total - remote_relief)
    wi_score = min(100, min(40, round(wi_total * 1.2)) + visit_pts + frailty)

    def _band(s: int) -> str:
        return "low" if s < 30 else ("moderate" if s < 60 else "high")

    return {
        "score": score,
        "band": _band(score),
        "factors": factors,
        "facts": facts,
        "what_if_remote": {
            "convertible_visits": len(convertible),
            "score": wi_score,
            "band": _band(wi_score),
            "delta": wi_score - score,
        },
        "basis": (
            "Bootloader points (max 100): visit burden ≤40, visit load ≤20, "
            "frailty ≤25 (age≥70, ECOG≥2, ≥5 meds, ≥4 conditions). Remote "
            "visits halve their burden in the what-if. Literature-backed "
            "drivers; weights are transparent, not fitted."
        ),
    }
