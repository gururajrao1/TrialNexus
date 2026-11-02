"""Query aging + database-lock readiness. Deterministic, stdlib only.

CDM close-out math: every stored safety query lands in an age bucket
(0-7 / 8-30 / 31-60 / 61-90 / 90+ days) and the lock checklist goes
RAG: open queries, open SAEs, and stale queries (>30d) must all clear
before lock. Resolution flows through the resolve endpoint; ages are
computed against an injectable `today` so tests never depend on the
wall clock.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

BUCKETS = ("0-7", "8-30", "31-60", "61-90", "90+")

# Query routing policy: SAE queries go to drug safety on a 7-day SLA
# (expedited-reporting clock); everything else goes to the site
# coordinator on a 30-day SLA (the stale-query threshold). Deterministic
# and documented here so the escalation list is auditable.
SAE_OWNER, SAE_SLA_DAYS = "drug safety", 7
ROUTINE_OWNER, ROUTINE_SLA_DAYS = "site coordinator", 30


def _age_days(created: str, today: date) -> int:
    try:
        day = datetime.strptime(created[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0
    return max(0, (today - day).days)


def _bucket(days: int) -> str:
    if days <= 7:
        return "0-7"
    if days <= 30:
        return "8-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def lock_readiness(
    queries: list[dict[str, Any]], today: date | None = None
) -> dict[str, Any]:
    """Age buckets + RAG lock checklist over stored safety queries."""
    today = today or date.today()
    buckets = {b: 0 for b in BUCKETS}
    open_q = [q for q in queries if (q.get("resolution_status") or "") != "RESOLVED"]
    for q in open_q:
        buckets[_bucket(_age_days(str(q.get("created_at", "")), today))] += 1
    open_sae = [q for q in open_q if q.get("is_sae")]
    stale = [q for q in open_q if _age_days(str(q.get("created_at", "")), today) > 30]
    checks = [
        {
            "item": "No open queries",
            "status": "green" if not open_q else ("amber" if not stale else "red"),
            "detail": f"{len(open_q)} open",
        },
        {
            "item": "No open SAE queries",
            "status": "green" if not open_sae else "red",
            "detail": f"{len(open_sae)} open SAE",
        },
        {
            "item": "No queries older than 30 days",
            "status": "green" if not stale else "red",
            "detail": f"{len(stale)} stale",
        },
    ]
    overall = (
        "red"
        if any(c["status"] == "red" for c in checks)
        else ("amber" if any(c["status"] == "amber" for c in checks) else "green")
    )
    return {
        "buckets": buckets,
        "n_open": len(open_q),
        "n_resolved": len(queries) - len(open_q),
        "checks": checks,
        "overall": overall,
        "stale_ids": [str(q.get("id", "?")) for q in stale[:20]],
        "basis": (
            "CDM close-out rule: queries age past 30/60/90 days, SAEs "
            "reconcile to resolved, and lock waits for green."
        ),
    }


def _route(query: dict[str, Any]) -> tuple[str, int]:
    """Owner + SLA days for one query, per the routing policy above."""
    if query.get("is_sae"):
        return SAE_OWNER, SAE_SLA_DAYS
    return ROUTINE_OWNER, ROUTINE_SLA_DAYS


def _escalation(days_overdue: int) -> str:
    if days_overdue > 60:
        return "critical"
    if days_overdue > 30:
        return "escalate"
    if days_overdue > 0:
        return "overdue"
    return "on-track"


def _due_date(created: str, sla_days: int) -> str | None:
    try:
        day = datetime.strptime(created[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
    return (day + timedelta(days=sla_days)).isoformat()


def query_aging(
    queries: list[dict[str, Any]], today: date | None = None
) -> dict[str, Any]:
    """Owner-routed query aging: due dates, SLA breaches, escalation list."""
    today = today or date.today()
    rows = []
    for q in queries:
        if (q.get("resolution_status") or "") == "RESOLVED":
            continue
        created = str(q.get("created_at", ""))
        age = _age_days(created, today)
        owner, sla = _route(q)
        overdue = max(0, age - sla)
        rows.append(
            {
                "id": str(q.get("id", "?")),
                "age_days": age,
                "bucket": _bucket(age),
                "owner": owner,
                "sla_days": sla,
                "due_date": _due_date(created, sla),
                "days_overdue": overdue,
                "escalation": _escalation(overdue),
            }
        )
    owners = sorted({r["owner"] for r in rows})
    matrix = {o: {b: 0 for b in BUCKETS} for o in owners}
    for r in rows:
        matrix[r["owner"]][r["bucket"]] += 1
    escalated = sorted(
        (r for r in rows if r["days_overdue"] > 0),
        key=lambda r: (-r["days_overdue"], r["id"]),
    )
    return {
        "rows": rows,
        "owner_matrix": matrix,
        "escalation_list": escalated,
        "n_open": len(rows),
        "n_overdue": len(escalated),
        "basis": (
            "Routing policy: SAE queries to drug safety (7d SLA), "
            "routine queries to site coordinator (30d SLA). "
            "Overdue past 30d escalates, past 60d is critical."
        ),
    }
