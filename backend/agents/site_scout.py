"""Agent 2 - Site Feasibility Scout. Deterministic scoring, no network required.

Optional live ClinicalTrials.gov lookup ships with disk cache + offline
fallback; scoring itself is pure arithmetic. Stdlib only unless the optional
lookup is invoked (uses httpx, a core dep).
"""

from __future__ import annotations

import json
from typing import Any

from backend.config import CTGV_CACHE, CTGV_CACHE_MAX_ENTRIES

CACHE = CTGV_CACHE

REGULATORY_EFFICIENCY = {
    "tier 1": 92.0,
    "tier1": 92.0,
    "fast": 92.0,
    "tier 2": 76.0,
    "tier2": 76.0,
    "standard": 76.0,
    "tier 3": 58.0,
    "tier3": 58.0,
    "slow": 58.0,
}


def _read_cache() -> dict[str, Any]:
    try:
        if CACHE.exists():
            data = json.loads(CACHE.read_text())
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def _write_cache(cache: dict[str, Any]) -> None:
    while len(cache) > CTGV_CACHE_MAX_ENTRIES:  # forget oldest lookups first
        cache.pop(next(iter(cache)))
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache))
    except OSError:
        pass


def fetch_ctgov_competitors(
    condition: str, country: str, timeout: float = 8.0
) -> dict[str, Any]:
    """Count recruiting CT.gov studies; cached, with offline fallback."""
    key = f"{condition.lower()}|{country.lower()}"
    cache = _read_cache()
    if key in cache and isinstance(cache[key], int):
        return {"count": cache[key], "source": "cache"}
    try:
        import httpx  # core dep, imported lazily

        res = httpx.get(
            "https://clinicaltrials.gov/api/v2/studies",
            params={
                "query.cond": condition,
                "query.locn": country,
                "filter.overallStatus": "RECRUITING",
                "pageSize": 1,
                "countTotal": "true",
            },
            timeout=timeout,
        )
        res.raise_for_status()
        count = int(res.json().get("totalCount", 0))
        cache[key] = count
        _write_cache(cache)
        return {"count": count, "source": "live"}
    except Exception:
        hit = cache.get(key)
        return {
            "count": hit if isinstance(hit, int) else 0,
            "source": "offline-fallback",
        }


