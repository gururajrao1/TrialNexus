"""Product routes: diversity, history/export, structure, burden, startup,
monitoring, trial finder, external control."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.agents.attrition import predict_attrition
from backend.agents.burden_scorer import score_burden
from backend.agents.consent_helper import check_consent
from backend.agents.crf_trace import trace_criteria
from backend.agents.criteria_feedback import design_feedback
from backend.agents.csm import csm_screen
from backend.agents.dct_readiness import dct_readiness
from backend.agents.deviation_watch import watch_deviations
from backend.agents.diversity_planner import DEFAULT_TARGETS, plan_diversity
from backend.agents.external_control import build_external_control
from backend.agents.failure_forensics import forensic_report
from backend.agents.kri_monitor import portfolio_kris
from backend.agents.lock_readiness import lock_readiness, query_aging
from backend.agents.protocol_auditor import parse_protocol
from backend.agents.pubmed import fetch_pubmed
from backend.agents.real_data import (
    attach_rxnorm,
    fetch_clinvar,
    fetch_dailymed_label,
    fetch_drug_label,
    fetch_faers,
    fetch_gene_card,
    fetch_live_studies,
    fetch_npi,
    fetch_recalls,
    fetch_rxnorm_id,
    fetch_variant_highlights,
)
from backend.agents.retention import retention_risk
from backend.agents.safety_triage import triage_records
from backend.agents.signal_detection import detect_signals
from backend.agents.site_scout import fetch_ctgov_outcomes
from backend.agents.startup_tracker import STAGES, startup_report
from backend.agents.structured_export import build_structure
from backend.agents.trial_finder import rank_trials
from backend.agents.trial_matcher import (
    match_trials,
    referral_letter,
    screening_questions,
)
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
    update_safety_resolution,
    upsert_startup_site,
)
from backend.routes.core import audited_criteria

router = APIRouter()


class DiversityRequest(BaseModel):
    bundles: list[dict[str, Any]]
    targets: dict[str, dict[str, float]] | None = None


@router.post("/api/diversity-plan")
def diversity_plan_endpoint(body: DiversityRequest) -> dict[str, Any]:
    return plan_diversity(body.bundles, body.targets)


@router.get("/api/diversity-defaults")
def diversity_defaults() -> dict[str, Any]:
    return {
        "targets": DEFAULT_TARGETS,
        "note": "Illustrative defaults; replace with protocol DAP targets.",
    }


@router.get("/api/history/cohort")
def history_cohort(protocol_id: str | None = None) -> dict[str, Any]:
    init_db()
    return {"evaluations": list_patient_evaluations(protocol_id)}


@router.get("/api/history/safety")
def history_safety(protocol_id: str | None = None) -> dict[str, Any]:
    init_db()
    return {"queries": list_safety_queries(protocol_id)}


@router.get("/api/lock-readiness/{protocol_id}")
def lock_readiness_endpoint(protocol_id: str) -> dict[str, Any]:
    init_db()
    return lock_readiness(list_safety_queries(protocol_id))


@router.get("/api/query-aging/{protocol_id}")
def query_aging_endpoint(protocol_id: str) -> dict[str, Any]:
    init_db()
    return query_aging(list_safety_queries(protocol_id))


@router.get("/api/faers")
def faers_lookup(drug: str, event: str = "") -> dict[str, Any]:
    if not drug.strip():
        raise HTTPException(status_code=400, detail="drug is required")
    return fetch_faers(drug.strip(), event)


@router.get("/api/gene-card")
def gene_card(gene: str) -> dict[str, Any]:
    if not gene.strip():
        raise HTTPException(status_code=400, detail="gene is required")
    card = fetch_gene_card(gene.strip())
    card["variant_highlights"] = fetch_variant_highlights(gene.strip())
    return card


@router.get("/api/drug-safety")
def drug_safety(drug: str, event: str = "") -> dict[str, Any]:
    if not drug.strip():
        raise HTTPException(status_code=400, detail="drug is required")
    return {
        "drug": drug.strip(),
        "event": event.strip(),
        "rxnorm": fetch_rxnorm_id(drug.strip()),
        "faers": fetch_faers(drug.strip(), event.strip()),
        "label": fetch_drug_label(drug.strip()),
        "dailymed": fetch_dailymed_label(drug.strip()),
        "recalls": fetch_recalls(drug.strip()),
    }


@router.get("/api/npi")
def npi_lookup(
    number: str = "",
    first_name: str = "",
    last_name: str = "",
    state: str = "",
) -> dict[str, Any]:
    """NPPES NPI registry: verify an investigator by number or name+state."""
    result = fetch_npi(number, first_name, last_name, state)
    return {
        "query": {
            "number": number,
            "first_name": first_name,
            "last_name": last_name,
            "state": state,
        },
        **result,
    }


@router.get("/api/live-studies")
def live_studies(condition: str, phase: str = "") -> dict[str, Any]:
    if not condition.strip():
        raise HTTPException(status_code=400, detail="condition is required")
    return fetch_live_studies(condition.strip(), phase)


class CrfTraceRequest(BaseModel):
    protocol_id: str
    fields: list[str] = []
    previous_criteria: list[dict[str, Any]] | None = None


@router.post("/api/crf-trace")
def crf_trace_endpoint(body: CrfTraceRequest) -> dict[str, Any]:
    init_db()
    if not body.protocol_id.strip():
        raise HTTPException(status_code=400, detail="protocol_id is required")
    crit = audited_criteria(body.protocol_id.strip())
    return trace_criteria(crit, body.fields, body.previous_criteria)


class ResolveRequest(BaseModel):
    resolution_status: str = "RESOLVED"


@router.put("/api/safety-queries/{query_id}/resolve")
def resolve_query(query_id: str, body: ResolveRequest) -> dict[str, Any]:
    init_db()
    status = body.resolution_status.strip().upper() or "RESOLVED"
    if status not in ("RESOLVED", "TRIAGED", "OPEN"):
        raise HTTPException(status_code=400, detail="unknown resolution_status")
    return {
        "id": query_id,
        "resolution_status": status,
        "updated": update_safety_resolution(query_id, status),
    }


@router.get("/api/export/cohort.csv")
def export_cohort_csv(protocol_id: str | None = None) -> Response:
    init_db()
    rows = list_patient_evaluations(protocol_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "protocol_id",
            "patient_fhir_id",
            "eligibility_status",
            "inclusion_match_score",
            "exclusion_conflict_count",
            "evaluated_at",
        ]
    )
    for r in rows:
        w.writerow(
            [
                r["id"],
                r["protocol_id"],
                r["patient_fhir_id"],
                r["eligibility_status"],
                r["inclusion_match_score"],
                r["exclusion_conflict_count"],
                r["evaluated_at"],
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cohort_history.csv"},
    )


@router.get("/api/export/safety.csv")
def export_safety_csv(protocol_id: str | None = None) -> Response:
    init_db()
    rows = list_safety_queries(protocol_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "protocol_id",
            "patient_id",
            "reported_term",
            "suspected_meddra_soc",
            "severity",
            "is_sae",
            "reporting_timeline_hours",
            "resolution_status",
            "created_at",
        ]
    )
    for r in rows:
        w.writerow(
            [
                r["id"],
                r["protocol_id"],
                r["patient_id"],
                r["reported_term"],
                r["suspected_meddra_soc"],
                r["severity"],
                r["is_sae"],
                r["reporting_timeline_hours"],
                r["resolution_status"],
                r["created_at"],
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=safety_history.csv"},
    )


class StartupAdvance(BaseModel):
    stage: str
    date: str | None = None
    note: str = ""


@router.get("/api/protocol-structure/{protocol_id}")
def protocol_structure(protocol_id: str) -> dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    audit = json.loads(proto["audit_results"]) if proto["audit_results"] else None
    if not audit:
        audit = parse_protocol(proto["raw_content"])
        save_protocol_audit(
            protocol_id,
            {
                "inclusion_criteria": audit["inclusion_criteria"],
                "exclusion_criteria": audit["exclusion_criteria"],
            },
            audit,
        )
    return build_structure(audit, protocol_id, proto["raw_content"])


@router.get("/api/burden/{protocol_id}")
def burden_endpoint(protocol_id: str) -> dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return score_burden(proto["raw_content"])


@router.get("/api/dct-readiness/{protocol_id}")
def dct_readiness_endpoint(protocol_id: str) -> dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return dct_readiness(score_burden(proto["raw_content"]), proto["raw_content"])


@router.get("/api/criteria-feedback/{protocol_id}")
def criteria_feedback_endpoint(protocol_id: str) -> dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    if not proto["audit_results"]:
        raise HTTPException(
            status_code=400,
            detail="Protocol not audited yet; call /api/audit-protocol/{id} first",
        )
    return design_feedback(json.loads(proto["audit_results"]))


@router.get("/api/consent-check/{protocol_id}")
def consent_check_protocol(protocol_id: str) -> dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return check_consent(proto["raw_content"])


class ConsentCheckRequest(BaseModel):
    text: str


@router.post("/api/consent-check")
def consent_check_text(body: ConsentCheckRequest) -> dict[str, Any]:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    return check_consent(body.text)


@router.get("/api/startup")
def startup_portfolio() -> dict[str, Any]:
    init_db()
    return startup_report(list_startup(), list_sites())


@router.post("/api/startup/{site_id}/advance")
def startup_advance(site_id: str, body: StartupAdvance) -> dict[str, Any]:
    init_db()
    if body.stage not in STAGES:
        raise HTTPException(
            status_code=400, detail=f"Unknown stage; expected one of {list(STAGES)}"
        )
    return upsert_startup_site(site_id, body.stage, body.date, body.note)


@router.get("/api/monitoring")
def monitoring() -> dict[str, Any]:
    init_db()
    rows: dict[str, list[dict[str, Any]]] = {}
    for r in list_site_metrics():
        rows.setdefault(r["site_id"], []).append(r)
    for v in rows.values():
        v.sort(key=lambda r: r["month"])
    return portfolio_kris(rows)


@router.get("/api/csm")
def csm_endpoint() -> dict[str, Any]:
    init_db()
    return csm_screen(list_site_metrics())


class FindTrialsRequest(BaseModel):
    bundle: dict[str, Any]


@router.post("/api/find-trials")
def find_trials(body: FindTrialsRequest) -> dict[str, Any]:
    init_db()
    protocols = []
    for p in list_protocols():
        protocols.append(
            {
                "id": p["id"],
                "title": p["title"],
                "phase": p["phase"],
                "criteria": audited_criteria(p["id"]),
            }
        )
    return rank_trials(body.bundle, protocols)


class TrialMatchRequest(BaseModel):
    description: str = ""
    condition: str = ""
    location: str = ""
    max_trials: int = 5
    model_explain: bool = False
    model_rerank: bool = False


@router.post("/api/trial-match")
def trial_match(body: TrialMatchRequest) -> dict[str, Any]:
    """Plain-English description -> live CT.gov trials, explained.

    The deterministic pipeline always runs. model_explain / model_rerank add
    a verified model layer (drafts + re-order, both checked or discarded)
    and require TRIALNEXUS_LLM_ENABLED=1; the model endpoint and key come
    from TRIALNEXUS_MODEL_BASE_URL / TRIALNEXUS_MODEL_API_KEY.
    """
    if not body.description.strip():
        raise HTTPException(
            status_code=422, detail="Describe the patient's condition first."
        )
    call_model = None
    if body.model_explain or body.model_rerank:
        if os.getenv("TRIALNEXUS_LLM_ENABLED", "0") != "1":
            raise HTTPException(
                status_code=403,
                detail="Model layer is disabled. Restart the server with "
                "TRIALNEXUS_LLM_ENABLED=1 to use it.",
            )

        from backend.router import ZeroCostRouter

        router = ZeroCostRouter()

        def call_model(system: str, user: str) -> dict[str, Any]:
            result = asyncio.run(router.execute_query(system, user))
            if result.get("engine") == "deterministic-local":
                raise RuntimeError("no model endpoint reachable")
            return result

    try:
        return match_trials(
            body.description,
            condition=body.condition,
            location=body.location,
            max_trials=body.max_trials,
            call_model=call_model,
            allow_rerank=body.model_rerank,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class MonitoringPlanRequest(BaseModel):
    protocol: dict[str, Any] = {}
    site_tiers: list[dict[str, Any]] = []


@router.post("/api/monitoring-plan")
def monitoring_plan_endpoint(body: MonitoringPlanRequest) -> dict[str, Any]:
    """Risk-based monitoring plan from protocol meta + per-site tiers."""
    from backend.agents.ops_tools import monitoring_plan

    return monitoring_plan(body.protocol, body.site_tiers)


class SivChecklistRequest(BaseModel):
    criteria: dict[str, Any] = {}


@router.post("/api/siv-checklist")
def siv_checklist_endpoint(body: SivChecklistRequest) -> dict[str, Any]:
    """SIV checklist from audited I/E criteria plus standards."""
    from backend.agents.ops_tools import siv_checklist

    return siv_checklist(body.criteria)


@router.get("/api/milestone-rollup")
def milestone_rollup_endpoint() -> dict[str, Any]:
    """Activation rollup from the startup pipeline with next actions."""
    from backend.agents.ops_tools import milestone_rollup
    from backend.agents.startup_tracker import startup_report

    init_db()
    return milestone_rollup(startup_report(list_startup(), list_sites()))


class PowerRequest(BaseModel):
    kind: str = "proportions"
    p1: float = 0.5
    p2: float = 0.4
    delta: float = 0.0
    sd: float = 1.0
    alpha: float = 0.05
    power: float = 0.8
    dropout: float = 0.0


@router.post("/api/power")
def power_endpoint(body: PowerRequest) -> dict[str, Any]:
    from backend.agents.power_calc import sample_size_means, sample_size_proportions

    try:
        if body.kind == "means":
            return sample_size_means(
                body.delta, body.sd, body.alpha, body.power, body.dropout
            )
        return sample_size_proportions(
            body.p1, body.p2, body.alpha, body.power, body.dropout
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class NiRequest(BaseModel):
    historical_effect: float = 0.0
    margin: float = 0.0


@router.post("/api/ni-margin")
def ni_margin_endpoint(body: NiRequest) -> dict[str, Any]:
    from backend.agents.power_calc import ni_margin_check

    try:
        return ni_margin_check(body.historical_effect, body.margin)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class SaeNarrativeRequest(BaseModel):
    record: dict[str, Any] = {}


@router.post("/api/sae-narrative")
def sae_narrative_endpoint(body: SaeNarrativeRequest) -> dict[str, Any]:
    from backend.agents.pv_tools import sae_narrative

    if not body.record:
        raise HTTPException(status_code=400, detail="record is required")
    try:
        return sae_narrative(body.record)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ContraRequest(BaseModel):
    label_sections: dict[str, Any] = {}
    meds: list[str] = []
    drug: str = ""
    fetch_live: bool = False


@router.post("/api/contra-screen")
def contra_screen_endpoint(body: ContraRequest) -> dict[str, Any]:
    from backend.agents.pv_tools import screen_concomitant
    from backend.agents.real_data import fetch_drug_label, fetch_label_sections

    sections = dict(body.label_sections)
    if body.fetch_live and body.drug.strip() and not sections:
        card = fetch_drug_label(body.drug.strip())
        sect = fetch_label_sections(body.drug.strip())
        sections = {
            "boxed_warning": card.get("boxed_warning", "")
            or sect.get("boxed_warning", ""),
            "warnings": sect.get("warnings", ""),
            "drug_interactions": sect.get("drug_interactions", ""),
            "label_source": card.get("source", "offline-fallback"),
            "label_brand": card.get("brand", ""),
        }
        if sect.get("source", "offline-fallback") != "offline-fallback":
            sections["label_source"] = sect.get("source", "")
    out = screen_concomitant(sections, body.meds)
    if sections.get("label_source") and "label_source" not in out:
        out["label_source"] = sections["label_source"]
    return out


class EscalationRequest(BaseModel):
    aging: dict[str, Any] = {}


@router.post("/api/escalation-chains")
def escalation_chains_endpoint(body: EscalationRequest) -> dict[str, Any]:
    from backend.agents.pv_tools import escalation_chains

    return escalation_chains(body.aging)


class PromoCheckRequest(BaseModel):
    draft: str = ""
    indication: str = ""


@router.post("/api/promo-check")
def promo_check_endpoint(body: PromoCheckRequest) -> dict[str, Any]:
    from backend.agents.warning_letters import check_promo_draft

    if not body.draft.strip():
        raise HTTPException(status_code=422, detail="draft is required")
    return check_promo_draft(body.draft, body.indication)


class VisitReportRequest(BaseModel):
    findings: list[dict[str, Any]] = []
    site_tier: dict[str, Any] = {}


@router.post("/api/visit-report")
def visit_report_endpoint(body: VisitReportRequest) -> dict[str, Any]:
    from backend.agents.ops_tools import visit_report

    return visit_report(body.findings, body.site_tier or None)


class CodeDeviationRequest(BaseModel):
    deviation_type: str = ""
    detail: str = ""


@router.post("/api/code-deviation")
def code_deviation_endpoint(body: CodeDeviationRequest) -> dict[str, Any]:
    from backend.agents.ops_tools import code_deviation

    return code_deviation(body.deviation_type, body.detail)


class FiveWhysRequest(BaseModel):
    deviation_type: str = ""
    detail: str = ""


@router.post("/api/five-whys")
def five_whys_endpoint(body: FiveWhysRequest) -> dict[str, Any]:
    from backend.agents.ops_tools import five_whys

    return five_whys(body.deviation_type, body.detail)


class BudgetRequest(BaseModel):
    spec: dict[str, Any] = {}


@router.post("/api/budget")
def budget_endpoint(body: BudgetRequest) -> dict[str, Any]:
    from backend.agents.ops_tools import budget_estimate

    try:
        return budget_estimate(body.spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class InspectionRequest(BaseModel):
    protocol_id: str = ""
    n_deviations: int = 0
    open_items: list[str] = []


@router.post("/api/inspection-pack")
def inspection_pack_endpoint(body: InspectionRequest) -> dict[str, Any]:
    from backend.agents.ops_tools import inspection_pack

    init_db()
    protocol = get_protocol(body.protocol_id) or {"id": body.protocol_id}
    queries = list_safety_queries(body.protocol_id)
    counts = {
        "deviations": max(0, body.n_deviations),
        "queries": len(queries),
        "overdue": sum(
            1
            for q in queries
            if str(q.get("resolution_status", "")).upper() != "RESOLVED"
        ),
        "sae": sum(1 for q in queries if q.get("is_sae")),
    }
    return inspection_pack(protocol, counts, body.open_items)


class DsmbRequest(BaseModel):
    protocol_id: str = ""


@router.post("/api/dsmb-pack")
def dsmb_pack_endpoint(body: DsmbRequest) -> dict[str, Any]:
    from backend.agents.ops_tools import dsmb_pack

    if not body.protocol_id.strip():
        raise HTTPException(status_code=422, detail="protocol_id is required")
    init_db()
    protocol = get_protocol(body.protocol_id) or {"id": body.protocol_id}
    queries = list_safety_queries(body.protocol_id)
    evaluations = list_patient_evaluations(body.protocol_id)
    eval_counts: dict[str, int] = {}
    for e in evaluations:
        if isinstance(e, dict):
            s = str(e.get("eligibility_status", "?"))
            eval_counts[s] = eval_counts.get(s, 0) + 1
    query_counts = {
        "total": len(queries),
        "open": sum(
            1
            for q in queries
            if str(q.get("resolution_status", "")).upper() != "RESOLVED"
        ),
        "sae": sum(1 for q in queries if q.get("is_sae")),
    }
    return dsmb_pack(
        protocol, list_startup(), query_counts, eval_counts, query_counts["sae"]
    )


@router.get("/api/portfolio")
def portfolio_endpoint() -> dict[str, Any]:
    init_db()
    rows = []
    for p in list_protocols():
        pid = p.get("id", "?")
        queries = list_safety_queries(pid)
        evaluations = list_patient_evaluations(pid)
        rows.append(
            {
                "protocol_id": pid,
                "title": p.get("title", ""),
                "phase": p.get("phase", ""),
                "indication": p.get("indication", ""),
                "queries": len(queries),
                "open_queries": sum(
                    1
                    for q in queries
                    if str(q.get("resolution_status", "")).upper() != "RESOLVED"
                ),
                "evaluations": len(evaluations),
            }
        )
    return {
        "protocols": sorted(rows, key=lambda r: str(r["protocol_id"])),
        "n_protocols": len(rows),
    }


class CompetitionRequest(BaseModel):
    threshold: int = 20
    country: str = "United States"


@router.post("/api/competition-alerts")
def competition_alerts_endpoint(body: CompetitionRequest) -> dict[str, Any]:
    from backend.agents.site_scout import fetch_ctgov_competitors

    init_db()
    alerts = []
    for p in list_protocols():
        indication = str(p.get("indication", "") or "")
        if not indication:
            continue
        try:
            got = fetch_ctgov_competitors(indication, body.country)
        except Exception:
            got = {"count": 0, "source": "offline-fallback"}
        count = int(got.get("count", 0) or 0)
        if count >= max(1, body.threshold):
            alerts.append(
                {
                    "protocol_id": p.get("id", "?"),
                    "indication": indication,
                    "recruiting_competitors": count,
                    "source": got.get("source", "?"),
                }
            )
    alerts.sort(key=lambda a: -a["recruiting_competitors"])
    return {
        "alerts": alerts,
        "threshold": body.threshold,
        "country": body.country,
        "basis": "Live CT.gov recruiting counts per indication.",
    }


class TrialArtifactRequest(BaseModel):
    trial: dict[str, Any] = {}
    description: str = ""
    patient_label: str = "the patient"


@router.post("/api/trial-referral")
def trial_referral(body: TrialArtifactRequest) -> dict[str, Any]:
    """Plain-text referral packet for one matched trial."""
    if not body.trial.get("nct_id"):
        raise HTTPException(status_code=422, detail="trial with nct_id required")
    return referral_letter(body.trial, body.description, body.patient_label)


@router.post("/api/trial-questions")
def trial_questions(body: TrialArtifactRequest) -> dict[str, Any]:
    """Yes/No/Unknown screening checklist from the trial's own criteria."""
    if not body.trial.get("nct_id"):
        raise HTTPException(status_code=422, detail="trial with nct_id required")
    return screening_questions(body.trial)


