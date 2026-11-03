# 06 · History & export — credibility card

- **Identity:** tab-history · `backend/database.py` (evaluations,
  safety_queries), `failure_forensics.py`, export routes.
- **Question of interest:** prove what we ran.
- **Context of use:** audit trail. Inputs: stored runs. Outputs:
  timestamped evaluation/query rows, CSV exports, screen-failure
  forensics with per-criterion fail/missing/trigger rates. Human
  sign-off: QA/auditor reads, system writes.
- **Non-COU boundary:** the log records what the panels computed; it
  does not re-validate the underlying verdicts.
- **Method + determinism:** append-only SQLite log; CSV is a direct
  projection of stored rows.
- **Data governance:** local DB only; user data never leaves the
  machine; no auto-purge (retention is the deployer's policy).
- **Provenance:** every row carries protocol, patient, timestamp, and
  the inputs hash of its run.
- **Validation bar:** insert/resolve/export round-trip tests green.
- **Lifecycle:** re-validate on schema change (migrations are explicit).
- **Adequacy verdict:** fit (record-keeping).
