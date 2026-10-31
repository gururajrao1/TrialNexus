"""Product routes: diversity, history/export, structure, burden, startup,
monitoring, trial finder, external control."""

from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.agents.burden_scorer import score_burden
from backend.agents.diversity_planner import DEFAULT_TARGETS, plan_diversity
from backend.agents.external_control import build_external_control
from backend.agents.kri_monitor import portfolio_kris
from backend.agents.protocol_auditor import parse_protocol
from backend.agents.startup_tracker import STAGES, startup_report
from backend.agents.structured_export import build_structure
from backend.agents.trial_finder import rank_trials
from backend.config import FHIR_DIR
from backend.database import (
    get_protocol,
    init_db,
    list_patient_evaluations,
    list_protocols,
    list_safety_queries,
    list_site_metrics,
    list_sites,
    list_startup,
    save_protocol_audit,
    upsert_startup_site,
)
from backend.routes.core import audited_criteria

router = APIRouter()


class DiversityRequest(BaseModel):
    bundles: List[Dict[str, Any]]
    targets: Optional[Dict[str, Dict[str, float]]] = None


@router.post("/api/diversity-plan")
def diversity_plan_endpoint(body: DiversityRequest) -> Dict[str, Any]:
    return plan_diversity(body.bundles, body.targets)


@router.get("/api/diversity-defaults")
def diversity_defaults() -> Dict[str, Any]:
    return {"targets": DEFAULT_TARGETS,
            "note": "Illustrative defaults; replace with protocol DAP targets."}


@router.get("/api/history/cohort")
def history_cohort(protocol_id: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    return {"evaluations": list_patient_evaluations(protocol_id)}


@router.get("/api/history/safety")
def history_safety(protocol_id: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    return {"queries": list_safety_queries(protocol_id)}


@router.get("/api/export/cohort.csv")
def export_cohort_csv(protocol_id: Optional[str] = None) -> Response:
    init_db()
    rows = list_patient_evaluations(protocol_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "protocol_id", "patient_fhir_id", "eligibility_status",
                "inclusion_match_score", "exclusion_conflict_count", "evaluated_at"])
    for r in rows:
        w.writerow([r["id"], r["protocol_id"], r["patient_fhir_id"], r["eligibility_status"],
                    r["inclusion_match_score"], r["exclusion_conflict_count"], r["evaluated_at"]])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=cohort_history.csv"})


@router.get("/api/export/safety.csv")
def export_safety_csv(protocol_id: Optional[str] = None) -> Response:
    init_db()
    rows = list_safety_queries(protocol_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "protocol_id", "patient_id", "reported_term", "suspected_meddra_soc",
                "severity", "is_sae", "reporting_timeline_hours", "resolution_status", "created_at"])
    for r in rows:
        w.writerow([r["id"], r["protocol_id"], r["patient_id"], r["reported_term"],
                    r["suspected_meddra_soc"], r["severity"], r["is_sae"],
                    r["reporting_timeline_hours"], r["resolution_status"], r["created_at"]])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=safety_history.csv"})


class StartupAdvance(BaseModel):
    stage: str
    date: Optional[str] = None
    note: str = ""


@router.get("/api/protocol-structure/{protocol_id}")
def protocol_structure(protocol_id: str) -> Dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    audit = json.loads(proto["audit_results"]) if proto["audit_results"] else None
    if not audit:
        audit = parse_protocol(proto["raw_content"])
        save_protocol_audit(protocol_id, {
            "inclusion_criteria": audit["inclusion_criteria"],
            "exclusion_criteria": audit["exclusion_criteria"]}, audit)
    return build_structure(audit, protocol_id, proto["raw_content"])


@router.get("/api/burden/{protocol_id}")
def burden_endpoint(protocol_id: str) -> Dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return score_burden(proto["raw_content"])


@router.get("/api/startup")
def startup_portfolio() -> Dict[str, Any]:
    init_db()
    return startup_report(list_startup(), list_sites())


@router.post("/api/startup/{site_id}/advance")
def startup_advance(site_id: str, body: StartupAdvance) -> Dict[str, Any]:
    init_db()
    if body.stage not in STAGES:
        raise HTTPException(status_code=400, detail=f"Unknown stage; expected one of {list(STAGES)}")
    return upsert_startup_site(site_id, body.stage, body.date, body.note)


@router.get("/api/monitoring")
def monitoring() -> Dict[str, Any]:
    init_db()
    rows: Dict[str, List[Dict[str, Any]]] = {}
    for r in list_site_metrics():
        rows.setdefault(r["site_id"], []).append(r)
    for v in rows.values():
        v.sort(key=lambda r: r["month"])
    return portfolio_kris(rows)


class FindTrialsRequest(BaseModel):
    bundle: Dict[str, Any]


@router.post("/api/find-trials")
def find_trials(body: FindTrialsRequest) -> Dict[str, Any]:
    init_db()
    protocols = []
    for p in list_protocols():
        protocols.append({"id": p["id"], "title": p["title"], "phase": p["phase"],
                          "criteria": audited_criteria(p["id"])})
    return rank_trials(body.bundle, protocols)


class ExternalControlRequest(BaseModel):
    protocol_id: str
    relax_ids: List[str] = []
    bundles: Optional[List[Dict[str, Any]]] = None


@router.post("/api/external-control")
def external_control(body: ExternalControlRequest) -> Dict[str, Any]:
    init_db()
    crit = audited_criteria(body.protocol_id)
    bundles = body.bundles
    if not bundles:
        bundles = [json.loads(p.read_text()) for p in sorted(FHIR_DIR.glob("*.json"))] \
            if FHIR_DIR.exists() else []
    return build_external_control(crit, bundles, body.relax_ids)
