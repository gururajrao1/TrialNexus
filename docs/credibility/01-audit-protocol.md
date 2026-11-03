# 01 · Protocol audit — credibility card

- **Identity:** tab-audit · `backend/agents/protocol_auditor.py`,
  `burden_scorer.py`, `dct_readiness.py`, `criteria_feedback.py`,
  `adaptive_design.py`, `consent_helper.py`, `risk_models.py` (outlook),
  `structured_export.py`.
- **Question of interest:** will this protocol need an amendment, and
  where are its operational weak points?
- **Context of use:** pre-enrollment design review. Inputs: protocol text
  (or PDF). Outputs: fragility index, amendment exposure, coded I/E
  tables, burden/DCT/adaptive/consent analyses. Human sign-off: sponsor
  study team.
- **Non-COU boundary:** not a regulatory submission; exposure dollars are
  planning estimates, never budget commitments.
- **Method + determinism:** regex/NLP-lite parser, disclosed weights,
  Lan-DeMets spending tables; seeded RNG; same input → same output.
- **Data governance:** user-supplied protocol text; nothing retained
  beyond the session except explicit saves.
- **Provenance:** every criterion row cites its evidence span; every
  number cites its basis string.
- **Validation bar:** worked-example regression green (fragility 20.5/Low,
  exposure ≈ $110K of $535K median); adaptive boundaries match textbook
  OBF/Pocock constants to ~0.01.
- **Lifecycle:** re-validate on parser/weight/threshold change.
- **Adequacy verdict:** fit-with-controls (team review required).
