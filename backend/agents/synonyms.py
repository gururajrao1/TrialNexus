"""Curated clinical synonym table (UMLS-lite). Deterministic, stdlib only.

Maps common variants to canonical phrases so exact matching survives
vocabulary differences ("MI" vs "myocardial infarction"). Applied to both
patient text and criterion text before term matching. Deliberately small
and reviewable; extend by editing SYNONYMS.
"""

from __future__ import annotations

import re

SYNONYMS = {
    "myocardial infarction": ["mi", "heart attack", "stemi", "nstemi"],
    "hypertension": ["htn", "high blood pressure"],
    "type 2 diabetes mellitus": ["t2dm", "type 2 diabetes", "dm2"],
    "type 1 diabetes mellitus": ["t1dm", "type 1 diabetes", "dm1"],
    "non-small cell lung cancer": ["nsclc"],
    "small cell lung cancer": ["sclc"],
    "heart failure": ["hf", "cardiac failure", "chf", "congestive heart failure"],
    "chronic kidney disease": ["ckd"],
    "atrial fibrillation": ["afib", "a-fib"],
    "deep vein thrombosis": ["dvt"],
    "pulmonary embolism": ["pe"],
    "cerebrovascular accident": ["cva", "stroke"],
    "chronic obstructive pulmonary disease": ["copd"],
    "coronary artery disease": ["cad"],
    "hemoglobin a1c": ["hba1c", "a1c", "hgba1c"],
    "absolute neutrophil count": ["anc"],
    "white blood cell": ["wbc"],
    "red blood cell": ["rbc"],
    "electrocardiogram": ["ecg", "ekg"],
    "body mass index": ["bmi"],
    "tyrosine kinase inhibitor": ["tki"],
    "computed tomography": ["ct scan"],
    "magnetic resonance imaging": ["mri"],
}

_SORTED = sorted(
    ((v, c) for c, vs in SYNONYMS.items() for v in vs),
    key=lambda p: len(p[0]),
    reverse=True,
)


def normalize(text: str) -> str:
    """Lowercase text with known variants replaced by canonical phrases."""
    out = text.lower()
    for variant, canon in _SORTED:
        out = re.sub(r"\b" + re.escape(variant) + r"\b", canon, out)
    return out
