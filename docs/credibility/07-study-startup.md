# 07 · Study startup — credibility card

- **Identity:** tab-startup · `backend/agents/startup_tracker.py`.
- **Question of interest:** where is activation stuck?
- **Context of use:** startup oversight. Inputs: site stage history.
  Outputs: per-site stage, days-in-stage vs contract/IRB/activation
  benchmarks, at-risk flags. Human sign-off: startup lead.
- **Non-COU boundary:** flags start conversation; they are not
  financial or contractual findings.
- **Method + determinism:** threshold-vs-benchmark arithmetic; no RNG.
- **Data governance:** user stage data, local only.
- **Provenance:** every flag cites days counted and benchmark used.
- **Validation bar:** benchmark-crossing fixtures green.
- **Lifecycle:** re-validate on benchmark or stage-model change.
- **Adequacy verdict:** fit (informational).