class ExternalControlRequest(BaseModel):
    protocol_id: str
    relax_ids: list[str] = []
    bundles: list[dict[str, Any]] | None = None


@router.post("/api/external-control")
def external_control(body: ExternalControlRequest) -> dict[str, Any]:
    init_db()
    crit = audited_criteria(body.protocol_id)
    bundles = body.bundles
    if not bundles:
        bundles = (
            [json.loads(p.read_text()) for p in sorted(FHIR_DIR.glob("*.json"))]
            if FHIR_DIR.exists()
            else []
        )
    return build_external_control(crit, bundles, body.relax_ids)


class RetentionRequest(BaseModel):
    protocol_id: str
    bundle: dict[str, Any]


@router.get("/api/forensics")
def forensics(protocol_id: str | None = None) -> dict[str, Any]:
    init_db()
    evals = []
    for r in list_patient_evaluations(protocol_id):
        raw = r.get("rationale")
        try:
            evals.append(json.loads(raw) if isinstance(raw, str) else raw)
        except (TypeError, ValueError):
            continue
    return forensic_report([e for e in evals if isinstance(e, dict)])


@router.post("/api/retention")
def retention_endpoint(body: RetentionRequest) -> dict[str, Any]:
    init_db()
    proto = get_protocol(body.protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return retention_risk(score_burden(proto["raw_content"]), body.bundle)


@router.get("/api/attrition/{protocol_id}")
def attrition_endpoint(protocol_id: str) -> dict[str, Any]:
    init_db()
    proto = get_protocol(protocol_id)
    if not proto:
        raise HTTPException(status_code=404, detail="Protocol not found")
    burden = score_burden(proto["raw_content"])
    sae_n = sum(1 for q in list_safety_queries(protocol_id) if q.get("is_sae"))
    return predict_attrition(burden, dct_readiness(burden, proto["raw_content"]), sae_n)


@router.get("/api/outcome-benchmark")
def outcome_benchmark(condition: str, phase: str = "") -> dict[str, Any]:
    if not condition.strip():
        raise HTTPException(status_code=400, detail="condition is required")
    try:
        return fetch_ctgov_outcomes(condition.strip(), phase.strip())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"registry lookup failed: {exc}")


