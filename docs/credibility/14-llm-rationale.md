# 14 · LLM rationale (optional) — credibility card

- **Identity:** `POST /api/match/explain` ·
  `backend/agents/llm_rationale.py` over `backend/router.py`
  (ZeroCostRouter: local Ollama when present, deterministic stub
  otherwise).
- **Question of interest:** can a model draft a readable rationale for
  an already-decided criterion?
- **Context of use:** advisory annotation only, behind
  `TRIALNEXUS_LLM_ENABLED=1` (default off). Inputs: deterministic
  evaluations. Outputs: same evaluations + verified `llm_rationale`
  or null + warning code. Human sign-off: reviewer reads the draft
  against the protocol.
- **Non-COU boundary:** rules-v1 is the sole writer of verdicts; the LLM
  never flips, never sorts, never sees free text beyond the cited
  snippet. No keys, no cloud, no PHI egress (localhost only).
- **Method + determinism:** prompt built server-side with the stated
  verdict; strict-JSON parse, verbatim-quote enforcement, verdict-echo
  check; fail-closed on disabled/timeout/malformed/mismatch.
- **Data governance:** only the criterion's cited snippet leaves the
  box, and only when explicitly enabled.
- **Provenance:** every annotation carries model + prompt-hash audit;
  label reads "AI draft - verify against protocol".
- **Validation bar:** stub-transport tests green (agree/mismatch/
  malformed/non-verbatim/error/disabled/cap/truncation); verdicts
  unchanged with layer on or off.
- **Lifecycle:** re-validate on prompt, guardrail, or router change.
- **Adequacy verdict:** fit-with-controls (human review mandatory;
  layer ships disabled).
