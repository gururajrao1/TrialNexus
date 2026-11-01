"""Plain-language consent helper. Deterministic, stdlib only.

eConsent-comprehension support: flags long sentences and trial jargon
in consent/protocol text and suggests plain alternatives from a small
built-in glossary. Scores 0-100 so teams can track drafts. Works on
any pasted text, not just stored protocols.
"""

from __future__ import annotations

import re
from typing import Any

JARGON = (
    ("randomization", "assigned by chance, like a coin flip"),
    ("randomized", "assigned by chance, like a coin flip"),
    ("placebo", "inactive pill with no medicine in it"),
    ("pharmacokinetics", "how the drug moves through your body over time"),
    ("adverse event", "side effect"),
    ("serious adverse event", "serious side effect needing hospital care"),
    ("efficacy", "whether the drug works"),
    ("biopsy", "removal of a small tissue sample for testing"),
    ("infusion", "medicine given slowly through a vein (a drip)"),
    ("titration", "slowly adjusting the dose to find the right level"),
    ("contraindication", "a reason you must not take the drug"),
    ("washout period", "a break to let earlier drugs leave your body"),
    ("double-blind", "neither you nor the study doctor knows which drug you get"),
    ("standard of care", "the usual treatment doctors already give"),
)

LONG_WORDS = 15


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if len(p.split()) >= 3]


def _claim_spans(
    low: str, term: str, claimed: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Occurrences of term that do not overlap already-claimed spans."""
    fresh = []
    for m in re.finditer(re.escape(term), low):
        span = (m.start(), m.end())
        if not any(s < span[1] and span[0] < e for s, e in claimed):
            fresh.append(span)
    return fresh


def check_consent(text: str) -> dict[str, Any]:
    """Flag long sentences + jargon with plain alternatives."""
    sents = _sentences(text)
    long = [
        {"excerpt": " ".join(s.split()[:14]) + "…", "words": len(s.split())}
        for s in sents
        if len(s.split()) > LONG_WORDS
    ][:10]
    low = text.lower()
    # Longest terms first so "serious adverse event" claims its span before
    # the shorter "adverse event" can double-count the same words.
    claimed: list[tuple[int, int]] = []
    hits = []
    for term, plain in sorted(JARGON, key=lambda jp: -len(jp[0])):
        spans = _claim_spans(low, term, claimed)
        if spans:
            claimed.extend(spans)
            hits.append({"term": term, "plain": plain, "count": len(spans)})
    hits.sort(key=lambda h: -h["count"])
    score = max(0, 100 - 4 * len(long) - 3 * sum(h["count"] for h in hits))
    suggestions = (
        [f"Split sentences over {LONG_WORDS} words into two short ones."]
        if long
        else []
    ) + ([f"Replace '{h['term']}' with '{h['plain']}'." for h in hits[:5]])
    return {
        "score": score,
        "n_sentences": len(sents),
        "long_sentences": long,
        "jargon_hits": hits,
        "suggestions": suggestions,
        "basis": (
            "eConsent comprehension pattern: short sentences + no unexplained "
            "jargon. 4 points per long sentence, 3 per jargon use."
        ),
    }
