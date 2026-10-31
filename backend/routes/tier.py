"""Tier 1+2 routes: trial outlook, enrollment forecast, synthetic twins,
mCODE summary, n2c2 validity."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.burden_scorer import score_burden
from backend.agents.enrollment_forecast import forecast
from backend.agents.mcode import mcode_profile
from backend.agents.n2c2_harness import CRITERIA, load_fixture, micro_f1
from backend.agents.protocol_auditor import parse_protocol
from backend.agents.risk_models import outlook
from backend.agents.twin_generator import twin_distribution
from backend.config import FHIR_DIR, N2C2_DATA_DIR
from backend.database import get_protocol, init_db, save_protocol_audit
from backend.routes.core import audited_criteria

router = APIRouter()


class ForecastRequest(BaseModel):
    sites: list[dict[str, Any]]
    target_enrollment: int
    enrolled_so_far: int = 0
    deadline_months: float | None = None
    seed: int = 42


class TwinsRequest(BaseModel):
    protocol_id: str
    bundle: dict[str, Any] | None = None
    bundle_id: str | None = None
    n: int = 100
    seed: int = 7


class McodeRequest(BaseModel):
    bundle: dict[str, Any]


@router.get("/api/trial-outlook/{protocol_id}")
def trial_outlook(protocol_id: str) -> dict[str, Any]:
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
    return outlook(audit, score_burden(proto["raw_content"]))


@router.post("/api/forecast")
def forecast_endpoint(body: ForecastRequest) -> dict[str, Any]:
    return forecast(
        body.sites,
        body.target_enrollment,
        body.enrolled_so_far,
        body.deadline_months,
        seed=body.seed,
    )


@router.post("/api/twins")
def twins_endpoint(body: TwinsRequest) -> dict[str, Any]:
    init_db()
    bundle = body.bundle
    if bundle is None and body.bundle_id:
        p = FHIR_DIR / f"{body.bundle_id}.json"
        if not p.exists():
            raise HTTPException(status_code=404, detail="Bundle not found")
        bundle = json.loads(p.read_text())
    if bundle is None:
        raise HTTPException(status_code=400, detail="Provide bundle or bundle_id")
    return twin_distribution(
        audited_criteria(body.protocol_id), bundle, body.n, body.seed
    )


@router.post("/api/mcode")
def mcode_endpoint(body: McodeRequest) -> dict[str, Any]:
    return mcode_profile(body.bundle)


@router.get("/api/n2c2-status")
def n2c2_status() -> dict[str, Any]:
    present = N2C2_DATA_DIR.exists() and any(N2C2_DATA_DIR.glob("*.txt"))
    return {
        "fixture_f1": micro_f1(load_fixture())["micro_f1"],
        "real_data_present": present,
        "criteria": list(CRITERIA),
        "instructions": (
            "Request n2c2 2018 cohort-selection data via the n2c2/Harvard DBMI "
            "data-use agreement, then place {id}.txt notes + labels.csv under "
            "data/n2c2/ and run: python -m backend.agents.n2c2_harness data/n2c2"
        ),
    }
