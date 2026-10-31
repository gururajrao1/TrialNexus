"""M11-inspired structured protocol export. Deterministic, stdlib only.

Converts an audit result into a structured study-definition package with
M11 CeSHarP-shaped sections (study, eligibility, schedule, quality). This is
a structural homage for downstream reuse (EDC setup, document generation),
not a certified ICH M11 exchange file.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List


def _coded(criteria: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{
        "id": c.get("id"), "category": c.get("category"),
        "variable": c.get("variable"), "operator": c.get("operator"),
        "value": c.get("value"), "unit": c.get("unit"),
        "flexibility": c.get("flexibility_rating"),
    } for c in criteria]


def build_structure(
    audit: Dict[str, Any], protocol_id: str, raw_text: str = ""
) -> Dict[str, Any]:
    """Build the structured package from an audit result."""
    md = audit.get("protocol_metadata", {}) or {}
    days = sorted({int(d) for d in re.findall(r"\bDay\s+(\d+)", raw_text, re.IGNORECASE)})
    return {
        "documentType": "TrialNexus Structured Protocol v1",
        "m11Mapping": ("ICH M11 CeSHarP-inspired sections (study, eligibility, "
                       "schedule, quality); structural homage, not a certified file"),
        "study": {
            "id": protocol_id,
            "title": md.get("title", "Untitled"),
            "phase": md.get("phase", "Unknown"),
            "indication": md.get("primary_indication", "Unknown"),
            "targetEnrollment": md.get("target_enrollment", 0),
        },
        "eligibility": {
            "inclusion": _coded(audit.get("inclusion_criteria", [])),
            "exclusion": _coded(audit.get("exclusion_criteria", [])),
        },
        "schedule": {
            "visit_days": days,
            "note": "Day numbers extracted from text; see burden endpoint for scored analysis",
        },
        "quality": {
            "fragility_index": audit.get("protocol_fragility_index", 0),
            "amendment_exposure_usd": audit.get("amendment_exposure_usd", 0),
            "operational_flaws": audit.get("operational_flaws", []),
        },
        "generated_at": date.today().isoformat(),
    }
