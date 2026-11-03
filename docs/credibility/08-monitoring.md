# 08 · Monitoring — credibility card

- **Identity:** tab-monitoring · `backend/agents/kri_monitor.py`,
  `csm.py`, `deviation_watch.py`, `backend/agents/retention.py`.
- **Question of interest:** which sites need a visit?
- **Context of use:** centralized monitoring input. Inputs: monthly site
  metrics + visit records. Outputs: KRI RAG vs quality-tolerance
  limits, CSM outlier screens (robust-z, exact Poisson, funnel
  limits), zero-enroll score + Cox-Stuart trend, deviation tiers +
  binomial site-rate signals. Human sign-off: central monitor.
- **Non-COU boundary:** screens prioritize visits; they do not replace
  SDV judgment or close sites.
- **Method + determinism:** disclosed thresholds; exact nonparametric
  tests; seeded RNG only in simulation paths.
- **Data governance:** user metrics/visits, local only.
- **Provenance:** every flag cites value, threshold/pool, and p-value
  where applicable.
- **Validation bar:** KRI band fixtures, CSM flag fixtures, trend and
  rate-signal tests green.
- **Lifecycle:** re-validate on threshold, limit, or test change.
- **Adequacy verdict:** fit-with-controls (monitor decides visits).
