# TrialNexus test guide — problem statement to proof

## Run it (from the `trialnexus/` folder)

```bat
python seed_data.py
python -m unittest discover -s tests        :: fast offline suite (39 tests)
uvicorn backend.app:app --port 8000         :: leave running
python tests/test_e2e_live.py               :: live problem-statement checks
```

Then open http://127.0.0.1:8000/ and walk the four scenarios below.

## Scenario 1 — Protocol amendments (tab: Protocol audit)

Problem: 76% of protocols need amendments (Tufts); median direct cost
$141K (Ph2) / $535K (Ph3); 45% avoidable, mostly eligibility relaxations.

- Run the audit on `PROT-TNX-001`.
- Expect: 5 inclusion + 4 exclusion rules, fragility 20.5/100 (Low band),
  1 flaw (Day 14 vs Day 16 window clash), amendment exposure ≈ $110,000
  (fragility-scaled share of the Tufts $535K median).
- Proves: machine-readable I/E criteria + amend-before-you-spend signal.

## Scenario 2 — Site selection (tab: Site feasibility)

Problem: 37% of sites under-enroll, 11% enroll zero (CISCRP).

- Score the 3 demo sites with target 450.
- Expect: SITE-001 GO (80.5), SITE-003 CONDITIONAL (64.6),
  SITE-002 NO-GO (43.8), each with the 35/25/20/20 breakdown, risks,
  and a portfolio months-to-last-patient-in estimate.
- Proves: objective ranking replaces relationship-based picks.

## Scenario 3 — Cohort matching (tab: Cohort matching)

Problem: 30–50% screen failures; 1 in 4 eligible oncology consents lost
to record mismatch; criteria must become computable definitions.

- Match all 3 FHIR bundles against `PROT-TNX-001`.
- Expect: patient-001 ELIGIBLE 100%; patient-002 INELIGIBLE (low ANC +
  prior TKI trigger); patient-003 REVIEW_REQUIRED (missing ECOG, QTc,
  pregnancy test) with physician action items.
- Negation check: patient-003's "No evidence of brain metastases" must
  NOT trigger EXC-02 — open its exclusion evaluations to confirm.
- Proves: prescreening worklist with cited evidence per criterion.

## Scenario 4 — Safety triage (tab: Safety triage)

Problem: manual ICSR intake/coding/narratives can't scale; 7/15-day clocks.

- Triage the 4 seeded safety records.
- Expect: DISC-902 flagged SAE with MedDRA Blood SOC and a 360h
  expedited clock + drafted site query; the other three routine with
  correct SOC/grade mapping, no false alerts.
- Proves: auto-triage queue with defensible, cited output.

## Scenario 5 — Live competitor lookup (tab: Site feasibility)

- Tick "Use live CT.gov counts" (condition prefilled) and re-score.
- Expect: per-site competitor counts with source chips (`live`, `cache`,
  or `offline-fallback` when the network is unavailable). Manual counts
  in the JSON always win when present.
- Proves: real registry benchmarking with graceful degradation.

## Scenario 6 — Diversity plan (tab: Diversity plan)

Problem: FDORA requires Diversity Action Plans for Phase 3/pivotal trials;
only 14% of protocols bake diversity in.

- Run with the default goals (or edit the JSON to protocol targets).
- Expect: mix vs goal per dimension (race, ethnicity, sex, age) with
  gaps, on-track/at-risk/behind/off-track status, catch-up numbers,
  and top-3 focus areas. Demo n=3, so most groups show gaps — expected.
- Proves: DAP-gap analysis from the same FHIR bundles.

## Scenario 7 — History + export (tab: History & export)

- Run Cohort matching and Safety triage at least once, then refresh.
- Expect: persisted evaluation/query rows with timestamps; CSV download
  links export the same tables.
- Proves: run history survives the session and leaves the building as CSV.

## Scenario 8 — Structured export + burden (tab: Protocol audit)

Problem: ICH M11 makes machine-readable protocols mandatory (enforcement
from June 2026); visit burden (biopsies, travel, dense sampling) drives
dropouts while badly-designed DCT adds site work instead of removing it.

