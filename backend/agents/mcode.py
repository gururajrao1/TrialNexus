"""mCODE-inspired oncology profile extraction. Deterministic, stdlib only.

Pulls Minimal Common Oncology Data Elements-style fields (cancer type,
stage, histology, biomarkers, performance status, metastasis sites) from a
FHIR bundle and scores completeness. Field names echo mCODE; this is not a
certified mCODE exporter.
"""

from __future__ import annotations

import re
from typing import Any

_BIOMARKERS = (
    "EGFR",
    "HER2",
    "PD-L1",
    "PDL1",
    "ALK",
    "KRAS",
    "BRCA1",
    "BRCA2",
    "ROS1",
    "BRAF",
    "MSI",
    "TMB",
)
_METS = ("brain", "bone", "liver", "lung", "adrenal")


def _texts(bundle: dict[str, Any]) -> list[str]:
    out = []
    for e in bundle.get("entry", []) if isinstance(bundle, dict) else []:
        r = e.get("resource", {}) if isinstance(e, dict) else {}
        rt = r.get("resourceType")
        if rt == "Condition":
            code = r.get("code", {}) if isinstance(r.get("code"), dict) else {}
            if code.get("text"):
                out.append(str(code["text"]))
        elif rt == "Observation":
            code = r.get("code", {}) if isinstance(r.get("code"), dict) else {}
            if code.get("text"):
                out.append(str(code["text"]))
    return out


def _marker_present(blob: str, low: str, marker: str) -> bool:
    """Word-boundary marker match.

    EGFR is case-sensitive on purpose: the kidney lab eGFR (lowercase e,
    estimated glomerular filtration rate) is not the EGFR gene (HGNC
    symbols are uppercase). Other markers match case-insensitively.
    """
    if marker == "EGFR":
        return re.search(r"\bEGFR\b", blob) is not None
    return re.search(r"\b" + re.escape(marker.lower()) + r"\b", low) is not None


def _ecog(bundle: dict[str, Any]) -> str:
    for e in bundle.get("entry", []) if isinstance(bundle, dict) else []:
        r = e.get("resource", {}) if isinstance(e, dict) else {}
        if r.get("resourceType") != "Observation":
            continue
        code = r.get("code", {}) if isinstance(r.get("code"), dict) else {}
        if (
            "ecog" in str(code.get("text", "")).lower()
            and r.get("valueInteger") is not None
        ):
            return str(r["valueInteger"])
    return "not documented"


def mcode_profile(bundle: dict[str, Any]) -> dict[str, Any]:
    """Extract the oncology profile + completeness score."""
    texts = _texts(bundle)
    blob = " | ".join(texts)
    low = blob.lower()
    cancer = next(
        (
            t
            for t in texts
            if "protocol" not in t.lower()
            and re.search(
                r"cancer|carcinoma|melanoma|lymphoma|leukemia|nsclc|sclc",
                t,
                re.IGNORECASE,
            )
        ),
        "not documented",
    )
    m = re.search(r"stage\s*([0-4ivx]+)", low)
    if m:
        stage = "Stage " + m.group(1).upper()
    elif "metastatic" in low:
        stage = "IV (inferred: metastatic)"
    else:
        stage = "not documented"
    if "non-small cell" in low or "non small cell" in low:
        hist = "non-small cell"
    else:
        hist = next(
            (
                h
                for h in (
                    "adenocarcinoma",
                    "squamous",
                    "ductal",
                    "lobular",
                    "small cell",
                    "large cell",
                )
                if re.search(r"\b" + re.escape(h) + r"\b", low)
            ),
            "not documented",
        )
    biomarkers = sorted({b for b in _BIOMARKERS if _marker_present(blob, low, b)})
    ecog = _ecog(bundle)
    mets = sorted({s for s in _METS if s in low and "metasta" in low})
    fields = {
        "cancer_type": cancer,
        "stage": stage,
        "histology": hist,
        "biomarkers": biomarkers,
        "ecog": ecog,
        "metastasis_sites": mets,
    }
    present = sum(
        1 for k, v in fields.items() if v and v != "not documented" and v != []
    )
    total = len(fields)
    gaps = [k for k, v in fields.items() if (not v) or v == "not documented" or v == []]
    return {
        "profile": fields,
        "completeness_pct": round(100.0 * present / total, 1),
        "gaps": gaps,
        "note": "mCODE-inspired field names; completeness = documented / 6 fields.",
    }
