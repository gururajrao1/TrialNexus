# 12 · mCODE summary — credibility card

- **Identity:** tab-mcode · `backend/agents/mcode.py`.
- **Question of interest:** is the oncology record complete?
- **Context of use:** chart-abstraction aid. Inputs: one FHIR bundle.
  Outputs: cancer type/stage/histology/biomarkers/ECOG/mets +
  completeness percentage + gaps. Human sign-off: abstractor/clinician.
- **Non-COU boundary:** mCODE-*inspired* extraction, not a certified
  mCODE exporter; case-sensitive EGFR rule and protocol-text exclusion
  are documented heuristics.
- **Method + determinism:** regex/keyword extraction; no RNG.
- **Data governance:** user bundle only.
- **Provenance:** every field traces to cited bundle text.
- **Validation bar:** histology, eGFR-exclusion, and protocol-text
  regression tests green.
- **Lifecycle:** re-validate on extraction-rule change.
- **Adequacy verdict:** fit (informational abstraction).
