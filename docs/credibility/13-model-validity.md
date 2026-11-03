# 13 · Model validity — credibility card

- **Identity:** tab-validity · `backend/agents/n2c2_harness.py`.
- **Question of interest:** is the matcher itself any good?
- **Context of use:** independent benchmark of the rules engine.
  Inputs: n2c2 2018 fixture notes (13 criteria). Outputs: fixture
  micro-F1, criteria list, real-data presence flag, DUA instructions.
  Human sign-off: methods reviewer.
- **Non-COU boundary:** fixture F1 measures the shipped rules on
  shipped fixtures; real-note performance requires the DUA dataset
  and is unverified until run.
- **Method + determinism:** rule-based predictor over notes; fully
  deterministic.
- **Data governance:** synthetic fixture in-repo; real notes only via
  institutional DUA into `data/n2c2/`, never committed.
- **Provenance:** per-criterion predictions reproducible from fixture.
- **Validation bar:** fixture micro-F1 1.0 test green.
- **Lifecycle:** re-validate on matcher or fixture change; report DUA
  numbers when available.
- **Adequacy verdict:** fit (benchmark, not a claim about real notes).
