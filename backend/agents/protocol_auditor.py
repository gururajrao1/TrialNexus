"""Agent 1 - Protocol Auditor. Deterministic I/E parsing + fragility scoring.

Pure functions: no network, no model calls, stdlib only.
Output matches the cookbook JSON contract.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

CATEGORY_KEYWORDS = [
    ("Demographic", ["age", "aged", "male", "female", "sex", "gender"]),
    ("Biomarker", ["mutation", "her2", "pd-l1", "pdl1", "alk", "kras", "biomarker",
                   "ihc", "fish", "ngs", "exon", "l858r", "egfr"]),
    ("Prior Treatment", ["prior", "previous", "chemotherapy", "tki", "tyrosine kinase",
                         "radiotherapy", "washout", "treatment"]),
    ("Renal", ["creatinine", "crcl", "creatinine clearance", "renal", "kidney", "gfr"]),
    ("Hepatic", ["alt", "ast", "bilirubin", "hepatic", "liver", "transaminase"]),
    ("Hematologic", ["neutrophil", "anc", "platelet", "hemoglobin", "anemia",
                     "leukocyte", "wbc", "marrow"]),
    ("Performance Status", ["ecog", "performance status", "karnofsky"]),
    ("Cardiac", ["qtc", "cardiac", "heart", "lvef", "failure", "arrhythmia",
                 "myocardial", "cardiovascular"]),
    ("CNS", ["brain", "cns", "metastas", "spinal cord", "seizure"]),
    ("Pregnancy", ["pregnan", "breastfeeding", "lactat", "contracept"]),
    ("Histology", ["histolog", "cytolog", "nsclc", "sclc", "adenocarcinoma",
                   "squamous", "stage", "metastatic"]),
]

AMBIGUOUS_PHRASES = ["adequate", "clinically significant", "appropriate",
                     "acceptable", "investigator", "discretion", "suitable"]
RIGID_PHRASES = ["must", "shall", "required", "mandatory", "strictly"]

SCI_RE = re.compile(
    r"(?P<var>[A-Za-z][\w .\-/()]{1,40}?)\s*(?P<op>>=|<=|>|<|=)\s*"
    r"(?P<val>\d+(?:\.\d+)?)\s*x\s*10\^9\s*/\s*L",
    re.IGNORECASE,
)
COMPARE_RE = re.compile(
    r"(?P<var>[A-Za-z][A-Za-z0-9 .\-/()]{1,48}?)\s*(?P<op>>=|<=|>|<|=)\s*"
    r"(?P<val>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>g/dL|mg/dL|U/L|/uL|mL/min|msec|ms\b|years|days|x ULN|ULN)?",
    re.IGNORECASE,
)
ITEM_RE = re.compile(r"^\s*(?:\(?(\d+)\)?[\.\)]\s+|\-\s+)(.+)$")


def _has(blob: str, *keywords: str) -> bool:
    """Left word-boundary match: 'ast' must not match 'metastatic'."""
    return any(re.search(r"\b" + re.escape(k.strip()), blob) for k in keywords)


def _categorize(text: str) -> str:
    low = text.lower()
    for cat, kws in CATEGORY_KEYWORDS:
        if _has(low, *kws):
            return cat
    return "Other"


def _flexibility(text: str) -> str:
    low = text.lower()
    if any(p in low for p in AMBIGUOUS_PHRASES):
        return "Ambiguous"
    if any(p in low for p in RIGID_PHRASES):
        return "Rigid"
    return "Negotiable"


def _parse_rule(text: str) -> Tuple[str, str, Any, Optional[str]]:
    sci = SCI_RE.search(text)
    if sci:
        return (sci.group("var").strip(" ."), sci.group("op"),
                float(sci.group("val")), "x10^9/L")
    m = COMPARE_RE.search(text)
    if m:
        raw_val = m.group("val")
        val: Any = float(raw_val) if "." in raw_val else int(raw_val)
        unit = (m.group("unit") or "").strip() or None
        return m.group("var").strip(" ."), m.group("op"), val, unit
    low = text.lower()
    if " or " in low and ("ecog" in low or "performance" in low):
        nums = [int(n) for n in re.findall(r"\b[0-4]\b", text)]
        if nums:
            return "ECOG", "IN", nums, None
    return text[:60].strip(), "==", "present", None


def _split_sections(raw: str) -> Tuple[List[str], List[str]]:
    inc: List[str] = []
    exc: List[str] = []
    current: Optional[List[str]] = None
    pending: Optional[str] = None
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if "exclusion" in low and "criteria" in low:
            if pending and current is not None:
                current.append(pending.strip())
            pending, current = None, exc
            continue
        if "inclusion" in low and "criteria" in low:
            if pending and current is not None:
                current.append(pending.strip())
            pending, current = None, inc
            continue
        m = ITEM_RE.match(s)
        if m and current is not None:
            if pending:
                current.append(pending.strip())
            pending = m.group(2)
        elif current is not None and pending is not None:
            pending += " " + s
    if pending and current is not None:
        current.append(pending.strip())
    return inc, exc


def _metadata(raw: str) -> Dict[str, Any]:
    title = "Untitled protocol"
    m = re.search(r"protocol\s+title\s*:\s*(.+)", raw, re.IGNORECASE)
    if m:
        title = m.group(1).strip()
    phase = "Unknown"
    m = re.search(r"\bPhase\s*([1234](?:\s*/\s*Phase\s*[1234])?)\b", raw, re.IGNORECASE)
    if m:
        phase = "Phase " + m.group(1)
    indication = "Unknown"
    m = re.search(r"indication\s*:\s*(.+)", raw, re.IGNORECASE)
    if m:
        indication = m.group(1).strip()
    else:
        low = raw.lower()
        if "non-small cell lung cancer" in low or "nsclc" in low:
            indication = "Non-Small Cell Lung Cancer"
        elif "breast cancer" in low:
            indication = "Breast Cancer"
    enrollment = 0
    m = re.search(r"target\s+enrollment\s*:\s*(\d+)", raw, re.IGNORECASE)
    if m:
        enrollment = int(m.group(1))
    return {"title": title, "phase": phase, "primary_indication": indication,
            "target_enrollment": enrollment}


def _audit_operations(
    raw: str, inc: List[str], exc: List[str]
) -> List[Dict[str, Any]]:
    flaws: List[Dict[str, Any]] = []
    days = sorted({int(d) for d in re.findall(r"\bDay\s+(\d+)", raw, re.IGNORECASE)})
    for a, b in zip(days, days[1:]):
        if 0 < b - a <= 2:
            flaws.append({
                "domain": "Schedule_of_Assessments",
                "description": (f"Visit windows Day {a} and Day {b} are {b - a} day(s) "
                                "apart; overlapping +/- windows likely."),
                "suggested_remediation": (f"Merge or separate Day {a}/Day {b} "
                                          "assessments with non-overlapping windows."),
                "amendment_risk_score": 0.6,
            })
    if len(re.findall(r"\bpk\b|pharmacokinetic", raw, re.IGNORECASE)) >= 4:
        flaws.append({
            "domain": "Schedule_of_Assessments",
            "description": "High PK sampling burden detected (4+ PK mentions).",
            "suggested_remediation": "Consolidate PK draws; justify each timepoint.",
            "amendment_risk_score": 0.55,
        })
    for i, crit in enumerate(inc + exc):
        hits = sum(1 for p in AMBIGUOUS_PHRASES if p in crit.lower())
        if hits >= 2:
            flaws.append({
                "domain": "Ambiguity",
                "description": (f"Criterion {i + 1} stacks subjective qualifiers: "
                                f"{crit[:100]}..."),
                "suggested_remediation": "Replace qualifiers with numeric thresholds.",
                "amendment_risk_score": 0.5,
            })
    if not re.search(r"contracept|pregnan", raw, re.IGNORECASE):
        flaws.append({
            "domain": "Regulatory_Risk",
            "description": "No pregnancy/contraception criterion detected.",
            "suggested_remediation": "Add standard pregnancy testing requirements.",
            "amendment_risk_score": 0.7,
        })
    return flaws


def _syllables(word: str) -> int:
    return max(1, len(re.findall(r"[aeiouy]+", word.lower())))


def _readability(raw_text: str, criteria: List[str]) -> Dict[str, Any]:
    words = re.findall(r"[A-Za-z']+", raw_text)
    sentences = max(1, len([s for s in re.split(r"[.!?]+", raw_text) if s.strip()]))
    w = max(1, len(words))
    syl = sum(_syllables(x) for x in words)
    ease = round(206.835 - 1.015 * (w / sentences) - 84.6 * (syl / w), 1)
    grade = round(0.39 * (w / sentences) + 11.8 * (syl / w) - 15.59, 1)
    entities = len(re.findall(r"\b\d+(?:\.\d+)?\b|[A-Z]{2,}", raw_text))
    longies = [i + 1 for i, c in enumerate(criteria) if len(c.split()) > 40]
    return {"flesch_ease": ease, "flesch_kincaid_grade": grade,
            "entity_density_per_100w": round(100.0 * entities / w, 1),
            "long_criteria": longies,
            "basis": ("Flesch readability + entity density; dense/hard criteria "
                      "predict amendments and site deviations")}


def parse_protocol(raw_text: str) -> Dict[str, Any]:
    """Parse raw protocol text into the cookbook audit JSON."""
    inc_raw, exc_raw = _split_sections(raw_text)
    inclusions: List[Dict[str, Any]] = []
    for i, text in enumerate(inc_raw, 1):
        var, op, val, unit = _parse_rule(text)
        inclusions.append({"id": f"INC-{i:02d}", "raw_text": text,
                           "category": _categorize(text), "variable": var,
                           "operator": op, "value": val, "unit": unit,
                           "flexibility_rating": _flexibility(text)})
    exclusions: List[Dict[str, Any]] = []
    for i, text in enumerate(exc_raw, 1):
        var, op, val, unit = _parse_rule(text)
        exclusions.append({"id": f"EXC-{i:02d}", "raw_text": text,
                           "category": _categorize(text), "variable": var,
                           "operator": op, "value": val, "unit": unit,
                           "flexibility_rating": _flexibility(text)})
    flaws = _audit_operations(raw_text, inc_raw, exc_raw)
    ambiguous = sum(1 for c in inclusions + exclusions
                    if c["flexibility_rating"] == "Ambiguous")
    fragility = min(100.0, round(len(flaws) * 8.0 + ambiguous * 4.0
                                 + (len(inclusions) + len(exclusions)) * 0.5, 1))
    exposure = int(round(fragility / 100.0 * 535000, -3))
    complexity = _readability(raw_text, inc_raw + exc_raw)
    return {"protocol_metadata": _metadata(raw_text),
            "inclusion_criteria": inclusions,
            "exclusion_criteria": exclusions,
            "operational_flaws": flaws,
            "protocol_fragility_index": fragility,
            "amendment_exposure_usd": exposure,
            "exposure_basis": "Tufts CSDD median direct cost $535K per substantial Phase III amendment",
            "complexity": complexity}
