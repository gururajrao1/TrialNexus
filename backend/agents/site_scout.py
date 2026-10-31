"""Agent 2 - Site Feasibility Scout. Deterministic scoring, no network required.

Optional live ClinicalTrials.gov lookup ships with disk cache + offline
fallback; scoring itself is pure arithmetic. Stdlib only unless the optional
lookup is invoked (uses httpx, a core dep).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

CACHE = Path(__file__).resolve().parent.parent.parent / "data" / "outputs" / "ctgov_cache.json"

REGULATORY_EFFICIENCY = {
    "tier 1": 92.0, "tier1": 92.0, "fast": 92.0,
    "tier 2": 76.0, "tier2": 76.0, "standard": 76.0,
    "tier 3": 58.0, "tier3": 58.0, "slow": 58.0,
}


def fetch_ctgov_competitors(
    condition: str, country: str, timeout: float = 8.0
) -> Dict[str, Any]:
    """Count recruiting CT.gov studies; cached, with offline fallback."""
    key = f"{condition.lower()}|{country.lower()}"
    cache: Dict[str, int] = {}
    try:
        if CACHE.exists():
            cache = json.loads(CACHE.read_text())
        if key in cache:
            return {"count": cache[key], "source": "cache"}
    except (OSError, ValueError):
        cache = {}
    try:
        import httpx  # core dep, imported lazily

        res = httpx.get(
            "https://clinicaltrials.gov/api/v2/studies",
            params={"query.cond": condition, "query.locn": country,
                    "filter.overallStatus": "RECRUITING",
                    "pageSize": 1, "countTotal": "true"},
            timeout=timeout,
        )
        res.raise_for_status()
        count = int(res.json().get("totalCount", 0))
        cache[key] = count
        while len(cache) > 200:  # storage cap: forget oldest lookups first
            cache.pop(next(iter(cache)))
        try:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache))
        except OSError:
            pass
        return {"count": count, "source": "live"}
    except Exception:
        return {"count": cache.get(key, 0), "source": "offline-fallback"}


def _velocity_score(accrual_per_month: float) -> float:
    return max(0.0, min(100.0, accrual_per_month / 4.0 * 100.0))


def score_site(site: Dict[str, Any], competitors: int = 0,
               competitor_source: str = "manual") -> Dict[str, Any]:
    """Score one site. Weights: velocity 35 / competition 25 / regulatory 20 / capacity 20."""
    velocity = _velocity_score(float(site.get("past_accrual_per_month", 0) or 0))
    comp = competitors or int(site.get("active_competing_trials", 0) or 0)
    penalty = min(60.0, comp * 6.0)
    tier = str(site.get("regulatory_tier", "standard")).lower()
    regulatory = REGULATORY_EFFICIENCY.get(tier, 70.0)
    activation = site.get("historical_activation_days")
    if activation:
        regulatory = max(0.0, min(100.0, regulatory - max(0.0, (float(activation) - 60.0) * 0.3)))
    capacity = float(site.get("staff_capacity_score", 70.0) or 70.0)
    feasibility = round(0.35 * velocity + 0.25 * (100.0 - penalty)
                        + 0.20 * regulatory + 0.20 * capacity, 1)
    if feasibility >= 75:
        rec = "GO"
    elif feasibility >= 55:
        rec = "CONDITIONAL"
    else:
        rec = "NO-GO"
    accrual = round(float(site.get("past_accrual_per_month", 0) or 0)
                    * (0.5 + capacity / 200.0), 2)
    risks: List[str] = []
    mitigations: List[str] = []
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
    sites: List[Dict[str, Any]],
    target_enrollment: int = 0,
    competitors_by_site: Dict[str, int] | None = None,
    competitor_sources: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Score a portfolio of sites; matches the cookbook JSON contract."""
    competitors_by_site = competitors_by_site or {}
    competitor_sources = competitor_sources or {}
    evaluated = [score_site(s, competitors_by_site.get(str(s.get("id", "")), 0),
                            competitor_sources.get(str(s.get("id", "")), "manual"))
                 for s in sites]
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