@router.get("/api/clinvar")
def clinvar_lookup(gene: str, retmax: int = 3) -> dict[str, Any]:
    if not gene.strip():
        raise HTTPException(status_code=400, detail="gene is required")
    return fetch_clinvar(gene.strip(), retmax)


class DeviationRequest(BaseModel):
    records: list[dict[str, Any]]
    window_days: int = 3


@router.post("/api/deviation-watch")
def deviation_watch_endpoint(body: DeviationRequest) -> dict[str, Any]:
    if not body.records:
        raise HTTPException(status_code=400, detail="records is required")
    return watch_deviations(body.records, body.window_days)


class QueryAgingUpload(BaseModel):
    records: list[dict[str, Any]]


@router.post("/api/query-aging")
def query_aging_upload(body: QueryAgingUpload) -> dict[str, Any]:
    return query_aging(body.records)


@router.get("/api/pubmed")
def pubmed_lookup(term: str, retmax: int = 5) -> dict[str, Any]:
    if not term.strip():
        raise HTTPException(status_code=400, detail="term is required")
    return fetch_pubmed(term.strip(), retmax)


class SignalRequest(BaseModel):
    records: list[dict[str, Any]]


@router.post("/api/safety-signals")
def safety_signals(body: SignalRequest) -> dict[str, Any]:
    if not body.records:
        raise HTTPException(status_code=400, detail="records is required")
    triaged = triage_records(body.records)["triaged_records"]
    attach_rxnorm(triaged)
    return detect_signals(triaged)


