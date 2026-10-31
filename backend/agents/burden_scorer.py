"""Visit-burden + DCT-fit scorer. Deterministic, stdlib only (re).

Extracts visit days from protocol text, scores each visit's procedural load,
and judges which visits could go remote (telehealth / home nursing) versus
must stay on-site. Weights follow reported burden drivers: invasive
procedures (biopsy) highest, then imaging, PK-intensive sampling, labs/ECG.
"""

from __future__ import annotations

import re
from typing import Any

VISIT_RE = re.compile(r"\bDay\s+(\d+)", re.IGNORECASE)
XN_RE = re.compile(r"x\s*(\d+)", re.IGNORECASE)

RULES = (
    ("biopsy", r"\bbiops\w*\b", 10),
    ("imaging", r"\b(mri|pet|imaging|tumor assessment|x-?ray)\b", 5),
    ("ct-scan", r"\bct\b", 5),
    ("pk draws", r"\bpk\b", 2),  # multiplied by sampled units
    ("labs", r"\blabs?\b", 2),
    ("infusion/dosing", r"\b(infusion|dos(e|ing))\b", 4),
    ("ecg", r"\becg\b", 1),
)
BASE_VISIT = 3


def _pk_units(window_low: str) -> int:
    m = XN_RE.search(window_low)
    if m:
        try:
            return max(1, int(m.group(1)))
        except ValueError:
            pass
    return 1


def _score_window(window: str) -> tuple[list[str], int, int]:
    low = window.lower()
    procs: list[str] = []
    score = BASE_VISIT
    pk_units = 0
    for label, pattern, weight in RULES:
        if re.search(pattern, low):
            if label == "pk draws":
                pk_units = _pk_units(low)
                score += weight * pk_units
                procs.append(f"pk draws x{pk_units}")
            else:
                score += weight
                procs.append(label)
    return procs, score, pk_units


def score_burden(raw_text: str) -> dict[str, Any]:
    """Score every visit day found in protocol text."""
    matches = list(VISIT_RE.finditer(raw_text))
    by_day: dict[str, dict[str, Any]] = {}
    for i, m in enumerate(matches):
        day = m.group(1)
        end = matches[i + 1].start() if i + 1 < len(matches) else m.start() + 150
        window = raw_text[m.start() : min(end, m.start() + 150)]
        procs, score, pk_units = _score_window(window)
        prev = by_day.get(day)
        if prev is None or score > prev["score"]:
            by_day[day] = {
                "day": day,
                "mentions": 0,
                "procedures": procs,
                "pk_units": pk_units,
                "score": score,
            }
        by_day[day]["mentions"] += 1
    visits = []
    for day in sorted(by_day, key=int):
        v = by_day[day]
        invasive = any(p in ("biopsy", "imaging", "ct-scan") for p in v["procedures"])
        pk_heavy = v["pk_units"] > 1
        if invasive:
            convertible, reason = False, "on-site: invasive procedure"
        elif pk_heavy:
            convertible, reason = False, "on-site: PK-intensive sampling"
        else:
            convertible, reason = True, "telehealth / home-nurse candidate"
        visits.append({**v, "convertible": convertible, "reason": reason})
    total = sum(v["score"] for v in visits)
    conv = sum(1 for v in visits if v["convertible"])
    pct = round(100.0 * conv / len(visits), 1) if visits else 0.0
    peak = max((v["score"] for v in visits), default=0)
    if total >= 30 or peak >= 15:
        verdict = "High — consider consolidating visits"
    elif total >= 15:
        verdict = "Moderate"
    else:
        verdict = "Low"
    return {
        "visits": visits,
        "total_score": total,
        "convertible_pct": pct,
        "verdict": verdict,
        "basis": (
            "Weights follow reported burden drivers (invasive > imaging > "
            "PK-intensive > labs/ECG); remote fit excludes invasive/PK-heavy visits."
        ),
    }