- Run the audit; scroll past the flaws.
- Expect: an M11-inspired structure block (5 INC / 4 EXC coded, visits
  Day 1/14/16) with Download/Copy JSON, plus a burden table (Day 1 = 18
  from 6 PK draws, Day 14 = 10, Day 16 = 3, 33.3% convertible) and verdict.
- Proves: the protocol leaves the app as reusable structured data, and
  each visit gets an on-site vs remote recommendation.

## Scenario 9 — Study startup (tab: Study startup)

Problem: site ID to activation averages 7–8 months (Tufts); $25K+ burns
on stalled pre-activation sites; CTA talks run 90+ days.

- Open the tab; SITE-002 should carry the at-risk flag, SITE-001 clean.
- Advance SITE-003 to `activated` with a note; the pipeline updates.
- Proves: bottleneck radar over the highest-variance trial stage.

## Scenario 10 — Monitoring (tab: Monitoring)

Problem: queries cost $28–225 each with tens of thousands per Phase 3,
SDV corrects ~1.1% of entries, and ICH E6(R3) mandates risk-based
central monitoring — visit the sites that need it, not all of them.

- Open the tab (auto-runs from monthly site metrics).
- Expect: SITE-002 red with 4 alert KRIs and a visit recommendation,
  SITE-001 green with no action, SITE-003 amber watch list.
- Proves: central oversight that targets monitoring spend.

## Scenario 11 — Find trials (tab: Find trials)

Problem: patients can't find trials they qualify for; sites prescreen
by hand from the wrong end (trial → chart instead of patient → trials).

- Pick `patient_004_her2.json`, run; then `patient_005_diabetes.json`.
- Expect: 004 ranks the breast trial #1 ELIGIBLE with reasons;
  005 ranks the diabetes trial #1 ELIGIBLE; others trail as INELIGIBLE
  with the blocking criteria named.
- Proves: patient-side matching reusing the exact site-side evaluator.

## Scenario 12 — External control (tab: External control)

Problem: single-arm trials (rare, peds, oncology) still need a
comparator; FDA increasingly accepts external controls with
pre-specified methods.

- Run with the default relaxation `INC-04, EXC-01`.
- Expect: pool n=2 (001 strict + 002 via relaxation), near-miss n=3,
  pool-mix comparability tables, and a methods note naming the relaxed
  criteria and caveats.
- Proves: a documented, reproducible comparator stub — relaxations
  explicit, never silent.

## Scenario 13 — Tier 1+2: forecast, outlook, twins, mCODE, validity

Problem: point estimates hide risk (sites slip, measurements vary),
success odds stay gut-feel, oncology records lack a standard summary,
and matchers ship without independent benchmarks.

- Protocol audit tab: scroll to Readability (Flesch ease/grade, entity
  density) and Trial outlook (success probability + enrollment/safety/
  efficacy failure shares with drivers).
- Site feasibility tab: scroll to the Poisson-Gamma forecast (P10/P50/P90
  months to target from 20,000 simulations).
- Synthetic twins tab: generate 500 twins of patient-001; expect a
  mostly-eligible mix with the ineligible share coming from jittered labs.
- mCODE summary tab: pick patient-004; expect breast cancer, HER2
  biomarker, ECOG 0, and a completeness % with gaps listed.
- Model validity tab: expect fixture micro-F1 1.0 across 13 criteria,
  real-data status, and DUA instructions for the full n2c2 set.
- Cohort matching: criteria now resolve through a synonym table
  ("MI" = "myocardial infarction") and DocumentReference notes;
  append a note to any bundle to test note-backed evidence and
  negation ("No ...") handling.
- Proves: uncertainty-quantified planning, a standard oncology summary,
  and a benchmarked matcher — all offline and deterministic.

## Features × data map

