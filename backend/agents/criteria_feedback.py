"""Eligibility-criteria design feedback. Deterministic, stdlib only.

Rule-based edition of TrialBench's eligibility-criteria-design task:
grades each audited criterion A/B/C on machine-readability and flags
the phrasings that drive amendments and screen failures — vague
qualifiers ("adequate", "significant"), bundled multi-rule lines,
missing units/windows, and investigator-judgment escapes. Each flag
carries a concrete rewrite suggestion.
"""

from __future__ import annotations

import re
from typing import Any

VAGUE = (
    "adequate",
    "significant",
    "clinically significant",
    "acceptable",
    "suitable",
    "appropriate",
    "investigator judgment",
    "investigator's discretion",
    "at the discretion",
    "in the opinion",
)
WINDOW_RE = re.compile(r"within\s+\d+\s*(day|week|month)", re.IGNORECASE)
UNIT_RE = re.compile(
    r"\b(mg/dL|g/dL|mmol/L|umol/L|µmol/L|mL/min|/uL|10\^9/L|msec|mmHg|"
    r"years?|months?|weeks?|days?)\b",
    re.IGNORECASE,
)


def grade_criterion(crit: dict[str, Any]) -> dict[str, Any]:
    """Grade one criterion + flags with rewrite suggestions."""
    text = str(crit.get("raw_text", ""))
    low = text.lower()
    flags: list[dict[str, str]] = []
    penalty = 0

    found = sorted({v for v in VAGUE if v in low})
    found = [v for v in found if not any(v != w and v in w for w in found)]
    if found:
        penalty += 2 + (len(found) - 1)
        flags.append(
            {
                "issue": f"vague qualifier: {', '.join(found)}",
                "suggestion": "Replace with a numeric threshold + unit (e.g. "
                "'creatinine <= 1.5x ULN' instead of 'adequate renal function').",
            }
        )
    subs = crit.get("sub_rules") or []
    if len(subs) > 1:
        penalty += 1
        flags.append(
            {
                "issue": f"bundled line ({len(subs)} sub-rules)",
                "suggestion": "Split into one machine-readable rule per line so "
                "each can pass/fail independently.",
            }
        )
    has_number = bool(re.search(r"\d", text))
    if (
        has_number
        and not UNIT_RE.search(text)
        and "ecog" not in low
        and "kps" not in low
    ):
        penalty += 1
        flags.append(
            {
                "issue": "numeric threshold without units",
                "suggestion": "Add explicit units (mg/dL, mL/min, /uL) to every number.",
            }
        )
    if (
        "prior" in low or "previous" in low or "history of" in low
    ) and not WINDOW_RE.search(text):
        penalty += 1
        flags.append(
            {
                "issue": "therapy/history statement without a time window",
                "suggestion": "Add 'within N days of Day 1' so washout is checkable.",
            }
        )
    grade = "A" if penalty == 0 else ("B" if penalty <= 2 else "C")
    return {
        "id": crit.get("id"),
        "grade": grade,
        "penalty": penalty,
        "flags": flags,
    }


def design_feedback(audit: dict[str, Any]) -> dict[str, Any]:
    """Grade all criteria; trial-level design score + worst offenders."""
    items = [
        grade_criterion(c)
        for c in (audit.get("inclusion_criteria", []) or [])
        + (audit.get("exclusion_criteria", []) or [])
    ]
    n = len(items)
    score = (
        round(
            100.0 * sum({"A": 1.0, "B": 0.6, "C": 0.2}[i["grade"]] for i in items) / n
        )
        if n
        else 0
    )
    worst = sorted(items, key=lambda i: (-i["penalty"], str(i["id"])))[:3]
    return {
        "criteria": items,
        "design_score": score,
        "worst": [w for w in worst if w["penalty"] > 0],
        "counts": {
            "A": sum(1 for i in items if i["grade"] == "A"),
            "B": sum(1 for i in items if i["grade"] == "B"),
            "C": sum(1 for i in items if i["grade"] == "C"),
        },
        "basis": (
            "A = machine-readable as written; B = one fix needed; C = vague "
            "or bundled. Vague-qualifier and missing-window flags track the "
            "amendment/screen-failure literature."
        ),
    }
