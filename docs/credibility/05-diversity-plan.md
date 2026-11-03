# 05 · Diversity plan — credibility card

- **Identity:** tab-diversity · `backend/agents/diversity_planner.py`.
- **Question of interest:** can we defend our enrollment mix?
- **Context of use:** FDORA Diversity Action Plan arithmetic. Inputs:
  enrolled bundles + target mix. Outputs: per-dimension gaps,
  on-track/at-risk/behind/off-track status, catch-up numbers, focus
  areas. Human sign-off: sponsor diversity lead.
- **Non-COU boundary:** arithmetic support, not a regulatory filing;
  targets are illustrative defaults unless replaced with protocol DAP.
- **Method + determinism:** pure-function gap arithmetic; no RNG.
- **Data governance:** user bundle demographics only.
- **Provenance:** every gap shows actual vs goal with counts.
- **Validation bar:** worked-example gaps green on seed data.
- **Lifecycle:** re-validate on formula or benchmark change.
- **Adequacy verdict:** fit (informational arithmetic).
