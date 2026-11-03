# 03 · Cohort matching — credibility card

- **Identity:** tab-cohort · `backend/agents/cohort_matcher.py`
  (ENTAILMENT_BACKEND=rules-v1), `synonyms.py`, `relaxation_sweep.py`,
  `retention.py`, `attrition.py`, `prescreen_queue.py`.
- **Question of interest:** which records satisfy the coded I/E rules,
  and what is missing for the rest?
- **Context of use:** prescreen triage only. Inputs: FHIR R4 bundles +
  structured criteria. Outputs: ELIGIBLE/INELIGIBLE/REVIEW_REQUIRED with
  per-criterion passed/triggered/missing_data + provenance
  (exact/absent/synonym/note, confidence high/medium/low) and physician
  action items. Human sign-off: coordinator + physician.
- **Non-COU boundary:** never an enrollment or eligibility decision;
  missing data can never be marked met. Negation-aware by construction.
- **Method + determinism:** pure-function rules evaluator; seeded RNG
  only in sweep/forecast paths; same input → same output.
- **Data governance:** user/inbox FHIR only, in-memory unless stored to
  the local DB by explicit run; no PHI ships.
- **Provenance:** every verdict reaches its input span via match_type +
  confidence + evidence text.
- **Validation bar:** n2c2 fixture micro-F1 1.0 across 13 criteria;
  negation regression green ("no brain mets" must not trigger);
  missing-data → REVIEW_REQUIRED rate covered by tests.
- **Lifecycle:** re-validate on rule-engine, synonym, or backend change
  (embedding swap needs a full ML package — not covered by this card).
- **Adequacy verdict:** fit-with-controls (clinician signs).
