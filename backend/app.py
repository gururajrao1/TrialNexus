"""TrialNexus FastAPI entrypoint (MVP: 4 cookbook agents). Run from the project root:

uvicorn backend.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:  # normal: run from project root as backend.app
    from backend.agents.cohort_matcher import evaluate_cohort
    from backend.agents.protocol_auditor import parse_protocol
    from backend.agents.safety_triage import triage_records
    from backend.agents.site_scout import fetch_ctgov_competitors, score_sites
    from backend.database import (
        get_protocol,
        init_db,
        insert_patient_evaluation,
        insert_safety_query,
        save_protocol_audit,
        save_site_feasibility,
        table_counts,
    )
except ImportError:  # fallback: run with backend/ as cwd
    from agents.cohort_matcher import evaluate_cohort  # type: ignore[no-redef]
    from agents.protocol_auditor import parse_protocol  # type: ignore[no-redef]
    from agents.safety_triage import triage_records  # type: ignore[no-redef]
    from agents.site_scout import (  # type: ignore[no-redef]
        fetch_ctgov_competitors,
        score_sites,
    )
    from database import (  # type: ignore[no-redef]
        get_protocol,
        init_db,
        insert_patient_evaluation,
        insert_safety_query,
        save_protocol_audit,
        save_site_feasibility,
        table_counts,
    )

app = FastAPI(title="TrialNexus Multi-Agent OS API")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/", include_in_schema=False)
def serve_ui() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/api/snapshot")
def snapshot() -> dict[str, Any]:
    init_db()
    counts = table_counts()
    fhir_dir = FRONTEND_DIR.parent / "data" / "fhir" / "synthea"
    ae_file = (
        FRONTEND_DIR.parent / "data" / "raw" / "queries" / "adverse_events_stream.json"
    )
    bundles = (
        sorted(p.name for p in fhir_dir.glob("*.json")) if fhir_dir.exists() else []
    )
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
    {
        "id": "SITE-001",
        "name": "City Cancer Center",
        "country": "USA",
        "historical_activation_days": 75,
        "regulatory_tier": "Tier 1",
        "active_competing_trials": 3,
        "past_accrual_per_month": 2.8,
        "staff_capacity_score": 90,
    },
    {
        "id": "SITE-002",
        "name": "Regional Oncology Hospital",
        "country": "India",
        "historical_activation_days": 140,
        "regulatory_tier": "Tier 3",
        "active_competing_trials": 7,
        "past_accrual_per_month": 1.2,
        "staff_capacity_score": 60,
    },
    {
        "id": "SITE-003",
        "name": "Metro Research Institute",
        "country": "UK",
        "historical_activation_days": 95,
        "regulatory_tier": "Tier 2",
        "active_competing_trials": 4,
        "past_accrual_per_month": 2.0,
        "staff_capacity_score": 75,
    },
]


@app.get("/api/demo-data")
def demo_data() -> dict[str, Any]:
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
    sites: list[dict[str, Any]]
    target_enrollment: int = 0
    competitors: dict[str, int] | None = None
    live_lookup: bool = False
    condition: str = ""


class MatchCohortRequest(BaseModel):
    protocol_id: str
    bundles: list[dict[str, Any]]


class TriageRequest(BaseModel):
    records: list[dict[str, Any]]
    protocol_id: str = "UNASSIGNED"


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "TrialNexus OS", "mode": "zero-cost-local"}


@app.post("/api/audit-protocol/{protocol_id}")
def audit_protocol_endpoint(protocol_id: str) -> dict[str, Any]:
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
def score_sites_endpoint(body: ScoreSitesRequest) -> dict[str, Any]:
    init_db()
    comp_map = dict(body.competitors or {})
    src_map: dict[str, str] = {}
    if body.live_lookup and body.condition.strip():
        for s in body.sites:
            sid = str(s.get("id", ""))
            if sid in comp_map:
                continue
            try:
                r = fetch_ctgov_competitors(
                    body.condition.strip(), str(s.get("country", "") or "")
                )
                comp_map[sid] = r["count"]
                src_map[sid] = r["source"]
            except Exception:
                pass
    result = score_sites(body.sites, body.target_enrollment, comp_map, src_map)
    for s in result["evaluated_sites"]:
        save_site_feasibility(s["site_id"], s["feasibility_score"], s)
    return result


@app.post("/api/match-cohort")
def match_cohort_endpoint(body: MatchCohortRequest) -> dict[str, Any]:
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
        insert_patient_evaluation(
            {
                "id": uuid.uuid4().hex[:16],
                "protocol_id": body.protocol_id,
                "patient_fhir_id": r["patient_id"],
                "eligibility_status": r["overall_status"],
                "inclusion_match_score": r["match_percentage"],
                "exclusion_conflict_count": sum(
                    1 for e in r["exclusion_evaluations"] if e["triggered"]
                ),
                "rationale": r,
            }
        )
    return result


@app.post("/api/triage-safety")
def triage_safety_endpoint(body: TriageRequest) -> dict[str, Any]:
    init_db()
    result = triage_records(body.records)
    grade_map = {
        "Grade 1": "MILD",
        "Grade 2": "MODERATE",
        "Grade 3": "SEVERE",
        "Grade 4": "SEVERE",
        "Grade 5": "SEVERE",
    }
    for t in result["triaged_records"]:
        insert_safety_query(
            {
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
            }
        )
    return result
