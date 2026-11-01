# TrialNexus — feature deliverables × product value

Each feature below lists what was delivered (code, endpoints, UI, tests, data)
and the product value it adds (problem → outcome, with the evidence behind it).

## 1. Protocol auditor (+ fragility + $ exposure)

- Deliverables: `backend/agents/protocol_auditor.py`; `POST /api/audit-protocol/{id}`;
  Audit tab (criteria tables, segmented gauge, flaw list); `TEST_GUIDE` scenario 1.
- Value: catches amendment-grade flaws pre-submission. 76% of protocols are
  amended (Tufts) at $141K–$535K median direct cost, 45% avoidable — the
  fragility index + dollar exposure turns "looks risky" into a budgeted decision.

## 2. Site scout (+ live CT.gov lookup)

- Deliverables: `backend/agents/site_scout.py` (35/25/20/20 formula, cached
  registry lookup); `POST /api/score-sites` (+ `live_lookup`); Sites tab with
  source chips; scenario 2/5; 3 seeded sites spanning GO/CONDITIONAL/NO-GO.
- Value: replaces relationship-based picks with objective ranking. 37% of
  sites under-enroll and 11% enroll zero (CISCRP) — scored portfolios with
  accrual run-rates attack that directly, live counts included.

## 3. Cohort matcher (+ negation handling)

- Deliverables: `backend/agents/cohort_matcher.py` (labs/conditions/meds/age,
  word-boundary + negation-aware); `POST /api/match-cohort`; Cohort tab with
  PASS/FAIL tables; 5 FHIR bundles; scenarios 3/11 admissibility paths.
- Value: prescreening worklist with cited evidence per criterion instead of
  hand-reading charts. Screen failures run 30–50%+; negation handling kills
  the classic false-positive class ("no history of X" ≠ X).

## 4. Safety triage coordinator

- Deliverables: `backend/agents/safety_triage.py` (MedDRA SOC map, SAE rules,
  7/15-day clocks, drafted queries); `POST /api/triage-safety`; Safety tab
  with SAE alert blocks; 4 seeded AE records; scenario 4.
- Value: auto-triage queue for the team drowning in manual ICSR intake and
  coding. Serious events surface with clocks and ready-to-send site queries.

## 5. Zero-cost local core (router + SQLite)

- Deliverables: `backend/router.py` (Ollama-optional, stub fallback),
  `backend/database.py` (WAL, 7 tables), `seed_data.py`, `requirements.txt`
  (4 packages only).
- Value: runs air-gapped inside a hospital firewall — no PHI leaves, no API
  bills, no model downloads. Deterministic output is auditable by design.

## 6. Static life-sciences UI

- Deliverables: `frontend/` (index.html, styles.css, app.js, zero deps),
  served at `/`; 13 auto-running tabs; snapshot metrics; `/docs` retained.
- Value: one screen per role, data visible on load, no installs beyond the
  API. Clinical styling (teal, badges, chips, meters) reads as a real
  product, not a notebook demo.

## 7. Diversity enrollment planner

- Deliverables: `backend/agents/diversity_planner.py` (OMB mix vs goals,
  gaps, catch-up math); `POST /api/diversity-plan` (+ defaults); Diversity
  tab; race/ethnicity in all 5 FHIR seeds; scenario 6.
- Value: FDORA requires Diversity Action Plans for Phase 3/pivotal trials
  while only 14% of protocols bake diversity in. Turns the cohort into a
  gap-closing plan with focus areas.

## 8. History persistence + CSV export

- Deliverables: `patient_evaluations` + `safety_queries` writes on every
  run; `/api/history/*`, `/api/export/*.csv`; History tab; scenario 7.
- Value: run history survives the session and leaves the building as CSV
  for TMF files, sponsor reports, and audits. Nothing evaporates.

## 9. Structured protocol export (M11-inspired)

- Deliverables: `backend/agents/structured_export.py`;
  `GET /api/protocol-structure/{id}`; Audit-tab block with Download/Copy;
  scenario 8.
- Value: ICH M11 makes machine-readable protocols mandatory (enforcement
  from June 2026). The protocol leaves the app as reusable structured
  data for EDC setup and downstream documents.

## 10. Visit-burden + DCT-fit scorer

- Deliverables: `backend/agents/burden_scorer.py` (per-visit procedure
  weights, remote-fit verdicts); `GET /api/burden/{id}`; Audit-tab table.
- Value: biopsies, travel, and dense sampling drive dropouts — yet 85% of
  sites say current DCT elements added work. Scores each visit and names
  which can go remote without breaking oversight.

## 11. Study-startup tracker

- Deliverables: `backend/agents/startup_tracker.py` + `site_startup` table;
  `GET /api/startup`, `POST /api/startup/{site}/advance`; Startup tab;
  scenario 9; relative-date seeds (1 clean, 1 flagged, 1 mid-flight).
- Value: site ID→activation averages 7–8 months (Tufts) with $25K+ burned
  per stalled site. Pipeline + benchmark flags spotlight the exact stuck
  site and the reason (CTA, IRB, total elapsed).

## 12. Centralized monitoring lite

- Deliverables: `backend/agents/kri_monitor.py` (5 KRIs vs tolerance
  limits); `site_metrics` seeds (3 sites × 4 months); `GET /api/monitoring`;
  Monitoring tab; scenario 10.
- Value: queries cost $28–225 each with tens of thousands per Phase 3,
  SDV fixes ~1.1%, and ICH E6(R3) mandates risk-based monitoring. Visit
  the red sites; leave the green ones alone.

## 13. Patient-facing trial finder

