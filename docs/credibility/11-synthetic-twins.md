# 11 · Synthetic twins — credibility card

- **Identity:** tab-twins · `backend/agents/twin_generator.py`
  (MAX_TWINS=2000, jitter clamped 0–0.5).
- **Question of interest:** how sensitive is eligibility to
  measurement noise?
- **Context of use:** design exploration only. Inputs: one FHIR bundle
  + n/seed/jitter. Outputs: eligibility distribution, Wilson 95% CI,
  Monte-Carlo SE, per-criterion flip counts. Human sign-off: study
  team interprets fragility, nothing more.
- **Non-COU boundary:** jitter twins are Monte Carlo sensitivity on one
  patient's own observations — NOT prognostic digital twins (no
  population model, no outcome prediction, no treatment-effect
  estimand). Never efficacy or safety, on every output.
- **Method + determinism:** uniform jitter, seeded RNG; same
  seed → same distribution; jitter=0 reproduces the index patient.
- **Data governance:** in-memory synthetic clones; nothing stored.
- **Provenance:** n/seed/jitter/CI/MCSE/flip table on every run.
- **Validation bar:** contract + cap + Wilson-ordering + flip-schema
  + jitter-zero + determinism + prespec tests green. Empirical
  per-analyte bands and correlated/lognormal noise stay gated: no
  stored lab-repeat data, no declared joint-distribution validation.
- **Lifecycle:** re-validate on generator, jitter, or evaluator
  change. Twin scores must never enter a treatment-effect model.
- **Adequacy verdict:** fit-with-controls (fragility input only).