def fetch_ctgov_outcomes(
    condition: str, phase: str = "", timeout: float = 10.0
) -> dict[str, Any]:
    """Benchmark completed trials: counts, results rate, enrollment, outcomes."""
    key = f"outcomes|{condition.lower()}|{phase.lower()}"
    cache = _read_cache()
    if key in cache and isinstance(cache[key], dict):
        out = dict(cache[key])
        out["source"] = "cache"
        return out
    blank = {
        "n_completed": 0,
        "sampled_n": 0,
        "with_results": 0,
        "with_results_pct": 0.0,
        "median_enrollment": 0,
        "top_outcomes": [],
        "source": "offline-fallback",
        "condition": condition,
        "phase": phase or "any",
    }
    try:
        import httpx  # core dep, imported lazily

        params: dict[str, Any] = {
            "query.cond": condition,
            "filter.overallStatus": "COMPLETED",
            "pageSize": 25,
            "countTotal": "true",
        }
        if phase.strip():
            params["filter.advanced"] = f"AREA[Phase]{phase.strip()}"
        res = httpx.get(
            "https://clinicaltrials.gov/api/v2/studies", params=params, timeout=timeout
        )
        res.raise_for_status()
        data = res.json()
        studies = data.get("studies", []) or []
        total = int(data.get("totalCount", len(studies)))
        enroll: list[int] = []
        outcomes: dict[str, int] = {}
        with_res = 0
        for s in studies:
            proto = s.get("protocolSection", {}) or {}
            design = proto.get("designModule", {}) or {}
            n = (design.get("enrollmentInfo", {}) or {}).get("count")
            if isinstance(n, int) and n > 0:
                enroll.append(n)
            mods = (proto.get("outcomesModule", {}) or {}).get(
                "primaryOutcomes", []
            ) or []
            for o in mods:
                m = str(o.get("measure") or "").strip()
                if m:
                    outcomes[m] = outcomes.get(m, 0) + 1
            res_sec = s.get("resultsSection", {}) or {}
            if res_sec.get("firstPostDateStruct") or s.get("hasResults"):
                with_res += 1
        enroll.sort()
        top = sorted(outcomes.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        out = {
            "n_completed": total,
            "sampled_n": len(studies),
            "with_results": with_res,
            "with_results_pct": round(100.0 * with_res / max(1, len(studies)), 1),
            "median_enrollment": enroll[len(enroll) // 2] if enroll else 0,
            "top_outcomes": [{"measure": m, "n": c} for m, c in top],
            "source": "live",
            "condition": condition,
            "phase": phase or "any",
        }
        cache[key] = {k: v for k, v in out.items() if k != "source"}
        _write_cache(cache)
        return out
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            out = dict(hit)
            out["source"] = "cache"
            return out
        return blank


def _velocity_score(accrual_per_month: float) -> float:
    return max(0.0, min(100.0, accrual_per_month / 4.0 * 100.0))


def score_site(
    site: dict[str, Any], competitors: int = 0, competitor_source: str = "manual"
) -> dict[str, Any]:
    """Score one site. Weights: velocity 35 / competition 25 / regulatory 20 / capacity 20."""
    velocity = _velocity_score(float(site.get("past_accrual_per_month", 0) or 0))
    comp = competitors or int(site.get("active_competing_trials", 0) or 0)
    penalty = min(60.0, comp * 6.0)
    tier = str(site.get("regulatory_tier", "standard")).lower()
    regulatory = REGULATORY_EFFICIENCY.get(tier, 70.0)
    activation = site.get("historical_activation_days")
    if activation:
        regulatory = max(
            0.0, min(100.0, regulatory - max(0.0, (float(activation) - 60.0) * 0.3))
        )
    capacity = float(site.get("staff_capacity_score", 70.0) or 70.0)
    feasibility = round(
        0.35 * velocity
        + 0.25 * (100.0 - penalty)
        + 0.20 * regulatory
        + 0.20 * capacity,
        1,
    )
    if feasibility >= 75:
        rec = "GO"
    elif feasibility >= 55:
        rec = "CONDITIONAL"
    else:
        rec = "NO-GO"
    accrual = round(
        float(site.get("past_accrual_per_month", 0) or 0) * (0.5 + capacity / 200.0), 2
    )
    risks: list[str] = []
    mitigations: list[str] = []
    if comp >= 5:
        risks.append(f"High competition: {comp} recruiting trials nearby.")
        mitigations.append("Expand referral network; consider satellite sites.")
    if activation and float(activation) > 120:
        risks.append(f"Slow activation history ({activation} days).")
        mitigations.append("Pre-submit regulatory package; parallel ethics review.")
    if velocity < 40:
        risks.append("Low historical accrual velocity.")
        mitigations.append("Dedicated recruitment coordinator; prescreening list.")
    return {
        "site_id": site.get("id", site.get("site_id", "UNKNOWN")),
        "site_name": site.get("name", site.get("site_name", "Unknown site")),
        "country": site.get("country", "Unknown"),
        "competitors_used": comp,
        "competitor_source": competitor_source,
        "feasibility_score": feasibility,
        "recommendation": rec,
        "projected_monthly_accrual_rate": accrual,
        "scoring_breakdown": {
            "velocity_score": round(velocity, 1),
            "competition_penalty": round(penalty, 1),
            "regulatory_efficiency": round(regulatory, 1),
            "capacity_score": round(capacity, 1),
        },
        "identified_risks": risks,
        "mitigation_strategies": mitigations,
    }


def score_sites(
    sites: list[dict[str, Any]],
    target_enrollment: int = 0,
    competitors_by_site: dict[str, int] | None = None,
    competitor_sources: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Score a portfolio of sites; matches the cookbook JSON contract."""
    competitors_by_site = competitors_by_site or {}
    competitor_sources = competitor_sources or {}
    evaluated = [
        score_site(
            s,
            competitors_by_site.get(str(s.get("id", "")), 0),
            competitor_sources.get(str(s.get("id", "")), "manual"),
        )
        for s in sites
    ]
    selected = [s for s in evaluated if s["recommendation"] in ("GO", "CONDITIONAL")]
    total_accrual = sum(s["projected_monthly_accrual_rate"] for s in selected)
    timeline = round(target_enrollment / total_accrual, 1) if total_accrual > 0 else 0.0
    return {
        "evaluated_sites": evaluated,
        "portfolio_summary": {
            "total_sites_analyzed": len(evaluated),
            "selected_sites_count": len(selected),
            "projected_timeline_to_lpi_months": timeline,
        },
    }
