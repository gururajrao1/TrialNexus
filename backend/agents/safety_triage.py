"""Agent 4 - Safety & Query Triage Coordinator. Deterministic, stdlib only.

Maps reported terms to MedDRA System Organ Classes, applies SAE criteria and
7-day / 15-day expedited clocks, and drafts site queries. Output matches the
cookbook JSON contract.
"""

from __future__ import annotations

import re
from typing import Any

SOC_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "Hepatobiliary disorders",
        "Alanine aminotransferase increased",
        ("alt", "ast", "bilirubin", "hepatic", "liver", "transaminase"),
    ),
    (
        "Cardiac disorders",
        "Electrocardiogram QT prolonged",
        ("qtc", "qt ", "cardiac", "heart", "arrhythmia", "myocardial", "lvef"),
    ),
    (
        "Blood and lymphatic system disorders",
        "Neutropenia",
        ("neutropen", "anc", "leukopen", "thrombocyto", "anemia", "platelet"),
    ),
    (
        "Gastrointestinal disorders",
        "Nausea",
        ("nausea", "vomit", "diarrhea", "diarrhoea", "abdominal", "colitis"),
    ),
    (
        "Respiratory, thoracic and mediastinal disorders",
        "Dyspnoea",
        ("dyspnea", "dyspnoea", "pneumonia", "pneumonitis", "cough", "hypoxia"),
    ),
    (
        "Nervous system disorders",
        "Headache",
        ("headache", "seizure", "neuropathy", "dizziness", "stroke"),
    ),
    (
        "Renal and urinary disorders",
        "Blood creatinine increased",
        ("creatinine", "renal", "kidney", "proteinuria"),
    ),
    (
        "Skin and subcutaneous tissue disorders",
        "Rash",
        ("rash", "pruritus", "dermatitis", "stevens"),
    ),
    (
        "Infections and infestations",
        "Febrile neutropenia",
        ("febrile", "sepsis", "septic", "infection"),
    ),
]

SAE_KEYWORDS = (
    "death",
    "fatal",
    "life-threat",
    "life threat",
    "hospital",
    "disab",
    "congenital",
    "anaphylaxis",
)
SEVERITY_GRADES = {"MILD": "Grade 1", "MODERATE": "Grade 2", "SEVERE": "Grade 3"}


def _has(blob: str, *keywords: str) -> bool:
    """Left word-boundary match: 'ast' must not match 'metastatic'."""
    return any(re.search(r"\b" + re.escape(k.strip()), blob) for k in keywords)


def _classify(text: str) -> tuple[str, str]:
    low = text.lower()
    for soc, pt, keywords in SOC_RULES:
        if _has(low, *keywords):
            return soc, pt
    return "General disorders and administration site conditions", "Adverse event"


def _grade(text: str, severity: str) -> str:
    m = re.search(r"grade\s*([1-5])", text, re.IGNORECASE)
    if m:
        return f"Grade {m.group(1)}"
    return SEVERITY_GRADES.get(severity.upper(), "Grade 2")


def _is_sae(text: str, grade: str) -> bool:
    low = text.lower()
    if any(k in low for k in SAE_KEYWORDS):
        return True
    try:
        return int(grade.split()[-1]) >= 4
    except ValueError:
        return False


def triage_one(record: dict[str, Any]) -> dict[str, Any]:
    """Triage a single discrepancy / adverse event record."""
    term = str(record.get("reported_term", record.get("term", "Unspecified event")))
    detail = str(record.get("description", record.get("query_text", "")))
    text = f"{term} {detail}"
    severity = str(record.get("severity", "MODERATE"))
    grade = _grade(text, severity)
    soc, pt = _classify(text)
    sae = _is_sae(text, grade)
    if isinstance(record.get("is_sae"), bool):
        sae = bool(record["is_sae"])
    unexpected = bool(record.get("unexpected")) or "unexpected" in text.lower()
    fatal = any(
        k in text.lower() for k in ("death", "fatal", "life-threat", "life threat")
    )
    if sae and unexpected:
        alert, deadline = True, 168 if fatal else 360
    else:
        alert, deadline = False, None
    query_text = (
        f"{term} reported for patient {record.get('patient_id', 'unknown')}: {detail or term}. "
        "Please confirm onset date, severity, relatedness to study drug, and action taken."
    ).strip()
    return {
        "discrepancy_id": str(record.get("discrepancy_id", record.get("id", "DISC-?"))),
        "patient_id": str(record.get("patient_id", "unknown")),
        "reported_term": term,
        "meddra_classification": {"soc": soc, "preferred_term": pt},
        "severity_grade": grade,
        "is_sae": sae,
        "regulatory_alert_required": alert,
        "reporting_deadline_hours": deadline,
        "site_query": {
            "query_target": "Investigator",
            "query_text": query_text,
            "auto_close_condition": (
                "Repeat assessment within 48 hours confirms "
                "resolution or documents alternative etiology."
            ),
        },
    }


def triage_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Triage many records; matches the cookbook JSON contract."""
    return {"triaged_records": [triage_one(r) for r in records]}
