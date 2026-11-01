"""Query aging + database-lock readiness. Deterministic, stdlib only.

CDM close-out math: every stored safety query lands in an age bucket
(0-7 / 8-30 / 31-60 / 61-90 / 90+ days) and the lock checklist goes
RAG: open queries, open SAEs, and stale queries (>30d) must all clear
before lock. Resolution flows through the resolve endpoint; ages are
computed against an injectable `today` so tests never depend on the
wall clock.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

BUCKETS = ("0-7", "8-30", "31-60", "61-90", "90+")


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