- Deliverables: `backend/agents/trial_finder.py` (reverse-rank, same
  evaluator); `POST /api/find-trials`; Finder tab; 3 protocols + 5
  patients giving unambiguous #1 ranks; scenario 11.
- Value: trial → chart prescreening misses patients; patient → trials
  finds them. Same engine both directions, so site and patient views
  can never disagree.

## 14. External control builder

- Deliverables: `backend/agents/external_control.py` (explicit-relaxation
  pool, near-miss set, comparability via diversity mix, methods note);
  `POST /api/external-control`; External tab; scenario 12.
- Value: single-arm trials still need comparators, and FDA acceptance of
  external controls keeps widening. Produces a documented, reproducible
  comparator stub with relaxations named, never silent.

## 15. Test packs (offline + live + guide)

- Deliverables: `tests/` (50 unit tests incl. `STrackTests` ×11,
  stdlib-only), `tests/test_e2e_live.py` (36 live checks),
  `TEST_GUIDE.md` (14 scenarios), this map, `DELIVERY_STATUS.md`,
  `README.md`.
- Value: every problem-statement claim is executable proof, not a slide.
  A buyer, auditor, or new hire can verify the whole product in minutes.

## 16. Relaxation sweep (amendment leverage)

- Deliverables: `backend/agents/relaxation_sweep.py`;
  `POST /api/relax-sweep`; Cohort-tab sweep panel; scenario 14.
- Value: 45% of amendments are avoidable, mostly eligibility relaxations —
  but teams negotiate blind. Per-threshold ladders + marginal flips name
  exactly which criterion to relax and how many patients each step buys.

## 17. Failure forensics (screen-failure drivers)

- Deliverables: `backend/agents/failure_forensics.py`;
  `GET /api/forensics`; History-tab forensics table; scenario 14.
- Value: turns anecdote ("we keep failing on renal") into ranked rates
  over every stored run — the evidence base for amendment discussions
  and pre-screening fixes.

## 18. Retention-risk scorer

- Deliverables: `backend/agents/retention.py` (burden + frailty proxies,
  remote-visit what-if); `POST /api/retention`; Cohort-tab panel.
- Value: dropout replacement costs ~$6K+ per patient and slips timelines.
  Scores discontinuation risk up front, with a what-if showing which
  remote conversions actually move the needle.

## 19. Registry benchmark + trust signals

- Deliverables: `fetch_ctgov_outcomes` + `GET /api/outcome-benchmark`
  (Audit tab); AE enrichment (temporality/attribution/certainty);
  empirical-Bayes forecast priors (`use_site_history`); per-evaluation
  provenance (`rules-v1`).
- Value: plans grounded in what similar trials achieved (counts, results
  rate, median enrollment), forecasts fitted to measured site history,
  and every automated judgment carrying its evidence grade — the
  difference between a black box and an auditable one.

## How it adds up

## 20. Original-file ingest + literature grounding

- Deliverables: `backend/agents/pdf_ingest.py` + `POST /api/audit-pdf`
  (base64 JSON, caps, plain-language failures); `backend/agents/pubmed.py`
  + `GET /api/pubmed` (Entrez, cached, offline-safe); Audit-tab upload,
  Safety-tab literature box; scenario 15.
- Value: protocols arrive as PDFs, not .txt — refusing them pushes work
  back on the user. And safety calls without literature grounding are
  just opinions; linked PMID cards make them defensible.

## 21. Demo-grade hardening (token + pixel proof)

- Deliverables: `backend/auth.py` (env-gated Bearer guard, UI prompts
  once); `tests/test_ui_pixel.py` + CI Chromium job with screenshot
  artifact.
- Value: a shareable demo URL needs a lock, and "it renders" needs proof
  better than a DOM stub. One env var secures the API; every push now
  proves the app boots in a real browser.

## 22. Calibrated planning models (outlook + attrition)

- Deliverables: log-odds outlook v2 in `risk_models.py`;
  `backend/agents/attrition.py` + `GET /api/attrition/{id}`;
  scenario 16.
- Value: gut-feel success odds and surprise dropouts become
  literature-anchored numbers with named drivers — plannable,
  challengeable, and ready to graduate to fitted TrialBench models.

## 23. Safety + design operations (signals, DCT, criteria)

- Deliverables: `signal_detection.py` + `POST /api/safety-signals`;
  `dct_readiness.py` + `GET /api/dct-readiness/{id}`;
  `criteria_feedback.py` + `GET /api/criteria-feedback/{id}`.
- Value: case lists become watchlists (Evans/ROR), DCT choices become
  a per-visit matrix instead of hand-waving, and vague criteria get
  graded with fixes before they become amendments.

## 24. Site foresight (zero-enroll flags)

- Deliverables: scorecard in `kri_monitor.py`, badges in the
  Monitoring tab; no new endpoint needed.
- Value: the observable half of ML site-behavior prediction for free —
  zero-months, gaps, and declining run-rates flag the next
  non-enroller while there is still time to intervene.

## How it adds up

Design (1, 9, 10) → select (2, 11) → enroll (3, 13, 7) → monitor (4, 12) →
document (8, 14, 20) → optimize (16, 17, 18, 19) → calibrate (22, 23, 24),
with (5) as the free-to-run foundation, (6) as the single surface, and
(15, 21) as the proof layer. Each feature consumes the last one's output:
audited criteria feed matching, matches feed diversity and history,
history feeds forensics, monitoring, and now signals, attrition, and
site foresight. That compounding — not any single tab — is the product:
a trial operations loop that runs end to end, offline, for $0.
