"""TrialNexus FastAPI entrypoint. Run from the project root:

    uvicorn backend.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:  # normal: run from project root as backend.app
    from backend.database import (
        get_protocol,
        init_db,
        insert_patient_evaluation,
        insert_safety_query,
        list_patient_evaluations,
        list_protocols,
        list_safety_queries,
        list_site_metrics,
        list_sites,
        list_startup,
        save_protocol_audit,
        save_site_feasibility,
        table_counts,
        upsert_startup_site,
    )
    from backend.agents.protocol_auditor import parse_protocol
    from backend.agents.site_scout import fetch_ctgov_competitors, score_sites
    from backend.agents.cohort_matcher import evaluate_cohort
    from backend.agents.safety_triage import triage_records
    from backend.agents.diversity_planner import DEFAULT_TARGETS, plan_diversity
    from backend.agents.structured_export import build_structure
    from backend.agents.burden_scorer import score_burden
    from backend.agents.startup_tracker import STAGES, startup_report
    from backend.agents.kri_monitor import portfolio_kris
    from backend.agents.trial_finder import rank_trials
    from backend.agents.external_control import build_external_control
    from backend.agents.enrollment_forecast import forecast
    from backend.agents.risk_models import outlook
    from backend.agents.twin_generator import twin_distribution
    from backend.agents.mcode import mcode_profile
    from backend.agents.n2c2_harness import CRITERIA, load_fixture, micro_f1
except ImportError:  # fallback: run with backend/ as cwd
    from database import (  # type: ignore[no-redef]
        get_protocol,
        init_db,
        insert_patient_evaluation,
        insert_safety_query,
        list_patient_evaluations,
        list_protocols,
        list_safety_queries,
        list_site_metrics,
        list_sites,
        list_startup,
        save_protocol_audit,
        save_site_feasibility,
        table_counts,
        upsert_startup_site,
    )
    from agents.protocol_auditor import parse_protocol  # type: ignore[no-redef]
    from agents.site_scout import fetch_ctgov_competitors, score_sites  # type: ignore[no-redef]
    from agents.cohort_matcher import evaluate_cohort  # type: ignore[no-redef]
    from agents.safety_triage import triage_records  # type: ignore[no-redef]
    from agents.diversity_planner import DEFAULT_TARGETS, plan_diversity  # type: ignore[no-redef]
    from agents.structured_export import build_structure  # type: ignore[no-redef]
    from agents.burden_scorer import score_burden  # type: ignore[no-redef]
    from agents.startup_tracker import STAGES, startup_report  # type: ignore[no-redef]
    from agents.kri_monitor import portfolio_kris  # type: ignore[no-redef]
    from agents.trial_finder import rank_trials  # type: ignore[no-redef]
    from agents.external_control import build_external_control  # type: ignore[no-redef]
    from agents.enrollment_forecast import forecast  # type: ignore[no-redef]
    from agents.risk_models import outlook  # type: ignore[no-redef]
    from agents.twin_generator import twin_distribution  # type: ignore[no-redef]
    from agents.mcode import mcode_profile  # type: ignore[no-redef]
    from agents.n2c2_harness import CRITERIA, load_fixture, micro_f1  # type: ignore[no-redef]

app = FastAPI(title="TrialNexus Multi-Agent OS API")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/", include_in_schema=False)
def serve_ui() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/snapshot")
def snapshot() -> Dict[str, Any]:
    init_db()
    counts = table_counts()
    fhir_dir = FRONTEND_DIR.parent / "data" / "fhir" / "synthea"
    ae_file = FRONTEND_DIR.parent / "data" / "raw" / "queries" / "adverse_events_stream.json"
    bundles = sorted(p.name for p in fhir_dir.glob("*.json")) if fhir_dir.exists() else []
    ae_records = json.loads(ae_file.read_text()) if ae_file.exists() else []
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


@app.get("/api/demo-data")
def demo_data() -> Dict[str, Any]:
    root = FRONTEND_DIR.parent
    bundles = []
    fhir_dir = root / "data" / "fhir" / "synthea"
    if fhir_dir.exists():
        for p in sorted(fhir_dir.glob("*.json")):
            bundles.append({"name": p.name, "bundle": json.loads(p.read_text())})
    ae_file = root / "data" / "raw" / "queries" / "adverse_events_stream.json"
    ae_records = json.loads(ae_file.read_text()) if ae_file.exists() else []
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


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "TrialNexus OS", "mode": "zero-cost-local"}


@app.post("/api/audit-protocol/{protocol_id}")
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


@app.post("/api/score-sites")
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


@app.post("/api/match-cohort")
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


@app.post("/api/triage-safety")
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


class DiversityRequest(BaseModel):
    bundles: List[Dict[str, Any]]
    targets: Optional[Dict[str, Dict[str, float]]] = None


@app.post("/api/diversity-plan")
def diversity_plan_endpoint(body: DiversityRequest) -> Dict[str, Any]:
    return plan_diversity(body.bundles, body.targets)


@app.get("/api/diversity-defaults")
def diversity_defaults() -> Dict[str, Any]:
    return {"targets": DEFAULT_TARGETS,
            "note": "Illustrative defaults; replace with protocol DAP targets."}


@app.get("/api/history/cohort")
def history_cohort(protocol_id: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    return {"evaluations": list_patient_evaluations(protocol_id)}


@app.get("/api/history/safety")
def history_safety(protocol_id: Optional[str] = None) -> Dict[str, Any]:
    init_db()
    return {"queries": list_safety_queries(protocol_id)}


@app.get("/api/export/cohort.csv")
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


@app.get("/api/export/safety.csv")
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


@app.get("/api/protocol-structure/{protocol_id}")
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


@app.get("/api/burden/{protocol_id}")
def burden_endpoint(protocol_id: str) -> Dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return score_burden(proto["raw_content"])


@app.get("/api/startup")
def startup_portfolio() -> Dict[str, Any]:
    init_db()
    return startup_report(list_startup(), list_sites())


@app.post("/api/startup/{site_id}/advance")
def startup_advance(site_id: str, body: StartupAdvance) -> Dict[str, Any]:
    init_db()
    if body.stage not in STAGES:
        raise HTTPException(status_code=400, detail=f"Unknown stage; expected one of {list(STAGES)}")
    return upsert_startup_site(site_id, body.stage, body.date, body.note)


def _audited_criteria(protocol_id: str) -> Dict[str, Any]:
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


@app.get("/api/monitoring")
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


@app.post("/api/find-trials")
def find_trials(body: FindTrialsRequest) -> Dict[str, Any]:
    init_db()
    protocols = []
    for p in list_protocols():
        protocols.append({"id": p["id"], "title": p["title"], "phase": p["phase"],
                          "criteria": _audited_criteria(p["id"])})
    return rank_trials(body.bundle, protocols)


class ExternalControlRequest(BaseModel):
    protocol_id: str
    relax_ids: List[str] = []
    bundles: Optional[List[Dict[str, Any]]] = None


@app.post("/api/external-control")
def external_control(body: ExternalControlRequest) -> Dict[str, Any]:
    init_db()
    crit = _audited_criteria(body.protocol_id)
    bundles = body.bundles
    if not bundles:
        fhir_dir = FRONTEND_DIR.parent / "data" / "fhir" / "synthea"
        bundles = [json.loads(p.read_text()) for p in sorted(fhir_dir.glob("*.json"))] \
            if fhir_dir.exists() else []
    return build_external_control(crit, bundles, body.relax_ids)


class ForecastRequest(BaseModel):
    sites: List[Dict[str, Any]]
    target_enrollment: int
    enrolled_so_far: int = 0
    deadline_months: Optional[float] = None
    seed: int = 42


class TwinsRequest(BaseModel):
    protocol_id: str
    bundle: Optional[Dict[str, Any]] = None
    bundle_id: Optional[str] = None
    n: int = 100
    seed: int = 7


class McodeRequest(BaseModel):
    bundle: Dict[str, Any]


@app.get("/api/trial-outlook/{protocol_id}")
def trial_outlook(protocol_id: str) -> Dict[str, Any]:
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
    return outlook(audit, score_burden(proto["raw_content"]))


@app.post("/api/forecast")
def forecast_endpoint(body: ForecastRequest) -> Dict[str, Any]:
    return forecast(body.sites, body.target_enrollment, body.enrolled_so_far,
                    body.deadline_months, seed=body.seed)


@app.post("/api/twins")
def twins_endpoint(body: TwinsRequest) -> Dict[str, Any]:
    init_db()
    bundle = body.bundle
    if bundle is None and body.bundle_id:
        p = FRONTEND_DIR.parent / "data" / "fhir" / "synthea" / f"{body.bundle_id}.json"
        if not p.exists():
            raise HTTPException(status_code=404, detail="Bundle not found")
        bundle = json.loads(p.read_text())
    if bundle is None:
        raise HTTPException(status_code=400, detail="Provide bundle or bundle_id")
    return twin_distribution(_audited_criteria(body.protocol_id), bundle, body.n, body.seed)


@app.post("/api/mcode")
def mcode_endpoint(body: McodeRequest) -> Dict[str, Any]:
    return mcode_profile(body.bundle)


@app.get("/api/n2c2-status")
def n2c2_status() -> Dict[str, Any]:
    data_dir = FRONTEND_DIR.parent / "data" / "n2c2"
    present = data_dir.exists() and any(data_dir.glob("*.txt"))
    return {"fixture_f1": micro_f1(load_fixture())["micro_f1"],
            "real_data_present": present,
            "criteria": list(CRITERIA),
            "instructions": ("Request n2c2 2018 cohort-selection data via the n2c2/Harvard DBMI "
                             "data-use agreement, then place {id}.txt notes + labels.csv under "
                             "data/n2c2/ and run: python -m backend.agents.n2c2_harness data/n2c2")}
