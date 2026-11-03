# 02 · Site feasibility — credibility card

- **Identity:** tab-sites · `backend/agents/site_scout.py`,
  `enrollment_forecast.py`, `real_data.py` (live CT.gov).
- **Question of interest:** which sites will actually enroll, and when
  will the trial hit last-patient-in?
- **Context of use:** site-selection meeting input. Inputs: site list +
  target enrollment. Outputs: GO/CONDITIONAL/NO-GO with 35/25/20/20
  breakdown (velocity/competition/regulatory/capacity), Poisson-Gamma
  P10/P50/P90 forecast with hindcast MAE. Human sign-off: sponsor
  feasibility lead.
- **Non-COU boundary:** not a site contract or a guarantee of accrual;
  live competitor counts are registry snapshots, never complete.
- **Method + determinism:** disclosed weights; Gamma(2,1) posterior +
  20,000-simulation Monte Carlo, seeded; expanding-window hindcast.
- **Data governance:** user site lists; live CT.gov degrades to
  cache/offline with source chips.
- **Provenance:** per-site scoring breakdown rows; rate sources labeled
  observed vs provided.
- **Validation bar:** hindcast MAE reported alongside every forecast
  (seed data: 0.62 patients/month over 9 site-months); forecast never
  ships without MAE + simulation count.
- **Lifecycle:** re-validate on weight, prior, or benchmark change.
- **Adequacy verdict:** fit-with-controls (selection committee decides).
