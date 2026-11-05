"""Operations shells: monitoring plan, SIV checklist, milestone rollup.

All three compile what the app already holds into execution documents.
No new data collection, no persistence — the caller supplies the inputs
and keeps the output. Deterministic, stdlib only.
"""

from __future__ import annotations

from typing import Any

SDV_BY_TIER = {
    "critical": "100% of critical fields (consent, eligibility, endpoints, SAEs)",
    "major": "100% of critical fields for flagged subjects, sampled review otherwise",
    "minor": "Sampled review of critical fields; remote check-in",
}

VISIT_CADENCE = {
    "critical": "On-site every 4 weeks until two clean visits",
    "major": "On-site every 8 weeks, remote in between",
    "minor": "Remote every 8 weeks; on-site at milestones",
}


def monitoring_plan(
    protocol: dict[str, Any], site_tiers: list[dict[str, Any]]
) -> dict[str, Any]:
    """Risk-based monitoring plan from protocol meta + per-site tiers."""
    pid = str((protocol or {}).get("id", "?"))
    title = str((protocol or {}).get("title", ""))
    rows = []
    for s in site_tiers:
        if not isinstance(s, dict):
            continue
        tier = str(s.get("tier", "minor")).lower()
        if tier not in SDV_BY_TIER:
            tier = "minor"
        rows.append(
            {
                "site_id": str(s.get("site_id", "?")),
                "tier": tier,
                "sdv": SDV_BY_TIER[tier],
                "cadence": VISIT_CADENCE[tier],
                "reason": str(s.get("reason", "")),
            }
        )
    lines = [
        f"# Monitoring plan — {pid} {title}".strip(),
        "",
        "## Objective",
        "Aim monitoring where the risk is: central signals first, targeted "
        "visits for flagged sites, sampled review elsewhere.",
        "",
        "## Central signals (recomputed each cycle)",
        "- KRIs: screen failure, queries/patient, deviations, SAEs, "
        "enrollment gap (+ consent/eligibility deviations and overdue "
        "queries when fed).",
        "- Cross-site screens: robust z, exact Poisson high/low, funnel limits.",
        "",
        "## Site tiers",
    ]
    for r in rows:
        lines += [
            f"### {r['site_id']} — {r['tier']}",
            f"- SDV: {r['sdv']}",
            f"- Cadence: {r['cadence']}",
            (f"- Reason: {r['reason']}" if r["reason"] else "- Reason: routine"),
        ]
    lines += [
        "",
        "## Escalation",
        "Alert KRIs two cycles running, or any critical deviation, "
        "escalate the tier and schedule a visit within 10 working days.",
    ]
    return {"protocol_id": pid, "sites": rows, "markdown": "\n".join(lines)}


def siv_checklist(criteria: dict[str, Any]) -> dict[str, Any]:
    """Site initiation visit checklist from audited I/E criteria + standards."""
    items = [
        "Confirm delegation log signed and training records current.",
        "Confirm consent process and the approved consent version.",
        "Confirm investigational product storage, access, and temperature logs.",
        "Confirm SAE reporting path and 24-hour notification contacts.",
        "Confirm source-data expectations and EDC access for the team.",
    ]
    inc = criteria.get("inclusion_criteria", []) if isinstance(criteria, dict) else []
    exc = criteria.get("exclusion_criteria", []) if isinstance(criteria, dict) else []
    for c in list(inc)[:6]:
        text = c.get("raw_text", "") if isinstance(c, dict) else str(c)
        if text.strip():
            items.append("Verify site can evidence: " + text.strip()[:140])
    for c in list(exc)[:4]:
        text = c.get("raw_text", "") if isinstance(c, dict) else str(c)
        if text.strip():
            items.append("Verify site screens out: " + text.strip()[:140])
    items.append("Document open questions with owners and due dates.")
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return {"n_items": len(out), "items": out}


