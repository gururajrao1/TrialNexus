"""Centralized monitoring lite: KRIs + alerts per site. Deterministic, stdlib only.

Implements the ICH E6(R3) idea in miniature: pre-specified thresholds
(quality tolerance limits) evaluated centrally across sites, so monitors
visit the sites that need it instead of verifying everything on-site.
An SDV-style visit is recommended only for alert-level sites.
"""

from __future__ import annotations

from typing import Any

THRESHOLDS = {
    "screen_failure_pct": {"watch": 30.0, "alert": 40.0},
    "queries_per_patient": {"watch": 2.0, "alert": 3.0},
    "deviations_month": {"watch": 2, "alert": 4},
    "sae_month": {"watch": 1, "alert": 2},
    "enrollment_gap_pct": {"watch": 20.0, "alert": 40.0},
}
DEFAULT_TARGETS = {"SITE-001": 3, "SITE-002": 3, "SITE-003": 3}


def _level(value: float, kri: str) -> str:
    t = THRESHOLDS[kri]
    if value >= t["alert"]:
        return "alert"
    if value >= t["watch"]:
        return "watch"
    return "ok"


def zero_enroll_risk(rows: list[dict[str, Any]], monthly_target: int) -> dict[str, Any]:
    """Transparent zero-enrollment scorecard (ZS/Medidata-style behavior flag).

    Scores P(trouble ahead) from zero-months, latest gap vs target, and a
    declining run-rate — the observable half of site-behavior prediction.
    Bands: low < 30, elevated < 60, high >= 60.
    """
    enrolled = [int(r.get("enrolled", 0) or 0) for r in rows]
    n = len(enrolled)
    zero_months = sum(1 for e in enrolled if e == 0)
    last = enrolled[-1] if enrolled else 0
    gap_pct = 100.0 * max(0, monthly_target - last) / max(1, monthly_target)
    first_avg = sum(enrolled[: max(1, n // 2)]) / max(1, n // 2) if enrolled else 0
    declining = bool(enrolled) and last < first_avg
    score = min(
        100,
        round(zero_months * 20 + min(40.0, gap_pct * 0.4) + (20 if declining else 0)),
    )
    band = "low" if score < 30 else ("elevated" if score < 60 else "high")
    factors = [
        f"{zero_months}/{n} zero-enrollment months",
        f"latest gap {gap_pct:.0f}% vs target {monthly_target}",
        "run-rate declining" if declining else "run-rate stable",
    ]
    return {"score": score, "band": band, "factors": factors}


def site_kris(rows: list[dict[str, Any]], monthly_target: int) -> dict[str, Any]:
    """Compute KRIs for one site from its monthly metric rows (oldest first)."""
    latest = rows[-1] if rows else {}
    screened = max(1, int(latest.get("screened", 0) or 0))
    enrolled = int(latest.get("enrolled", 0) or 0)
    fails = screened - enrolled
    kris = [
        {
            "kri": "screen_failure_pct",
            "value": round(100.0 * fails / screened, 1),
            "detail": f"{fails}/{screened} screened failed",
        },
        {
            "kri": "queries_per_patient",
            "value": round(float(latest.get("open_queries", 0) or 0) / screened, 2),
            "detail": f"{latest.get('open_queries', 0)} open queries",
        },
        {
            "kri": "deviations_month",
            "value": int(latest.get("deviations", 0) or 0),
            "detail": f"in {latest.get('month', '?')}",
        },
        {
            "kri": "sae_month",
            "value": int(latest.get("sae", 0) or 0),
            "detail": f"in {latest.get('month', '?')}",
        },
        {
            "kri": "enrollment_gap_pct",
            "value": round(
                100.0 * max(0, monthly_target - enrolled) / max(1, monthly_target), 1
            ),
            "detail": f"{enrolled}/{monthly_target} enrolled",
        },
    ]
    for k in kris:
        k["status"] = _level(float(k["value"]), k["kri"])
    worst = "ok"
    for k in kris:
        if k["status"] == "alert":
            worst = "alert"
        elif k["status"] == "watch" and worst == "ok":
            worst = "watch"
    alerts = [
        f"{k['kri']} = {k['value']} ({k['detail']})"
        for k in kris
        if k["status"] == "alert"
    ]
    return {
        "kris": kris,
        "worst": worst,
        "alerts": alerts,
        "action": "Schedule targeted monitoring visit"
        if worst == "alert"
        else ("Remote check-in advised" if worst == "watch" else "No action"),
        "zero_enroll": zero_enroll_risk(rows, monthly_target),
    }


def portfolio_kris(
    rows_by_site: dict[str, list[dict[str, Any]]],
    targets: dict[str, int] | None = None,
) -> dict[str, Any]:
    """KRIs for every site plus the portfolio alert list."""
    targets = targets or DEFAULT_TARGETS
    sites = []
    for sid in sorted(rows_by_site):
        r = site_kris(rows_by_site[sid], targets.get(sid, 3))
        sites.append({"site_id": sid, **r})
    return {
        "sites": sites,
        "alert_site_ids": sorted(s["site_id"] for s in sites if s["worst"] == "alert"),
        "thresholds": THRESHOLDS,
        "note": (
            "Thresholds encode industry tolerance limits (screen fail 30/40%, "
            "queries/pt 2/3, deviations 2/4, SAE 1/2, enrollment gap 20/40%)."
        ),
    }
