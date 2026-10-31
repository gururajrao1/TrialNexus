"""Core routes: health, UI feeds, and the 4 cookbook agents."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.cohort_matcher import evaluate_cohort
from backend.agents.protocol_auditor import parse_protocol
from backend.agents.safety_triage import triage_records
from backend.agents.site_scout import fetch_ctgov_competitors, score_sites
from backend.config import AE_STREAM, FHIR_DIR
from backend.database import (
    get_protocol,
    init_db,
    insert_patient_evaluation,
    insert_safety_query,
    save_protocol_audit,
    save_site_feasibility,
    table_counts,
)

router = APIRouter()


@router.get("/api/snapshot")
def snapshot() -> Dict[str, Any]:
    init_db()
    counts = table_counts()
    bundles = sorted(p.name for p in FHIR_DIR.glob("*.json")) if FHIR_DIR.exists() else []
    ae_records = json.loads(AE_STREAM.read_text()) if AE_STREAM.exists() else []
    return {
        "protocols": counts.get("protocols", 0),
        "sites": counts.get("sites", 0),
        "fhir_bundles": len(bundles),
        "ae_records": len(ae_records),
        "evaluations": counts.get("patient_evaluations", 0),
        "safety_queries": counts.get("safety_queries", 0),
    }


DEMO_SITES = [
    {"id": "SITE-001", "name": "City Cancer Center", "country": "USA",
     "historical_activation_days": 75, "regulatory_tier": "Tier 1",
     "active_competing_trials": 3, "past_accrual_per_month": 2.8,
     "staff_capacity_score": 90},
    {"id": "SITE-002", "name": "Regional Oncology Hospital", "country": "India",
     "historical_activation_days": 140, "regulatory_tier": "Tier 3",
     "active_competing_trials": 7, "past_accrual_per_month": 1.2,
     "staff_capacity_score": 60},
    {"id": "SITE-003", "name": "Metro Research Institute", "country": "UK",
     "historical_activation_days": 95, "regulatory_tier": "Tier 2",
     "active_competing_trials": 4, "past_accrual_per_month": 2.0,
     "staff_capacity_score": 75},
]


@router.get("/api/demo-data")
def demo_data() -> Dict[str, Any]:
    bundles = []
    if FHIR_DIR.exists():
        for p in sorted(FHIR_DIR.glob("*.json")):
            bundles.append({"name": p.name, "bundle": json.loads(p.read_text())})
    ae_records = json.loads(AE_STREAM.read_text()) if AE_STREAM.exists() else []
    return {"sites": DEMO_SITES, "bundles": bundles, "ae_records": ae_records}


class ScoreSitesRequest(BaseModel):
    sites: List[Dict[str, Any]]
    target_enrollment: int = 0
    competitors: Optional[Dict[str, int]] = None
    live_lookup: bool = False
    condition: str = ""


class MatchCohortRequest(BaseModel):
    protocol_id: str
    bundles: List[Dict[str, Any]]


class TriageRequest(BaseModel):
    records: List[Dict[str, Any]]
    protocol_id: str = "UNASSIGNED"


@router.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "TrialNexus OS", "mode": "zero-cost-local"}


@router.post("/api/audit-protocol/{protocol_id}")
def audit_protocol_endpoint(protocol_id: str) -> Dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    audit = parse_protocol(proto["raw_content"])
    structured = {
        "inclusion_criteria": audit["inclusion_criteria"],
        "exclusion_criteria": audit["exclusion_criteria"],
    }
    save_protocol_audit(protocol_id, structured, audit)
    return audit


@router.post("/api/score-sites")
def score_sites_endpoint(body: ScoreSitesRequest) -> Dict[str, Any]:
    init_db()
    comp_map = dict(body.competitors or {})
    src_map: Dict[str, str] = {}
    if body.live_lookup and body.condition.strip():
        for s in body.sites:
            sid = str(s.get("id", ""))
            if sid in comp_map:
                continue
            try:
                r = fetch_ctgov_competitors(
                    body.condition.strip(), str(s.get("country", "") or ""))
                comp_map[sid] = r["count"]
                src_map[sid] = r["source"]
            except Exception:
                pass
    result = score_sites(body.sites, body.target_enrollment, comp_map, src_map)
    for s in result["evaluated_sites"]:
        save_site_feasibility(s["site_id"], s["feasibility_score"], s)
    return result


@router.post("/api/match-cohort")
def match_cohort_endpoint(body: MatchCohortRequest) -> Dict[str, Any]:
    init_db()
    proto = get_protocol(body.protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    if not proto["structured_ie_criteria"]:
        raise HTTPException(
            status_code=400,
            detail="Protocol not audited yet; call /api/audit-protocol/{id} first",
        )
    criteria = json.loads(proto["structured_ie_criteria"])
    result = evaluate_cohort(criteria, body.bundles)
    for r in result["matching_results"]:
        insert_patient_evaluation({
            "id": uuid.uuid4().hex[:16],
            "protocol_id": body.protocol_id,
            "patient_fhir_id": r["patient_id"],
            "eligibility_status": r["overall_status"],
            "inclusion_match_score": r["match_percentage"],
            "exclusion_conflict_count": sum(1 for e in r["exclusion_evaluations"] if e["triggered"]),
            "rationale": r,
        })
    return result


@router.post("/api/triage-safety")
def triage_safety_endpoint(body: TriageRequest) -> Dict[str, Any]:
    init_db()
    result = triage_records(body.records)
    grade_map = {"Grade 1": "MILD", "Grade 2": "MODERATE", "Grade 3": "SEVERE",
                 "Grade 4": "SEVERE", "Grade 5": "SEVERE"}
    for t in result["triaged_records"]:
        insert_safety_query({
            "id": uuid.uuid4().hex[:16],
            "protocol_id": body.protocol_id,
            "patient_id": t["patient_id"],
            "reported_term": t["reported_term"],
            "suspected_meddra_soc": t["meddra_classification"]["soc"],
            "severity": grade_map.get(t["severity_grade"], "MODERATE"),
            "is_sae": t["is_sae"],
            "reporting_timeline_hours": t["reporting_deadline_hours"],
            "query_text": t["site_query"]["query_text"],
            "resolution_status": "TRIAGED",
        })
    return result


def audited_criteria(protocol_id: str) -> Dict[str, Any]:
    """Structured I/E criteria, auditing on demand. Shared by other routers."""
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    if proto["structured_ie_criteria"]:
        return json.loads(proto["structured_ie_criteria"])
    audit = parse_protocol(proto["raw_content"])
    crit = {"inclusion_criteria": audit["inclusion_criteria"],
            "exclusion_criteria": audit["exclusion_criteria"]}
    save_protocol_audit(protocol_id, crit, audit)
    return crit