STAGE_ORDER = ("identified", "feasibility", "contract", "irb", "activated", "fpi")
NEXT_ACTION = {
    "identified": "Send feasibility questionnaire; set a 2-week return date.",
    "feasibility": "Score the return; go/no-go within 1 week.",
    "contract": "Push CTA redlines weekly; escalate past the benchmark.",
    "irb": "Confirm submission accepted; answer stipulations within 5 days.",
    "activated": "Confirm first-patient-ready: staff, IMP, EDC live.",
    "fpi": "No action — enrolled.",
}


def budget_estimate(spec: dict[str, Any]) -> dict[str, Any]:
    """Site budget from a user-supplied rate card x schedule.

    spec: {arms: [{name, n_subjects}], visits: [{name, n_per_subject,
    procedures: [{name, unit_cost, count_per_visit}]}], fixed_costs:
    [{name, amount}]}. All rates are user-entered; the app only multiplies.
    """
    if not isinstance(spec, dict):
        raise ValueError("spec must be an object")
    arms = [a for a in (spec.get("arms", []) or []) if isinstance(a, dict)]
    visits = [v for v in (spec.get("visits", []) or []) if isinstance(v, dict)]
    fixed = [f for f in (spec.get("fixed_costs", []) or []) if isinstance(f, dict)]
    if not arms:
        raise ValueError("at least one arm with n_subjects is required")
    if not visits:
        raise ValueError("at least one visit is required")
    visit_rows = []
    per_subject = 0.0
    for v in visits:
        per_visit = 0.0
        procs = []
        for p in v.get("procedures", []) or []:
            if not isinstance(p, dict):
                continue
            cost = max(0.0, float(p.get("unit_cost", 0) or 0))
            cnt = max(0, int(p.get("count_per_visit", 1) or 0))
            per_visit += cost * cnt
            procs.append(
                {
                    "name": str(p.get("name", "?")),
                    "unit_cost": cost,
                    "count_per_visit": cnt,
                    "line": round(cost * cnt, 2),
                }
            )
        times = max(0, int(v.get("n_per_subject", 1) or 0))
        visit_rows.append(
            {
                "visit": str(v.get("name", "?")),
                "times_per_subject": times,
                "per_visit": round(per_visit, 2),
                "per_subject": round(per_visit * times, 2),
                "procedures": procs,
            }
        )
        per_subject += per_visit * times
    arm_rows = []
    for a in arms:
        n = max(0, int(a.get("n_subjects", 0) or 0))
        arm_rows.append(
            {
                "arm": str(a.get("name", "?")),
                "n_subjects": n,
                "subtotal": round(n * per_subject, 2),
            }
        )
    fixed_rows = [
        {
            "name": str(f.get("name", "?")),
            "amount": round(max(0.0, float(f.get("amount", 0) or 0)), 2),
        }
        for f in fixed
    ]
    fixed_total = round(sum(f["amount"] for f in fixed_rows), 2)
    variable_total = round(sum(a["subtotal"] for a in arm_rows), 2)
    return {
        "per_subject": round(per_subject, 2),
        "arms": arm_rows,
        "visits": visit_rows,
        "fixed_costs": fixed_rows,
        "variable_total": variable_total,
        "fixed_total": fixed_total,
        "grand_total": round(variable_total + fixed_total, 2),
        "basis": "User-entered rates times user-entered schedule; no benchmarks applied.",
    }


CDISC_DEVIATION_MAP = {
    "out-of-window": ("C158837", "Visit window deviation"),
    "missing-assessment": ("C158838", "Assessment not performed"),
    "consent-violation": ("C158839", "Informed consent deviation"),
    "unreported-sae": ("C158840", "Safety reporting deviation"),
    "eligibility-violation": ("C158841", "Eligibility deviation"),
}

