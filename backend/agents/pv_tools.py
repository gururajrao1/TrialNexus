"""Pharmacovigilance shells: E2B export, DSUR shell, risk register, review.

Everything here compiles what the app already holds into submission-shaped
output. Nothing is transmitted anywhere; case narratives stay local. The
E2B XML covers core ICSR elements (E2B(R3)-shaped, not a certified build);
the DSUR shell counts the database and marks prose sections [FILL].
Deterministic, stdlib only, never raises on bad shapes.
"""

from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape


def _text(value: Any, default: str = "") -> str:
    text = str(value).strip() if value is not None else ""
    return text or default


def e2b_xml(record: dict[str, Any]) -> dict[str, Any]:
    """One triaged record -> E2B(R3)-shaped ICSR XML (core elements only)."""
    if not isinstance(record, dict):
        return {"xml": "", "error": "record must be an object"}
    disc = _text(record.get("discrepancy_id", record.get("id")), "DISC-?")
    meddra = record.get("meddra_classification", {}) or {}
    sae = bool(record.get("is_sae", False))
    serious = "1" if sae else "2"
    body = (
        "<ichicsr>"
        "<ichicsrmessageheader>"
        f"<messagetype>ichicsr</messagetype><messageformatversion>2.1</messageformatversion>"
        f"<messageformatrelease>1.0</messageformatrelease><messagenumb>{escape(disc)}</messagenumb>"
        "</ichicsrmessageheader>"
        "<safetyreport>"
        f"<safetyreportid>{escape(disc)}</safetyreportid>"
        f"<patient><patientinitial>{escape(_text(record.get('patient_id'), '?')[:8])}</patientinitial>"
        "<reaction>"
        f"<reactionmeddrapt>{escape(_text(meddra.get('preferred_term'), '?'))}</reactionmeddrapt>"
        f"<reactionmeddrasoc>{escape(_text(meddra.get('soc'), '?'))}</reactionmeddrasoc>"
        f"<reactionoutcome>1</reactionoutcome>"
        "</reaction>"
        "<drug>"
        f"<drugcharacterization>1</drugcharacterization>"
        f"<medicinalproduct>{escape(_text(record.get('suspect_drug'), '?'))}</medicinalproduct>"
        "</drug></patient>"
        f"<serious>{serious}</serious>"
        f"<seriousnessdeath>{'1' if sae else '2'}</seriousnessdeath>"
        f"<reportersourcetype>4</reportersourcetype>"
        f"<reportcomment>{escape(_text(record.get('reported_term'), ''))} "
        f"[{escape(_text(record.get('severity_grade'), ''))}]</reportcomment>"
        "</safetyreport></ichicsr>"
    )
    return {"xml": body, "message_id": disc, "serious": sae}