| Feature | Input data | What it does | Output |
|---|---|---|---|
| Protocol audit | `data/raw/protocols/*.txt` via SQLite | Regex I/E parse, SoA clash + ambiguity checks, fragility + $ exposure | Structured criteria, flaws, score |
| Site scoring | JSON site profiles (+ optional CT.gov cache) | 35/25/20/20 formula, GO bands, accrual + timeline math | Ranked sites, portfolio summary |
| Cohort matching | Structured criteria + `data/fhir/synthea/*.json` | Labs/conditions/meds/age checks, negation + missing-data handling | ELIGIBLE/INELIGIBLE/REVIEW + evidence + actions |
| Safety triage | `data/raw/queries/*.json` or pasted records | MedDRA keyword map, SAE rules, 7/15-day clocks, query drafting | Triaged records with alerts + queries |
| Live CT.gov lookup | Condition + site countries | Cached registry counts feed the competition penalty | Counts + source chips |
| Diversity plan | FHIR bundles + goal JSON | Mix vs goal per OMB/sex/age dimension, gaps, catch-up math | Dimension tables + focus areas |
| History + export | SQLite run tables | Every match/triage run persisted; CSV download | History tables, cohort/safety CSV |
| Structured export | Audit result + raw text | M11-shaped study/eligibility/schedule/quality package | JSON view + download + copy |
| Burden + DCT fit | Raw protocol text | Per-visit procedure scoring, remote-convertible verdict | Visit table, convertible %, verdict |
| Startup tracker | `site_startup` pipeline table | Stage tracking vs 90/45/240-day benchmarks | Pipeline table, flags, advance form |
| Monitoring lite | `site_metrics` monthly rows | 5 KRIs vs tolerance limits per site | Per-site KRI tables, alert list, actions |
| Trial finder | 3 audited protocols + 1 bundle | Reverse-rank trials eligible-first with reasons | Ranked trial cards with match bars |
| External control | 5-bundle pool + relax list | Relaxed re-evaluation, comparability, methods note | Pool table, mix tables, methods text |
| Enrollment forecast | Scored sites (accrual + months observed) | Poisson-Gamma Monte Carlo, 20k sims, seeded | P10/P50/P90 months, mean, P(deadline) |
| Trial outlook | Audit + burden scores | Phase base rates × fragility/burden discounts, TrialBench 4-way split | Success probability, failure shares, drivers |
| Synthetic twins | 1 bundle + criteria | ±15% lab jitter, seeded, capped 500, in-memory | Status counts, eligible %, caveats |
| mCODE summary | 1 bundle | mCODE-inspired field extraction + completeness | Profile table, completeness %, gaps |
| n2c2 validity | `tests/fixtures/n2c2_mini.json` (+ optional `data/n2c2/`) | 13-criterion rule benchmark, micro-F1 | Fixture F1 1.0, real-data status, DUA path |
| Note-aware matching | DocumentReference / note Observations | Synonym-normalized, negation-aware note search | Note-cited evidence in evaluations |
| Snapshot + demo feed | SQLite + seed files | Counts + prefill payloads for the UI | `/api/snapshot`, `/api/demo-data` |

## Data catalog (every file earns its place)

- `protocol_oncology_phase3.txt` — NSCLC EGFR Phase 3; exercises age,
  ECOG, ANC sci-notation, creatinine, TKI, CNS, QTc, pregnancy parsing.
- `patient_001_breast_cancer.json` — clean eligible case (all data present).
- `patient_002_control.json` — hard fails (ANC 900, prior osimertinib).
- `patient_003_review.json` — missing-data case + negation trap.
- `adverse_events_stream.json` — routine liver signal, unexpected SAE,
  severe QTc, mild nausea.
- `trialnexus_state.db` — SQLite WAL store (seeded: 1 protocol, 3 sites).

## Known limits (next upgrades)

- Washout windows cover dated TKI/medication statements; undated
  matches trigger conservatively.
- Exotic multi-rule phrasings may split imperfectly — the audit JSON
  shows the parsed sub-rules for review.
- Diversity defaults are illustrative; plug in protocol-specific DAP targets.
- Twins probe measurement sensitivity only — never efficacy or safety.
- Outlook is a transparent heuristic until fitted on HINT public data.
- Full n2c2 validation needs a DUA; only the synthetic fixture ships.
