"""Diversity enrollment planner (FDORA-style). Deterministic, stdlib only.

Compares a matched cohort's mix (race, ethnicity, sex, age from FHIR Patient
resources) against enrollment goals and reports gaps plus catch-up numbers.
Default goals are illustrative US-population-shaped placeholders — replace with
protocol-specific Diversity Action Plan targets.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List

REF_DATE = date(2025, 6, 1)

RACE_BUCKETS = ("White", "Black or African American", "Asian",
                "American Indian or Alaska Native",
                "Native Hawaiian or Pacific Islander", "Other / Unknown")
ETH_BUCKETS = ("Hispanic or Latino", "Not Hispanic or Latino", "Unknown")
SEX_BUCKETS = ("female", "male", "unknown")
AGE_BUCKETS = ("18-39", "40-64", "65+")

DEFAULT_TARGETS: Dict[str, Dict[str, float]] = {
    "race": {"White": 59.0, "Black or African American": 13.0, "Asian": 6.0,
             "American Indian or Alaska Native": 1.0,
             "Native Hawaiian or Pacific Islander": 1.0, "Other / Unknown": 20.0},
    "ethnicity": {"Hispanic or Latino": 19.0, "Not Hispanic or Latino": 79.0,
                  "Unknown": 2.0},
    "sex": {"female": 51.0, "male": 49.0},
    "age": {"18-39": 30.0, "40-64": 45.0, "65+": 25.0},
}


def _patient(bundle: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        return {}
    for e in bundle.get("entry", []):
        r = e.get("resource", {}) if isinstance(e, dict) else {}
        if r.get("resourceType") == "Patient":
            return r
    return {}


def _omb_value(patient: Dict[str, Any], key: str) -> str:
    for ext in patient.get("extension", []) or []:
        if not isinstance(ext, dict):
            continue
        if key in str(ext.get("url", "")).lower():
            v = ext.get("valueString")
            if v:
                return str(v).strip()
            cc = ext.get("valueCodeableConcept", {})
            if isinstance(cc, dict) and cc.get("text"):
                return str(cc["text"]).strip()
    return ""


def _race_bucket(raw: str) -> str:
    v = raw.lower()
    if not v:
        return "Other / Unknown"
    if "black" in v or "african american" in v:
        return "Black or African American"
    if "asian" in v:
        return "Asian"
    if "american indian" in v or "alaska native" in v:
        return "American Indian or Alaska Native"
    if "hawaiian" in v or "pacific islander" in v:
        return "Native Hawaiian or Pacific Islander"
    if "white" in v or "caucasian" in v:
        return "White"
    return "Other / Unknown"


def _eth_bucket(raw: str) -> str:
    v = raw.lower().strip()
    if not v:
        return "Unknown"
    if "hispanic" in v or "latino" in v or "latina" in v:
        if v.startswith("not ") or v.startswith("non") or "not hispanic" in v:
            return "Not Hispanic or Latino"
        return "Hispanic or Latino"
    return "Unknown"


def _sex_bucket(patient: Dict[str, Any]) -> str:
    g = str(patient.get("gender", "unknown")).lower()
    return g if g in ("female", "male") else "unknown"


def _age_bucket(patient: Dict[str, Any]) -> str:
    birth = patient.get("birthDate")
    if not birth:
        return "unknown"
    try:
        years = (REF_DATE - date.fromisoformat(str(birth)[:10])).days // 365
    except ValueError:
        return "unknown"
    if years < 40:
        return "18-39"
    if years < 65:
        return "40-64"
    return "65+"


def _need_to_enroll(actual: int, n: int, goal_pct: float) -> int:
    """Extra enrollments in this group so its share reaches goal_pct."""
    g = goal_pct / 100.0
    if n <= 0 or g <= 0:
        return 0
    if g >= 1.0:
        return 0 if actual >= n else -1  # unreachable without replacing cohort
    return max(0, math.ceil((g * n - actual) / (1.0 - g)))


def plan_diversity(
    bundles: List[Dict[str, Any]],
    targets: Dict[str, Dict[str, float]] | None = None,
) -> Dict[str, Any]:
    """Compare cohort mix vs goals; gaps in percentage points."""
    tg = targets or DEFAULT_TARGETS
    n = len(bundles)
    counts: Dict[str, Dict[str, int]] = {
        "race": {}, "ethnicity": {}, "sex": {}, "age": {},
    }
    for b in bundles:
        p = _patient(b)
        counts["race"][_race_bucket(_omb_value(p, "race"))] = \
            counts["race"].get(_race_bucket(_omb_value(p, "race")), 0) + 1
        counts["ethnicity"][_eth_bucket(_omb_value(p, "ethnicity"))] = \
            counts["ethnicity"].get(_eth_bucket(_omb_value(p, "ethnicity")), 0) + 1
        counts["sex"][_sex_bucket(p)] = counts["sex"].get(_sex_bucket(p), 0) + 1
        counts["age"][_age_bucket(p)] = counts["age"].get(_age_bucket(p), 0) + 1
    dimensions: Dict[str, List[Dict[str, Any]]] = {}
    shortfalls: List[Dict[str, Any]] = []
    for dim, goals in tg.items():
        rows = []
        for group, goal in goals.items():
            a = counts.get(dim, {}).get(group, 0)
            actual_pct = round(100.0 * a / n, 1) if n else 0.0
            gap = round(goal - actual_pct, 1)
            if gap <= 0:
                status = "on-track"
            elif gap <= 5:
                status = "at-risk"
            elif gap <= 15:
                status = "behind"
            else:
                status = "off-track"
            need = _need_to_enroll(a, n, goal)
            rows.append({"group": group, "n": a, "actual_pct": actual_pct,
                         "goal_pct": goal, "gap_pp": gap, "status": status,
                         "need_to_enroll": need})
            if gap > 0:
                shortfalls.append({"dimension": dim, "group": group, "gap_pp": gap,
                                   "need_to_enroll": need})
        dimensions[dim] = sorted(rows, key=lambda r: r["gap_pp"], reverse=True)
    shortfalls.sort(key=lambda s: s["gap_pp"], reverse=True)
    focus = [f"Enroll {s['need_to_enroll']}+ more {s['group']} ({s['dimension']}) "
             f"to close a {s['gap_pp']}pp gap" if s["need_to_enroll"] >= 0
             else f"{s['group']} ({s['dimension']}) goal unreachable at n={n} — reset target"
             for s in shortfalls[:3]]
    states = [r["status"] for rows in dimensions.values() for r in rows]
    if any(s == "off-track" for s in states):
        overall = "needs-work"
    elif any(s in ("behind", "at-risk") for s in states):
        overall = "watch"
    else:
        overall = "ready"
    return {"n": n, "targets_used": tg, "dimensions": dimensions,
            "focus_areas": focus, "overall_status": overall,
            "note": "Default goals are illustrative; replace with protocol DAP targets."}
