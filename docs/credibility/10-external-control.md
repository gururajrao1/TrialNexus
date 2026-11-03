# 10 · External control — credibility card

- **Identity:** tab-external · `backend/agents/external_control.py`,
  `relaxation_sweep.py`.
- **Question of interest:** what do we compare a single arm against?
- **Context of use:** design exploration for single-arm settings.
  Inputs: strict pool + relaxed criteria. Outputs: comparator pool,
  near-miss set, pool-mix comparability, methods note naming every
  relaxed criterion. Human sign-off: biostatistician.
- **Non-COU boundary:** an explicitly-relaxed comparator pool is not a
  control arm and supports no efficacy claim; relaxations are never
  silent.
- **Method + determinism:** same evaluator; relaxation ladders are
  enumerated, not searched; seeded twins only where noted.
- **Data governance:** user/inbox bundles only.
- **Provenance:** methods note lists each relaxation and its effect.
- **Validation bar:** pool/near-miss accounting tests green.
- **Lifecycle:** re-validate on evaluator or sweep change.
- **Adequacy verdict:** fit-with-controls (statistician owns inference).
