"""Optional LLM rationale annotations over deterministic evaluations.

Rules-v1 (cohort_matcher) remains the sole writer of verdicts. This module
only appends *advisory* annotations drafted by a local model through
ZeroCostRouter (Ollama on localhost when present, deterministic stub
otherwise — no keys, no cloud, no PHI egress). Every annotation is
verified before display: strict JSON, verbatim quotes from the cited
evidence, and a verdict restatement that must agree with the
deterministic outcome. Anything else fails closed to null + warning.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

MAX_RATIONALE_WORDS = 150

SYSTEM_PROMPT = (
    "You draft a one-paragraph advisory rationale for a clinical trial "
    "eligibility check. Reply with strict JSON only, no other text: "
    '{"rationale": "<=150 words, plain language", '
    '"quotes": ["<verbatim substrings of the evidence span>"], '
    '"verdict": "met|not_met"}. '
    "Quote ONLY the evidence span provided. The verdict MUST restate the "
    "given deterministic outcome. This is a draft for human review, never "
    "a decision."
)


def build_prompt(
    criterion_id: str,
    raw_text: str,
    evidence: str,
    passed: bool,
) -> str:
    """Server-side prompt: cited snippet only, verdict stated up front."""
    verdict = "met" if passed else "not_met"
    return (
        f"criterion {criterion_id}: {raw_text}\n"
        f"deterministic outcome: {verdict}\n"
        f"evidence span: {evidence}\n"
        "Draft the advisory rationale JSON."
    )


def _truncate(words: str) -> tuple[str, bool]:
    parts = words.split()
    if len(parts) <= MAX_RATIONALE_WORDS:
        return words, False
    return " ".join(parts[:MAX_RATIONALE_WORDS]), True


def verify_response(
    response: Any, evidence: str, passed: bool
) -> tuple[dict[str, Any] | None, str | None]:
    """Verify a router response. Returns (rationale, warning)."""
    expected = "met" if passed else "not_met"
    if not isinstance(response, dict):
        return None, "untrusted"
    rationale = response.get("rationale")
    quotes = response.get("quotes")
    verdict = response.get("verdict")
    if (
        not isinstance(rationale, str)
        or not rationale.strip()
        or not isinstance(quotes, list)
        or not all(isinstance(q, str) and q and q in evidence for q in quotes)
        or verdict != expected
    ):
        if verdict != expected:
            return None, "verdict_mismatch"
        return None, "untrusted"
    text, truncated = _truncate(rationale.strip())
    return (
        {
            "text": text,
            "quotes": quotes,
            "verdict_agrees": True,
            "truncated": truncated,
            "label": "AI draft - verify against protocol",
        },
        None,
    )


def annotate_evaluations(
    evals: list[dict[str, Any]],
    call_model: Callable[[str, str], dict[str, Any]] | None,
    kind: str,
    max_criteria: int,
    budget: list[int],
) -> list[dict[str, Any]]:
    """Attach verified annotations to evaluation dicts (top-K cap).

    call_model(system, user) returns the router dict; None disables the
    layer. budget is a single-item list tracking remaining call count so
    inclusion + exclusion lists share one cap. Never raises: model
    failures become null rationale + warning codes.
    """
    out = []
    for e in evals:
        annotated = dict(e)
        if call_model is None:
            annotated["llm_rationale"] = None
            annotated["llm_warning"] = "llm_disabled"
        elif budget[0] <= 0:
            annotated["llm_rationale"] = None
            annotated["llm_warning"] = "llm_skipped_top_k"
        else:
            budget[0] -= 1
            passed = (
                bool(e.get("passed", False))
                if kind == "inclusion"
                else not bool(e.get("triggered", False))
            )
            evidence = str(e.get("clinical_evidence_found", "") or "")
            prompt = build_prompt(
                str(e.get("criterion_id", "?")),
                str(e.get("raw_text", e.get("criterion_id", "?"))),
                evidence,
                passed,
            )
            try:
                response = call_model(SYSTEM_PROMPT, prompt)
            except Exception:
                response = None
            rationale, warning = verify_response(response, evidence, passed)
            annotated["llm_rationale"] = rationale
            annotated["llm_warning"] = warning
        out.append(annotated)
    return out


def annotate_results(
    results: dict[str, Any],
    call_model: Callable[[str, str], dict[str, Any]] | None,
    max_criteria: int = 6,
) -> dict[str, Any]:
    """Annotate inclusion + exclusion evaluations under one shared cap."""
    budget = [max(0, int(max_criteria))]
    annotated = dict(results)
    annotated["inclusion_evaluations"] = annotate_evaluations(
        list(results.get("inclusion_evaluations", []) or []),
        call_model,
        "inclusion",
        max_criteria,
        budget,
    )
    annotated["exclusion_evaluations"] = annotate_evaluations(
        list(results.get("exclusion_evaluations", []) or []),
        call_model,
        "exclusion",
        max_criteria,
        budget,
    )
    return annotated