class E2BRequest(BaseModel):
    record: dict[str, Any] = {}


@router.post("/api/e2b")
def e2b_export(body: E2BRequest) -> dict[str, Any]:
    """One triaged record -> E2B(R3)-shaped ICSR XML (core elements)."""
    from backend.agents.pv_tools import e2b_xml

    if not body.record:
        raise HTTPException(status_code=400, detail="record is required")
    return e2b_xml(body.record)


@router.get("/api/dsur/{protocol_id}")
def dsur_shell_endpoint(protocol_id: str) -> dict[str, Any]:
    """DSUR-shaped shell compiled from the database; prose marked [FILL]."""
    from backend.agents.pv_tools import dsur_shell

    init_db()
    protocol = get_protocol(protocol_id) or {"id": protocol_id, "title": ""}
    queries = list_safety_queries(protocol_id)
    evaluations = list_patient_evaluations(protocol_id)
    return dsur_shell(protocol, queries, evaluations)


class RiskRegisterRequest(BaseModel):
    signals: list[dict[str, Any]] = []
    deviations_note: str = ""


@router.post("/api/risk-register")
def risk_register_endpoint(body: RiskRegisterRequest) -> dict[str, Any]:
    """Ranked risk list from signal rows with owner + mitigation."""
    from backend.agents.pv_tools import build_risk_register

    return build_risk_register(body.signals, body.deviations_note)


class SignalReviewRequest(BaseModel):
    signals: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []


@router.post("/api/signal-review")
def signal_review_endpoint(body: SignalReviewRequest) -> dict[str, Any]:
    """Reviewer dispositions over signal rows, with an audit trail."""
    from backend.agents.pv_tools import review_signals

    return review_signals(body.signals, body.decisions)
