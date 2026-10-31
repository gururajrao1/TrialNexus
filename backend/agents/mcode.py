"""mCODE-inspired oncology profile extraction. Deterministic, stdlib only.

Pulls Minimal Common Oncology Data Elements-style fields (cancer type,
stage, histology, biomarkers, performance status, metastasis sites) from a
FHIR bundle and scores completeness. Field names echo mCODE; this is not a
certified mCODE exporter.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_BIOMARKERS = ("EGFR", "HER2", "PD-L1", "PDL1", "ALK", "KRAS", "BRCA1", "BRCA2",
               "ROS1", "BRAF", "MSI", "TMB")
_METS = ("brain", "bone", "liver", "lung", "adrenal")


def _texts(bundle: Dict[str, Any]) -> List[str]:
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


def _ecog(bundle: Dict[str, Any]) -> str:
    for e in bundle.get("entry", []) if isinstance(bundle, dict) else []:
        r = e.get("resource", {}) if isinstance(e, dict) else {}
        if r.get("resourceType") != "Observation":
            continue
        code = r.get("code", {}) if isinstance(r.get("code"), dict) else {}
        if "ecog" in str(code.get("text", "")).lower() and r.get("valueInteger") is not None:
            return str(r["valueInteger"])
    return "not documented"


def mcode_profile(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the oncology profile + completeness score."""
    texts = _texts(bundle)
    blob = " | ".join(texts)
    low = blob.lower()
    cancer = next((t for t in texts if re.search(
        r"cancer|carcinoma|melanoma|lymphoma|leukemia|nsclc|sclc", t, re.IGNORECASE)),
        "not documented")
    m = re.search(r"stage\s*([0-4ivx]+)", low)
    if m:
        stage = "Stage " + m.group(1).upper()
    elif "metastatic" in low:
        stage = "IV (inferred: metastatic)"
    else:
        stage = "not documented"
    hist = next((h for h in ("adenocarcinoma", "squamous", "ductal", "lobular",
                             "small cell", "large cell") if h in low), "not documented")
    biomarkers = sorted({b for b in _BIOMARKERS if b.lower() in low})
    ecog = _ecog(bundle)
    mets = sorted({s for s in _METS if s in low and "metasta" in low})
    fields = {"cancer_type": cancer, "stage": stage, "histology": hist,
              "biomarkers": biomarkers, "ecog": ecog, "metastasis_sites": mets}
    present = sum(1 for k, v in fields.items()
                  if v and v != "not documented" and v != [])
    total = len(fields)
    gaps = [k for k, v in fields.items()
            if (not v) or v == "not documented" or v == []]
    return {"profile": fields, "completeness_pct": round(100.0 * present / total, 1),
            "gaps": gaps,
            "note": "mCODE-inspired field names; completeness = documented / 6 fields."}