WHY_QUESTIONS = {
    "out-of-window": [
        "Why was the visit outside the window (scheduling, patient, site)?",
        "Why did the scheduling process allow the drift?",
        "Why was the drift not caught before the window closed?",
        "Why does the process depend on that single check?",
        "Why is that dependency acceptable — and what changes it?",
    ],
    "missing-assessment": [
        "Why was the assessment missed (forgotten, refused, unevaluable)?",
        "Why did the visit checklist not catch it?",
        "Why is the checklist not enforced at visit close?",
        "Why does the workflow allow closing without it?",
        "Why is that acceptable — and what changes it?",
    ],
    "consent-violation": [
        "Why was consent late, missing, or the wrong version?",
        "Why did the procedure start without verified consent?",
        "Why is verification not a hard stop in the workflow?",
        "Why was the wrong version in circulation?",
        "Why is version control not enforced — and what changes it?",
    ],
}


def code_deviation(deviation_type: str, detail: str = "") -> dict[str, Any]:
    """Map our deviation types to CDISC-style categories (documented map)."""
    key = str(deviation_type or "").strip().lower()
    code, label = CDISC_DEVIATION_MAP.get(key, ("C158842", "Other deviation"))
    return {
        "type": key or "?",
        "cdisc_code": code,
        "cdisc_label": label,
        "detail": str(detail or "")[:200],
        "basis": "Fixed project map; confirm against CDISC CT before filing.",
    }


def five_whys(deviation_type: str, detail: str = "") -> dict[str, Any]:
    """5-whys root-cause scaffold for a deviation type; generic fallback."""
    key = str(deviation_type or "").strip().lower()
    questions = WHY_QUESTIONS.get(
        key,
        [
            "What happened, in one sentence?",
            "Why did that happen (immediate cause)?",
            "Why did the immediate cause occur (process cause)?",
            "Why did the process allow it (system cause)?",
            "Why is that system state acceptable — and what changes it?",
        ],
    )
    return {
        "type": key or "?",
        "detail": str(detail or "")[:200],
        "questions": questions,
        "effectiveness_check": (
            "Re-audit 5 consecutive cases; zero repeat in 90 days closes the CAPA."
        ),
        "basis": "Scaffold only — answers come from the site, not the app.",
    }