def dsur_shell(
    protocol: dict[str, Any],
    queries: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    """DSUR-shaped shell from database counts; prose sections marked [FILL]."""
    queries = [q for q in queries if isinstance(q, dict)]
    open_q = sum(
        1 for q in queries if str(q.get("resolution_status", "")).upper() != "RESOLVED"
    )
    sae_q = sum(1 for q in queries if q.get("is_sae"))
    statuses: dict[str, int] = {}
    for e in evaluations:
        if isinstance(e, dict):
            s = str(e.get("eligibility_status", "?"))
            statuses[s] = statuses.get(s, 0) + 1
    title = _text((protocol or {}).get("title"), "Untitled protocol")
    pid = _text((protocol or {}).get("id"), "?")
    counts = {
        "safety_queries": len(queries),
        "open_queries": open_q,
        "sae_queries": sae_q,
        "evaluations_by_status": statuses,
    }
    sections = [
        {
            "heading": "1. Introduction",
            "body": f"Development Safety Update Report shell for {pid} — {title}. [FILL period]",
        },
        {"heading": "2. Worldwide marketing approval status", "body": "[FILL]"},
        {
            "heading": "3. Actions taken for safety reasons",
            "body": (
                "[FILL] Open queries at cutoff: "
                f"{open_q} of {len(queries)}; SAE-linked: {sae_q}."
            ),
        },
        {"heading": "4. Changes to reference safety information", "body": "[FILL]"},
        {
            "heading": "5. Inventory of clinical trial exposure",
            "body": (f"[FILL] Evaluations on file by status: {statuses or '{}'}."),
        },
        {
            "heading": "6. Data in summary tabulations",
            "body": "[FILL — attach SAE line listings]",
        },
        {"heading": "7. Overall safety assessment and conclusion", "body": "[FILL]"},
    ]
    return {"protocol_id": pid, "counts": counts, "sections": sections}


def build_risk_register(
    signals: list[dict[str, Any]], deviations_note: str = ""
) -> dict[str, Any]:
    """Ranked risk list from signal rows; each risk gets owner + mitigation.

    Rank key: status weight (signal 3, watch 2, else 1) times log(1+n) times
    PRR. Documented and fixed — prioritization, not statistics.
    """
    import math

    weight = {"signal": 3.0, "watch": 2.0}
    risks = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        n = max(0, int(s.get("n", 0) or 0))
        prr = max(0.0, float(s.get("prr", 0) or 0))
        score = round(
            weight.get(str(s.get("status", "")), 1.0) * math.log1p(n) * (1 + prr), 2
        )
        risks.append(
            {
                "drug": _text(s.get("drug_label", s.get("drug"))),
                "event": _text(s.get("event")),
                "status": _text(s.get("status")),
                "n": n,
                "prr": prr,
                "risk_score": score,
                "owner": "Safety physician",
                "mitigation": (
                    "Assess case series and update investigator "
                    "brochure language if confirmed."
                ),
            }
        )
    risks.sort(key=lambda r: (-r["risk_score"], r["drug"], r["event"]))
    return {
        "risks": risks,
        "context": deviations_note.strip()[:300],
        "note": "Prioritization aid; confirm every risk against source cases.",
    }


VALID_DECISIONS = ("accept", "refute", "monitor")


def sae_narrative(record: dict[str, Any]) -> dict[str, Any]:
    """Structured SAE narrative drafted from a triaged record's fields.

    Template only — the medical writer verifies every line. Placeholders
    ([FILL]) mark what the record cannot supply.
    """
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    meddra = record.get("meddra_classification", {}) or {}
    lines = [
        "SERIOUS ADVERSE EVENT NARRATIVE (draft — verify before filing)",
        f"Subject: {record.get('patient_id', '[FILL]')} | "
        f"Report: {record.get('discrepancy_id', record.get('id', '[FILL]'))}",
        f"Suspect drug: {record.get('suspect_drug', '[FILL]')}",
        f"Event: {record.get('reported_term', '[FILL]')} "
        f"({meddra.get('preferred_term', '?')} / {meddra.get('soc', '?')})",
        f"Severity: {record.get('severity_grade', '[FILL]')} | "
        f"Serious: {'yes' if record.get('is_sae') else 'no'}",
        f"Onset: {((record.get('enrichment', {}) or {}).get('temporality', {}) or {}).get('onset', '[FILL]')} | "
        f"Relatedness: {((record.get('enrichment', {}) or {}).get('attribution', {}) or {}).get('relatedness', '[FILL]')}",
        "Course: [FILL — onset date, treatment, outcome, dates]",
        "Medical history / concomitants: [FILL]",
        f"Reporter query: {(record.get('site_query', {}) or {}).get('query_text', '[FILL]')}",
        "Causality assessment: [FILL — Naranjo / WHO-UMC]",
    ]
    return {"narrative": "\n".join(lines)}


def screen_concomitant(
    label_sections: dict[str, Any], meds: list[str]
) -> dict[str, Any]:
    """Flag concomitant meds named in a DailyMed label's warning sections.

    Lexical, section-aware: matches whole-word mentions inside boxed
    warnings, warnings, interactions, and contraindications text. A hit is
    a pointer to read that section — not an interaction claim.
    """
    sections = label_sections if isinstance(label_sections, dict) else {}
    watch = ("boxed", "warning", "interaction", "contraindication")
    haystacks = []
    for key, val in sections.items():
        low = str(key).lower()
        if any(w in low for w in watch):
            text = (
                val
                if isinstance(val, str)
                else " ".join(str(x) for x in (val if isinstance(val, list) else [val]))
            )
            haystacks.append((key, text.lower()))
    hits = []
    for med in meds:
        name = str(med or "").strip().lower()
        if len(name) < 3:
            continue
        for key, hay in haystacks:
            if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", hay):
                hits.append({"med": str(med), "section": str(key)})
                break
    return {
        "checked": [str(m) for m in meds],
        "hits": hits,
        "basis": (
            "Whole-word mentions in warning-class label sections. "
            "Read the cited section — this is not an interaction claim."
        ),
    }


ESCALATION_CHAINS = [
    (1, "Site coordinator resolves within 7 days; CRA notified."),
    (31, "Escalate to CRA + site manager; 5-day action plan."),
    (61, "Escalate to sponsor; open a CAPA with effectiveness check."),
]


def escalation_chains(aging: dict[str, Any]) -> dict[str, Any]:
    """Escalation chains from a query-aging payload (levels + owners)."""
    rows = [
        r for r in (aging or {}).get("escalation_list", []) or [] if isinstance(r, dict)
    ]
    chains = []
    for r in rows:
        overdue = int(r.get("days_overdue", 0) or 0)
        rule = next(
            rule for start, rule in reversed(ESCALATION_CHAINS) if overdue >= start
        )
        level = (
            "site"
            if overdue <= 30
            else "cra+manager"
            if overdue <= 60
            else "sponsor+capa"
        )
        chains.append(
            {
                "id": str(r.get("id", "?")),
                "days_overdue": overdue,
                "level": level,
                "rule": rule,
            }
        )
    return {"chains": chains, "n_chains": len(chains), "basis": query_aging_basis()}


def query_aging_basis() -> str:
    return (
        "Levels: 1-30d site, 31-60d CRA+manager, 61d+ sponsor+CAPA. "
        "Mirrors the query-aging SLA policy."
    )


def review_signals(
    signals: list[dict[str, Any]], decisions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Apply reviewer dispositions to signal rows with an audit trail.

    Decisions key on drug+event; unknown keys and bad verdicts are reported,
    never applied. Pure function — persistence stays with the caller.
    """
    by_key = {}
    for s in signals:
        if isinstance(s, dict):
            by_key[(str(s.get("drug")), str(s.get("event")))] = dict(s)
    trail = []
    errors = []
    for d in decisions:
        if not isinstance(d, dict):
            errors.append("decision must be an object")
            continue
        key = (str(d.get("drug", "")), str(d.get("event", "")))
        verdict = str(d.get("decision", ""))
        if key not in by_key:
            errors.append(f"unknown pair: {key[0]} / {key[1]}")
            continue
        if verdict not in VALID_DECISIONS:
            errors.append(f"bad verdict '{verdict}' for {key[0]} / {key[1]}")
            continue
        by_key[key]["review"] = verdict
        by_key[key]["review_note"] = _text(d.get("note", ""))[:300]
        trail.append(
            {
                "drug": key[0],
                "event": key[1],
                "decision": verdict,
                "note": by_key[key]["review_note"],
            }
        )
    reviewed = sorted(
        by_key.values(), key=lambda r: (str(r.get("drug")), str(r.get("event")))
    )
    return {
        "signals": reviewed,
        "trail": trail,
        "errors": errors,
        "n_reviewed": len(trail),
    }
