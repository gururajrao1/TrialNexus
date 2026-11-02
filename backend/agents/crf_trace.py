"""Criterion-to-eCRF-field traceability. Deterministic, stdlib only.

Maps each audited I/E criterion (INC-xx/EXC-xx) to the posted eCRF field
names via synonym-aware token overlap: underscores in field names are
expanded first so abbreviations resolve ("anc_result" -> "absolute
neutrophil count result"). A criterion with no overlapping field is
`missing` (data never captured); otherwise `covered` with the matched
fields listed. An optional previous criterion list flags amendment drift:
removed ids and changed raw text surface as `stale`.
"""

from __future__ import annotations

import re
from typing import Any

from backend.agents.synonyms import normalize

STOPWORDS = frozenset(
    {
        "and",
        "or",
        "the",
        "of",
        "to",
        "in",
        "a",
        "an",
        "with",
        "within",
        "for",
        "from",
        "by",
        "on",
        "vs",
        "vs.",
        "than",
        "is",
        "are",
    }
)


def _tokens(text: str) -> set[str]:
    expanded = (text or "").replace("_", " ")
    toks = re.split(r"[^a-z0-9]+", normalize(expanded))
    return {t for t in toks if len(t) > 2 and t not in STOPWORDS}


def _criterion_text(criterion: dict[str, Any]) -> str:
    parts = [
        str(criterion.get("variable", "")),
        str(criterion.get("unit", "")),
        str(criterion.get("raw_text", "")),
    ]
    return " ".join(p for p in parts if p)


def trace_criteria(
    criteria: dict[str, Any],
    fields: list[str],
    previous_criteria: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Trace audited criteria to eCRF fields; flag amendment drift."""
    field_tokens = {f: _tokens(f) for f in fields}
    rows = []
    for kind in ("inclusion_criteria", "exclusion_criteria"):
        for c in criteria.get(kind, []) or []:
            wanted = _tokens(_criterion_text(c))
            matched = sorted(f for f, toks in field_tokens.items() if wanted & toks)
            rows.append(
                {
                    "id": str(c.get("id", "?")),
                    "kind": "inclusion"
                    if kind == "inclusion_criteria"
                    else "exclusion",
                    "status": "covered" if matched else "missing",
                    "matched_fields": matched,
                }
            )
    current = {
        str(c.get("id", "?")): str(c.get("raw_text", ""))
        for kind in ("inclusion_criteria", "exclusion_criteria")
        for c in criteria.get(kind, []) or []
    }
    stale = []
    for prev in previous_criteria or []:
        pid = str(prev.get("id", "?"))
        if pid not in current:
            stale.append({"id": pid, "change": "removed"})
        elif prev.get("raw_text", "") != current[pid]:
            stale.append({"id": pid, "change": "changed"})
    covered = sum(1 for r in rows if r["status"] == "covered")
    return {
        "rows": rows,
        "summary": {
            "n_criteria": len(rows),
            "covered": covered,
            "missing": len(rows) - covered,
        },
        "stale": stale,
        "basis": (
            "Synonym-aware token overlap between criterion text "
            "(variable + unit + raw text) and eCRF field names. "
            "Missing = no field captures the criterion. Stale = "
            "criterion removed or reworded since the previous audit."
        ),
    }
