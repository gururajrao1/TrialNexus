"""Study-startup tracker: activation pipeline + bottleneck flags. Stdlib only.

Benchmarks (industry): ~7-8 months site ID to activation (Tufts), ~$25K
wasted per stalled pre-activation site, ~90-day CTA negotiation, central
IRB ~27d vs local ~66d. Flags fire when a site exceeds them. Pure
functions over database rows; persistence lives in backend/database.py.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

STAGES = ("identified", "feasibility", "contract", "irb", "activated", "fpi")
BENCHMARKS = {"contract_days": 90, "irb_days": 45, "activation_days": 240}


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def startup_report(
    rows: list[dict[str, Any]],
    sites: list[dict[str, Any]],
    today: str | date | None = None,
) -> dict[str, Any]:
    """Assemble per-site pipeline state plus bottleneck flags."""
    now = _as_date(today) if today else date.today()
    sitemap = {s["id"]: s for s in sites}
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            hist = json.loads(r.get("history") or "[]")
        except ValueError:
            hist = []
        last = (
            hist[-1]["date"] if hist else (r.get("updated_at") or now.isoformat())[:10]
        )
        first = hist[0]["date"] if hist else last
        days_stage = (now - _as_date(last)).days
        days_total = (now - _as_date(first)).days
        stage = r.get("stage", "identified")
        flags: list[str] = []
        if stage == "contract" and days_stage > BENCHMARKS["contract_days"]:
            flags.append(f"CTA negotiation {days_stage}d exceeds ~90-day benchmark")
        if stage == "irb" and days_stage > BENCHMARKS["irb_days"]:
            flags.append(f"IRB review {days_stage}d exceeds ~45-day benchmark")
        if (
            stage not in ("activated", "fpi")
            and days_total > BENCHMARKS["activation_days"]
        ):
            flags.append(
                f"{days_total}d since identification exceeds ~8-month benchmark; "
                "~$25K startup spend at risk"
            )
        site = sitemap.get(r["site_id"], {})
        out.append(
            {
                "site_id": r["site_id"],
                "site_name": site.get("name", r["site_id"]),
                "country": site.get("country", "Unknown"),
                "stage": stage,
                "days_in_stage": days_stage,
                "days_since_identified": days_total,
                "flags": flags,
                "history": hist,
                "notes": r.get("notes", ""),
            }
        )
    counts = {s: sum(1 for r in out if r["stage"] == s) for s in STAGES}
    return {
        "as_of": now.isoformat(),
        "sites": sorted(out, key=lambda s: s["site_id"]),
        "stage_counts": counts,
        "flagged_site_ids": sorted(s["site_id"] for s in out if s["flags"]),
        "benchmarks": BENCHMARKS,
    }
