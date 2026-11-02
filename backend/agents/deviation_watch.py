"""Deviation watch: rule-based protocol-deviation detector + SDV tiers.

Reads visit records (uploaded by the CRA, e.g. exported from the CTMS)
and flags out-of-window visits, missing required assessments, and
consent-date violations with severity and days-late. Sites with
critical/major findings get 100%-of-critical-fields SDV; clean sites get
sample-only review of low-risk fields. Deterministic, stdlib only.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

CRITICAL_TYPES = {"consent-violation"}
BINOMIAL_FLAG_P = 0.05


def _parse_day(value: Any) -> int | None:
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None


def _parse_date(value: Any):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _binom_upper_tail(n: int, k: int, p: float) -> float:
    """Exact P(X >= k) for Binomial(n, p). Guards degenerate p."""
    if n <= 0 or k <= 0:
        return 1.0
    if p <= 0:
        return 0.0
    if p >= 1:
        return 1.0
    return sum(
        math.comb(n, i) * (p**i) * ((1.0 - p) ** (n - i)) for i in range(k, n + 1)
    )


def _site_signals(
    records: list[dict[str, Any]], findings: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-site deviation-rate outlier screen (central-monitoring style).

    A site's affected-visit rate is tested against the pooled portfolio
    background rate with an exact binomial upper tail: a site with far
    more deviations than the portfolio explains gets flagged, while a
    uniformly clean (or uniformly messy) portfolio flags nothing.
    """
    visits: set[tuple[str, str, str]] = set()
    for rec in records:
        visits.add(
            (
                str(rec.get("site_id", "?")),
                str(rec.get("subject", rec.get("patient_id", "?"))),
                str(rec.get("visit", "?")),
            )
        )
    affected: set[tuple[str, str, str]] = set()
    for f in findings:
        affected.add((str(f["site_id"]), str(f["subject"]), str(f["visit"])))
    n_by_site: dict[str, int] = {}
    for s, _, _ in visits:
        n_by_site[s] = n_by_site.get(s, 0) + 1
    k_by_site: dict[str, int] = {}
    for s, _, _ in affected:
        k_by_site[s] = k_by_site.get(s, 0) + 1
    total_n = sum(n_by_site.values()) or 1
    total_k = sum(k_by_site.get(s, 0) for s in n_by_site)
    background = total_k / total_n
    out = []
    for s in sorted(n_by_site):
        n = n_by_site[s]
        k = k_by_site.get(s, 0)
        rate = k / n if n else 0.0
        p = _binom_upper_tail(n, k, background) if k > 0 else 1.0
        out.append(
            {
                "site_id": s,
                "n_visits": n,
                "n_affected": k,
                "rate": round(rate, 3),
                "background_rate": round(background, 3),
                "p_value": round(p, 4),
                "direction": "high" if rate > background else "-",
                "flag": bool(k > 0 and rate > background and p < BINOMIAL_FLAG_P),
            }
        )
    return out


def watch_deviations(
    records: list[dict[str, Any]], window_days: int = 3
) -> dict[str, Any]:
    """Flag deviations over uploaded visit records."""
    window = max(0, int(window_days))
    findings = []
    for rec in records:
        site = str(rec.get("site_id", "?"))
        subj = str(rec.get("subject", rec.get("patient_id", "?")))
        visit = str(rec.get("visit", "?"))
        planned = _parse_day(rec.get("planned_day"))
        actual = _parse_day(rec.get("actual_day", rec.get("visit_day")))
        if planned is not None and actual is not None:
            late = abs(actual - planned)
            if late > window:
                findings.append(
                    {
                        "site_id": site,
                        "subject": subj,
                        "visit": visit,
                        "type": "out-of-window",
                        "severity": "major" if late > 7 else "minor",
                        "days_late": late,
                        "detail": f"Day {actual} vs planned day {planned}",
                    }
                )
        required = rec.get("assessments_required", []) or []
        done = set(rec.get("assessments_done", []) or [])
        missing = [a for a in required if a not in done]
        if missing:
            findings.append(
                {
                    "site_id": site,
                    "subject": subj,
                    "visit": visit,
                    "type": "missing-assessment",
                    "severity": "major",
                    "days_late": 0,
                    "detail": "Missing: " + ", ".join(str(a) for a in missing),
                }
            )
        consent = _parse_date(rec.get("consent_date"))
        vdate = _parse_date(rec.get("visit_date"))
        if consent is not None and vdate is not None and consent > vdate:
            findings.append(
                {
                    "site_id": site,
                    "subject": subj,
                    "visit": visit,
                    "type": "consent-violation",
                    "severity": "critical",
                    "days_late": (consent - vdate).days,
                    "detail": f"Consent {consent.isoformat()} after visit {vdate.isoformat()}",
                }
            )
    sites = sorted({f["site_id"] for f in findings})
    tiers = [
        {
            "site_id": s,
            "tier": (
                "100% critical fields"
                if any(
                    f["site_id"] == s and (f["severity"] in ("critical", "major"))
                    for f in findings
                )
                else "sample low-risk fields"
            ),
            "n_findings": sum(1 for f in findings if f["site_id"] == s),
        }
        for s in sites
    ]
    return {
        "findings": findings,
        "by_site": tiers,
        "site_signals": _site_signals(records, findings),
        "summary": {
            "n_records": len(records),
            "n_findings": len(findings),
            "n_sites_flagged": len(sites),
        },
        "basis": (
            f"Out-of-window beyond ±{window}d, required-but-missing "
            "assessments, and consent-after-visit. Critical/major sites "
            "get 100% SDV of critical fields; the rest get sampled review. "
            "Site signals test each site's affected-visit rate against the "
            "pooled background rate (exact binomial tail, p<0.05)."
        ),
    }
