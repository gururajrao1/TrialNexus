"""Deviation watch: rule-based protocol-deviation detector + SDV tiers.

Reads visit records (uploaded by the CRA, e.g. exported from the CTMS)
and flags out-of-window visits, missing required assessments, and
consent-date violations with severity and days-late. Sites with
critical/major findings get 100%-of-critical-fields SDV; clean sites get
sample-only review of low-risk fields. Deterministic, stdlib only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

CRITICAL_TYPES = {"consent-violation"}


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
        "summary": {
            "n_records": len(records),
            "n_findings": len(findings),
            "n_sites_flagged": len(sites),
        },
        "basis": (
            f"Out-of-window beyond ±{window}d, required-but-missing "
            "assessments, and consent-after-visit. Critical/major sites "
            "get 100% SDV of critical fields; the rest get sampled review."
        ),
    }