def visit_report(
    findings: list[dict[str, Any]], site_tier: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Monitoring visit report from screened deviation findings."""
    rows = [f for f in findings if isinstance(f, dict)]
    by_sev: dict[str, int] = {}
    for f in rows:
        by_sev[str(f.get("severity", "?"))] = (
            by_sev.get(str(f.get("severity", "?")), 0) + 1
        )
    tier = (site_tier or {}).get("tier", "?") if isinstance(site_tier, dict) else "?"
    lines = [
        f"# Monitoring visit report — {((site_tier or {}).get('site_id', '?') if isinstance(site_tier, dict) else '?')} (tier {tier})",
        "",
        f"Findings reviewed: {len(rows)} "
        + (
            f"({', '.join(f'{k}: {v}' for k, v in sorted(by_sev.items()))})"
            if by_sev
            else "(none)"
        ),
        "",
        "## Findings",
    ]
    for f in rows:
        lines.append(
            f"- [{f.get('severity', '?')}] {f.get('type', '?')} — "
            f"{f.get('subject', '?')} {f.get('visit', '?')}: "
            f"{str(f.get('detail', ''))[:160]}"
        )
    lines += [
        "",
        "## Actions",
        "1. Confirm each finding with source; record corrections.",
        "2. Open CAPAs for major/critical with effectiveness checks.",
        "3. Re-screen next cycle; escalate tier on repeat.",
    ]
    return {
        "n_findings": len(rows),
        "by_severity": by_sev,
        "markdown": "\n".join(lines),
    }


def inspection_pack(
    protocol: dict[str, Any],
    counts: dict[str, int],
    open_items: list[str],
) -> dict[str, Any]:
    """BIMO-style exhibit list compiled from database counts."""
    pid = str((protocol or {}).get("id", "?"))
    exhibits = [
        {
            "exhibit": "Protocol + all amendments",
            "status": "on file" if pid != "?" else "confirm",
            "detail": str((protocol or {}).get("title", ""))[:120],
        },
        {
            "exhibit": "Delegation + training records",
            "status": "[FILL — pull from TMF]",
            "detail": "",
        },
        {
            "exhibit": "Consent forms (all versions)",
            "status": "[FILL — pull from TMF]",
            "detail": "",
        },
        {
            "exhibit": "Deviation log",
            "status": "compiled" if counts.get("deviations") else "confirm",
            "detail": f"{counts.get('deviations', 0)} findings in scope",
        },
        {
            "exhibit": "Query log with aging",
            "status": "compiled",
            "detail": (
                f"{counts.get('queries', 0)} queries, "
                f"{counts.get('overdue', 0)} overdue"
            ),
        },
        {
            "exhibit": "SAE listings with reporting clocks",
            "status": "compiled",
            "detail": f"{counts.get('sae', 0)} SAE-linked records",
        },
        {
            "exhibit": "Monitoring visit reports + CAPAs",
            "status": "[FILL — attach plans]",
            "detail": "",
        },
        {"exhibit": "Database-lock checklist", "status": "[FILL]", "detail": ""},
    ]
    return {
        "protocol_id": pid,
        "exhibits": exhibits,
        "open_items": [str(x)[:200] for x in (open_items or []) if x],
        "ready": all(e["status"] not in ("confirm",) for e in exhibits),
        "basis": "Compiled exhibits are counts from the app DB; [FILL] items live in the TMF.",
    }


def dsmb_pack(
    protocol: dict[str, Any],
    site_rows: list[dict[str, Any]],
    query_counts: dict[str, int],
    eval_counts: dict[str, int],
    sae_count: int,
) -> dict[str, Any]:
    """One-click DSMB pack: enrollment, safety, deviations-ready summary."""
    sites = [s for s in site_rows if isinstance(s, dict)]
    activated = sum(1 for s in sites if str(s.get("stage", "")) in ("activated", "fpi"))
    lines = [
        f"# DSMB report pack — {protocol.get('id', '?')} "
        f"{str(protocol.get('title', ''))[:80]}".rstrip(),
        "",
        "## Enrollment",
        f"Sites: {len(sites)} listed, {activated} activated. "
        f"Evaluations by status: {eval_counts or '{}'}.",
        "",
        "## Safety",
        f"Safety queries: {query_counts.get('total', 0)} total, "
        f"{query_counts.get('open', 0)} open, "
        f"{query_counts.get('sae', 0)} SAE-linked; "
        f"{sae_count} SAE records in scope.",
        "",
        "## Deviations & queries",
        "[FILL — attach deviation log and query listings]",
        "",
        "## Recommendation",
        "[FILL — continue / modify / pause with rationale]",
    ]
    return {
        "protocol_id": str(protocol.get("id", "?")),
        "n_sites": len(sites),
        "n_activated": activated,
        "markdown": "\n".join(lines),
    }


def milestone_rollup(report: dict[str, Any]) -> dict[str, Any]:
    """Activation rollup from a startup report: counts, flags, next actions.

    Accepts the /api/startup payload shape (sites with stage/days/flags).
    """
    sites = [s for s in (report or {}).get("sites", []) if isinstance(s, dict)]
    by_stage: dict[str, int] = {s: 0 for s in STAGE_ORDER}
    flagged = []
    for s in sites:
        stage = str(s.get("stage", "identified"))
        by_stage[stage] = by_stage.get(stage, 0) + 1
        flags = s.get("flags", []) or []
        if flags:
            flagged.append(
                {
                    "site_id": str(s.get("site_id", "?")),
                    "stage": stage,
                    "days_in_stage": s.get("days_in_stage", "?"),
                    "flags": [str(f) for f in flags],
                    "next_action": NEXT_ACTION.get(stage, "Review manually."),
                }
            )
    done = by_stage.get("activated", 0) + by_stage.get("fpi", 0)
    total = max(1, len(sites))
    return {
        "n_sites": len(sites),
        "by_stage": by_stage,
        "pct_activated": round(100.0 * done / total, 1),
        "flagged": sorted(flagged, key=lambda f: str(f["site_id"])),
        "basis": "Startup pipeline stages with benchmark flags; no action invented.",
    }
