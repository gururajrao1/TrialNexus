# 04 · Safety triage — credibility card

- **Identity:** tab-safety · `backend/agents/safety_triage.py`,
  `signal_detection.py`, `lock_readiness.py`, `crf_trace.py`,
  `pubmed.py`, `real_data.py` (openFDA).
- **Question of interest:** what needs a clock, what needs a query, and
  is the database ready to lock?
- **Context of use:** safety operations triage. Inputs: AE records.
  Outputs: SAE flags with reporting clocks, MedDRA-style SOC/grade
  mapping, site queries, PRR/ROR screen with BH q-values + IC shrinker,
  lock-readiness RAG. Human sign-off: drug safety + PI.
- **Non-COU boundary:** flags clock and draft; humans file. The SOC/PT
  map is a keyword map, not licensed MedDRA — never imply MedDRA
  coverage. PRR/ROR/q-values are screening signals, never confirmatory.
- **Method + determinism:** keyword + rule engine; Evans criteria +
  ROR CI + BH-FDR (screening) + fixed-prior IC; seeded where random;
  same input → same output.
- **Data governance:** user AE data; openFDA counts carry source+date
  labels; cache/offline fallback.
- **Provenance:** every flag cites term, SOC/PT, grade, clock arithmetic.
- **Validation bar:** zero silent SAE misses on fixtures (seeded SAE
  must flag with clock + drafted query); SOC/grade mapping precision
  tests green; known-table PRR/chi2 math pinned.
- **Lifecycle:** re-validate on keyword map, clock, or threshold change.
- **Adequacy verdict:** fit-with-controls (safety sign-off mandatory).
