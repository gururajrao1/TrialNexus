# Batch 4 — warm list (gated, not started)

Nothing here is approved work. Items graduate into a build batch only from
demo friction or from an external input landing. Code-only rule still holds
unless the item says otherwise.

## Awaits the demo pass (your friction decides)

- _Empty — fill from the demo run-through: every "I wish it…" becomes a
  candidate, ranked by how often it bites._

## Gated by external inputs (blocked until the input exists)

- EHR/FHIR live feed → real cohort + safety rows instead of pasted bundles.
- CTMS auto-import → scheduled pull replacing manual CSV paste.
- Part 11 e-signatures → signatures on lock/closeout exhibits.
- TrialBench coefficients (gated) → replace fitted priors in trial-outlook.
- n2c2 real data (DUA) → matcher benchmark beyond the mini fixture.
- Completion-analysis funding → the money-at-risk item in the README.
- EU AI Act counsel sign-off → classification note before any deployment.

## Small, pre-approved, code-only (build anytime on request)

- Adaptive visit cadence from KRI deltas between runs (needs a state
  decision: localStorage vs DB table — currently blocked by no-migrations).
- CAPA tracker with effectiveness-check countdowns (same state decision).
- Protocol PDF version store for the amendment diff (currently paste-only).
- Digest scheduling note (morning digest is on-demand; email/push needs a
  new API key, so it stays out under current rules).

## Done criteria for any Batch 4 item

Pure tests + e2e check + smoke IDs + docs paragraph + live verify, then
commit + push. Same gates as Batches 1–3.
