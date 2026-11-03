# 09 · Find trials — credibility card

- **Identity:** tab-finder · `backend/agents/trial_finder.py`.
- **Question of interest:** which trial fits this patient?
- **Context of use:** prescreen signposting. Inputs: one FHIR bundle +
  protocol set. Outputs: ranked trials with blocking criteria named.
  Human sign-off: coordinator + physician.
- **Non-COU boundary:** ranking is not a referral or eligibility
  decision; both views reuse the cohort evaluator so they cannot
  disagree by construction.
- **Method + determinism:** same rules-v1 evaluator as cohort
  matching; deterministic ranking.
- **Data governance:** user bundle only.
- **Provenance:** every rank cites match percentage + blocking rules.
- **Validation bar:** cross-view agreement tests green (finder vs
  cohort on shared bundles).
- **Lifecycle:** re-validate on evaluator or ranking change.
- **Adequacy verdict:** fit-with-controls (clinician signs).
