# TrialNexus OS — zero-cost local clinical trials intelligence

TrialNexus is a multi-agent clinical trials platform that runs **entirely on
your machine**: protocol auditing, site feasibility, cohort matching, and
safety triage, plus a full product layer (diversity planning, startup
tracking, monitoring, trial finding, live trial matching, warning-letter
cross-checks, synthetic twins, and more).

The core is **deterministic**: every agent is a pure function with cited,
reproducible output — the same input always produces the same result. An
optional model layer (off by default, bring-your-own endpoint) drafts
plain-English explanations that are verified or discarded; templates always
decide. No data leaves the machine unless you explicitly tick the box.

## The problem it solves

Bringing a drug from Phase I to approval averages 10–12 years and over
$2.6B, and most of the waste is operational — predictable, measurable, and
still handled by gut feel and spreadsheets in small teams:

| Pain | Number (Tufts CSDD / industry) | TrialNexus answer |
|---|---|---|
| Protocol amendments | 76% of protocols amended (up from 57%); median $141K Phase II / $535K Phase III each; ~260 days to push through; +9.5 months when post-enrollment | Protocol audit: fragility index, $ exposure, clash checks — amend before you spend |
| Sites miss enrollment | ~80% of trials delayed by recruitment; 37% of sites under-enroll, 11% enroll zero; delay days cost $600K–$8M | Site feasibility scoring + startup tracking + live CT.gov competition counts |
| Eligible patients never found | Screen failures 30–50% (70%+ in precision oncology); matching is manual chart review | Cohort matching (FHIR) + trial matcher: plain-English description → live recruiting trials, explained with quotes |
| Monitoring spread evenly | Verifying everything everywhere burns visit budget | CSM outlier screens, KRIs, deviation watch with SDV tiers — visit the risky sites |
| Safety/query lag | Manual triage under 7/15-day clocks | Safety triage (MedDRA, SAE flags, clocks), ROR/PRR signals with FDR, FAERS/label checks |
| Repeat regulatory mistakes | FDA warning letters cite the same CAPA/design/complaint failures for years | Warning-letter cross-check: your finding vs indexed FDA violations, with trial analogues |
| Diversity mandates | FDORA requires Diversity Action Plans | Diversity planner: mix-vs-goal gaps + catch-up math |
| Startup drag | 7–8 months site ID → activation | Startup tracker, enrollment forecast, trial outlook |

## Where it falls short (gaps)

- **Lexical, not semantic.** No dense embeddings (zero-cost rule): "mutant = mutation" comes from a small synonym map, not understanding. A sponsor with embedding infrastructure out-matches us.
- **No live feeds.** Everything is file-in or public API. No EHR, CTMS, or EDC integration — no automatic enrollment streams, no real-time monitoring.
- **Predictions aren't trained on your history.** The outlook runs on disclosed priors plus a fitter waiting on gated TrialBench access — calibrated reasoning, not a model learned from a sponsor's past trials.
- **Single-user local tool.** No multi-user roles, no 21 CFR Part 11 audit trail — not a system of record a regulator would accept.
- **Public-data-bound.** Startup benchmarks derive from public dates, not real CRO timelines; warning letters must be hand-saved; the model layer only works if you bring your own endpoint.

## Future improvements

1. **EHR/CTMS feeds** — automatic enrollment streams and monitoring inputs instead of file uploads.
2. **Train the outlook on sponsor history** — fit the success/failure model on real past-trial data (TrialBench access pending).
3. **Dense retrieval** — swap TF-IDF term-vectors for embeddings when a dependency budget allows; the UI and verification already assume swappable ranking.
4. **Regulated multi-user mode** — roles, Part 11 audit trail, e-signatures for lock readiness.
5. **Richer evidence** — live FDA warning-letter ingestion if an API appears; full n2c2 validation under a data-use agreement.

## 30-second tour — the 15 tabs

| # | Tab | What it does |
|---|---|---|
| 1 | Protocol audit | I/E extraction, fragility, $ exposure, M11 export, burden, outlook, outcome benchmarks, PDF upload, DCT + criteria design |
| 2 | Diversity plan | Enrollment mix vs goals, gaps, focus areas |
| 3 | Model validity | Independent n2c2 benchmark of the matcher |
| 4 | Site feasibility | Ranked sites + Poisson-Gamma forecast, live CT.gov competition, NPI checks |
| 5 | Study startup | Pipeline stages vs benchmark flags |
| 6 | Monitoring | Central KRIs + CSM outlier screens, deviation watch with SDV tiers |
| 7 | Cohort matching | FHIR patients → ELIGIBLE / INELIGIBLE / REVIEW_REQUIRED + sweep + retention + attrition |
| 8 | Find trials | Reverse match: patient bundle → ranked local protocols |
| 9 | External control | Relaxed-criteria comparator pool + methods note |
| 10 | Synthetic twins | Measurement-sensitivity stress test (in-memory) with prespec block |
| 11 | mCODE summary | Standard oncology profile + completeness |
| 12 | Safety triage | AE triage with SAE flags, clocks, FAERS/RxNorm/DailyMed enrichment, PubMed, ROR/PRR signals |
| 13 | Warning letters | Your FDA letters indexed; finding cross-check with trial analogues |
| 14 | History & export | Every run persisted; forensics; CSV downloads |
| 15 | Trial matcher | Plain-English description → live recruiting CT.gov trials, explained (optional verified model drafts) |

Most tabs auto-run when the page loads (matcher shows guidance until you
describe a patient; history just replays saved runs). No login, no setup
beyond the quickstart below.

## Quickstart (VS Code)

Prerequisite: Python 3.11+.

```bat
:: 1. Open the trialnexus folder in VS Code, then in a terminal:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt        :: 5 packages: fastapi, uvicorn, pydantic, httpx, pypdf

:: 2. Seed the database and run the fast suite (no server needed):
python seed_data.py
python -m unittest discover -s tests  :: 177 tests, ~40 seconds (1 CI-only browser skip)

:: 3. Start the API (leave running) and open the app:
uvicorn backend.app:app --port 8000
```

- UI: http://localhost:8000/
- Interactive API docs: http://localhost:8000/docs
- Live checks: `python tests/test_e2e_live.py` (45 checks, needs the server)

OneDrive tip: right-click `.venv` → "Free up space" to keep it on-demand.

## How it works (deterministic core, optional model layer)

| Cookbook agent | This build |
|---|---|
| Protocol Auditor | Regex I/E parser → INC/EXC rules, fragility index, SoA clash checks, readability metrics |
| Site Scout | 35/25/20/20 feasibility formula; CT.gov lookup cached with offline fallback; completed-trial outcome benchmarks |
| Cohort Matcher | FHIR R4 evaluator (labs, conditions, meds, age, notes) → ELIGIBLE / INELIGIBLE / REVIEW_REQUIRED, negation- and synonym-aware, with per-criterion provenance |
| Safety Triage | MedDRA SOC keyword map + SAE rules + 7-day / 15-day clocks + drafted site queries + temporality/attribution/certainty enrichment |
| EngineRouter | `ZeroCostRouter`: your configured endpoint (`TRIALNEXUS_MODEL_BASE_URL`), local Ollama, else deterministic stub (agents never need it; drafts verified or discarded) |
| Trial Matcher | CT.gov API v2 (`fields`-slimmed) → TF-IDF rank + TrialGPT-style criterion notes (met/conflict/unknown/N/A) + exclusion-weighted score |

Multi-threshold lines evaluate every sub-rule: comma/and-joined panels
(ANC + platelets + hemoglobin) must all pass; `or`-joined alternatives
(creatinine or CrCl) need any one to pass.

## Architecture

```
browser (static ES modules, zero deps)
        │  same-origin JSON
        ▼
FastAPI  backend/app.py  ── thin entrypoint: UI + static + routers
        │                      (+ optional token guard via backend/auth.py)
        ├── routes/core.py     health, snapshot, demo-data, audit,
        │                      audit-pdf, score-sites, match-cohort,
        │                      triage-safety
        ├── routes/product.py  diversity, history/export, structure,
        │                      burden, startup, monitoring, finder,
        │                      external-control, forensics, retention,
        │                      outcome-benchmark, pubmed, signals,
        │                      dct-readiness, criteria-feedback, attrition
        └── routes/tier.py     outlook, forecast (+history), sweep, twins,
                               mcode, n2c2-status
        │
        ▼
agents  backend/agents/*.py  ── pure deterministic functions
        │  (protocol_auditor, site_scout, cohort_matcher, safety_triage,
        │   + 22 product/Tier/S/G/R modules; see Features)
        ▼
SQLite (WAL)  data/local_db/trialnexus_state.db  ── via backend/database.py
config  backend/config.py  ── every path + cap in one place
```

Design rules: deterministic (seeded RNG, no clocks in logic), offline-first
(network only for the optional CT.gov lookup, with cache + fallback),
storage-light (no datasets on disk; twins/simulations are in-memory).

Request flow example — cohort match:

```
POST /api/match-cohort {protocol_id, bundles}
  → core.py loads audited criteria from SQLite (400 if never audited)
  → cohort_matcher.evaluate_cohort scores each bundle
  → evaluations persisted to patient_evaluations
  → JSON: per-patient status + per-criterion evidence + action items
```

## Project layout

```
trialnexus/
├── backend/
│   ├── app.py                   # entrypoint (UI + routers)
│   ├── config.py                # paths, cache caps, schema version
│   ├── router.py                # ZeroCostRouter (optional Ollama probe)
│   ├── database.py              # SQLite WAL layer (7 tables + schema_version)
│   ├── routes/                  # core.py, product.py, tier.py
│   └── agents/                  # 4 cookbook agents + 22 product/Tier/S/G/R modules
├── frontend/
│   ├── index.html               # 13 tabs + snapshot + stepper
│   ├── styles.css               # life-sciences theme
│   ├── app.js                   # entrypoint (imports js/boot.js)
│   └── js/                      # api, ui, data, panels-*, boot modules
├── data/
│   ├── raw/protocols/           # 3 protocol .txt seeds
│   ├── raw/queries/             # adverse event stream seed
│   ├── fhir/synthea/            # 5 FHIR patient bundles
│   └── local_db/                # SQLite DB (generated; git-ignored)
├── tests/                       # test_smoke, test_tier12, test_e2e_live, fixtures
├── seed_data.py                 # DB init + seed (stdlib only)
├── requirements.txt             # runtime: fastapi, uvicorn, pydantic, httpx, pypdf
├── requirements-dev.txt         # dev only: ruff
├── pyproject.toml               # ruff config
└── .github/workflows/ci.yml     # lint → seed → unit → e2e → parity
```

Seed data catalog (every file earns its place):

| File | Role |
|---|---|
| `protocol_oncology_phase3.txt` | NSCLC EGFR Phase 3; exercises age, ECOG, ANC sci-notation, creatinine, TKI, CNS, QTc, pregnancy parsing |
| `protocol_breast_phase2.txt` / `protocol_diabetes_phase2.txt` | Extra protocols for trial finder + control pool |
| `patient_001_breast_cancer.json` | Clean eligible NSCLC case (all data present) |
| `patient_002_control.json` | Hard fails (ANC 900, prior TKI) |
| `patient_003_review.json` | Missing-data case + negation trap + Assessment note |
| `patient_004_her2.json` | HER2+ breast case (finder + mCODE demo) |
| `patient_005_diabetes.json` | Diabetes case (finder demo) |
| `adverse_events_stream.json` | 10 records across TNX-101/Placebo arms: liver cluster (signal watch), unexpected SAE, severe QTc, mild routine events |

## Features — what each does and how to test it

Conventions: **Try it** = clicks in the UI. **API** = endpoint + payload.
**Proof** = the automated check that guards it (`unittest` / `e2e`).

### 1. Protocol audit — amend before you spend

Parses raw protocol text into machine-readable inclusion/exclusion rules,
flags schedule-of-assessments clashes and ambiguities, and scores the
**fragility index (0–100)** with a Tufts-based amendment $ exposure, plus
readability/complexity metrics (Flesch ease/grade, entity density).

- **Try it:** Protocol audit tab → Run audit on `PROT-TNX-001`. Expect:
  5 INC / 4 EXC rules, fragility **20.5 (Low)**, 1 flaw (Day 14 vs Day 16
  window clash), exposure **≈ $110,000**, grade ≈ 10.1.
- **API:** `POST /api/audit-protocol/PROT-TNX-001` → full audit JSON
  (also persists structured criteria for matching). PDF originals go
  through §21 instead.
- **Proof:** `ProtocolParseTest`, e2e `audit extracts 5 INC / 4 EXC`,
  `audit flags schedule flaw + cost exposure`,
  `audit carries readability complexity`.

### 2. Site feasibility — rank sites on evidence, not relationships

Scores candidate sites with the cookbook **35/25/20/20 formula**
(velocity / competition / regulatory / capacity) into GO / CONDITIONAL /
NO-GO bands with accrual projections and a portfolio months-to-last-patient-in
estimate. Optional live CT.gov competitor lookup with `live` / `cache` /
`offline-fallback` source chips (manual counts always win).

- **Try it:** Site feasibility tab → Score sites (target 450). Expect:
  SITE-001 GO (80.5), SITE-003 CONDITIONAL (64.6), SITE-002 NO-GO (43.8),
  each with breakdown + risks. Tick "Use live CT.gov counts" to see
  real registry numbers feed the penalty.
- **API:** `POST /api/score-sites`
  `{sites, target_enrollment, live_lookup, condition}`.
- **Proof:** `SiteSafetyTest` (scoring half), `LiveLookupTest`
  (lookup never crashes), e2e `sites span GO/CONDITIONAL/NO-GO`,
  `portfolio timeline computed`.

### 3. Cohort matching — prescreening worklist with cited evidence

Evaluates FHIR bundles against audited criteria: exact numeric labs (with
unit handling), age/histology/stage, meds, and **clinical notes**
(`DocumentReference`) through a synonym table ("MI" =
"myocardial infarction") with negation awareness ("No evidence of…"
never counts as evidence). Prior-therapy windows use real date math
against medication dates; creatinine converts mg/dL↔µmol/L; ECOG/KPS can
come from notes when no observation exists. Every evaluation carries
**provenance** (`match_type`: exact / synonym / note / missing;
`confidence`: high / medium / low) backed by the `rules-v1` entailment
backend. Verdicts: ELIGIBLE (all INC pass, 0 EXC hit), INELIGIBLE (hard
fail), REVIEW_REQUIRED (data missing → action items).

- **Try it:** Cohort matching tab → Match cohort. Expect: patient-001
  ELIGIBLE 100%; patient-002 INELIGIBLE (low ANC + prior TKI trigger);
  patient-003 REVIEW_REQUIRED (missing ECOG/QTc/pregnancy) with action
  items. Open 003's EXC-02 to confirm the negated brain note did NOT
  trigger; its EGFR evidence cites the Assessment note.
- **API:** `POST /api/match-cohort` `{protocol_id, bundles}`
  (400 until the protocol has been audited once).
- **Proof:** `CohortTest`, `Tier12Tests` (synonyms/notes ×4), e2e
  `patient-001 ELIGIBLE`, `patient-002 INELIGIBLE with cause`,
  `patient-003 REVIEW_REQUIRED`, `negation respected`,
  `match carries provenance`, `STrackTests` provenance ×3.

### 4. Safety triage — SAE radar with regulatory clocks

Maps reported terms to MedDRA System Organ Classes, applies SAE rules
(death, life-threatening, hospitalization, disability, anomaly),
computes **7-day (fatal/life-threatening) / 15-day (other serious)**
expedited clocks, and drafts a site query with an auto-close condition.
Each record also carries **enrichment**: temporality (onset timing),
attribution (relatedness), and certainty (evidence level), each with a
stated basis; the UI surfaces a Signal column for at-a-glance review.

- **Try it:** Safety triage tab → Triage. Expect: DISC-902 flagged SAE
  (Blood SOC) with a **360h** expedited clock + drafted query; the other
  three records routine with correct SOC/grade, no false alerts.
- **API:** `POST /api/triage-safety` `{records, protocol_id}`.
- **Proof:** `SiteSafetyTest` (triage half), e2e `SAE detected with 360h
  clock`, `routine cases stay routine`, `triage carries enrichment`,
  `STrackTests` enrichment ×1.

### 5. Diversity plan — DAP-gap analysis from the same bundles

Compares the matched cohort's mix vs enrollment goals per dimension
(race, ethnicity, sex, age band): actual %, goal %, gap, status
(on-track/at-risk/behind/off-track), catch-up headcount, and top-3 focus
areas. Ships with illustrative defaults; paste protocol DAP targets.

- **Try it:** Diversity plan tab → Plan diversity. Expect per-dimension
  tables with gaps (demo n is small, so gaps are expected) + focus areas.
- **API:** `POST /api/diversity-plan` `{bundles, targets}`,
  `GET /api/diversity-defaults`.
- **Proof:** `DiversityTest`, e2e `diversity mix computed`.

### 6. History & export — runs survive the session

Every match-cohort and triage-safety run is persisted with timestamps;
the tab lists them and offers one-click **CSV downloads** of both tables.

- **Try it:** run Cohort matching + Safety triage, then History & export →
  Refresh history. Expect evaluation/query rows and working
  `cohort.csv` / `safety.csv` links.
- **API:** `GET /api/history/cohort?protocol_id=…`,
  `GET /api/history/safety`, `GET /api/export/cohort.csv`,
  `GET /api/export/safety.csv`.
- **Proof:** e2e `cohort/safety history persisted`, `cohort/safety CSV
  exports`.

### 7. Structured export + burden — the protocol leaves the building

M11-inspired machine-readable package (study, coded eligibility,
schedule, quality) with Download/Copy JSON, plus a per-visit **burden
table** scoring procedures (PK draws, biopsies, imaging) with a
remote-convertible verdict per visit.

- **Try it:** Protocol audit tab → scroll past the flaws. Expect: 5 INC /
  4 EXC coded, visits Day 1/14/16, burden Day 1 = 18 / Day 14 = 10 /
  Day 16 = 3, 33.3% convertible.
- **API:** `GET /api/protocol-structure/PROT-TNX-001`,
  `GET /api/burden/PROT-TNX-001`.
- **Proof:** `StructureExportTest`, `BurdenTest`, e2e `structure package
  M11-shaped`, `burden ranked Day1 > Day14 > Day16`.

## Features, continued

### 8. Study startup — bottleneck radar for activation

Tracks each site through identified → feasibility → contract → IRB →
activated → first-patient-in, flagging stages that exceed benchmarks
(contract ≤ 90d, IRB ≤ 45d, activation ≤ 240d). Advance stages with notes.

- **Try it:** Study startup tab. Expect SITE-002 flagged (stuck in
  feasibility), SITE-001 clean. Advance SITE-003 to `activated`; the
  pipeline updates.
- **API:** `GET /api/startup`, `POST /api/startup/{site}/advance`
  `{stage, date?, note}`.
- **Proof:** `StartupTrackerTest`, e2e `startup flags stale site`,
  `startup advance works`.

### 9. Monitoring — central KRIs that target visit spend

Computes 5 Key Risk Indicators per site from monthly metrics
(enrollment, screen-failure proxy, query rate, deviations, SAEs) against
tolerance limits, with an alert/watch/ok roll-up and a recommended action
(visit, remote check-in, or no action). Each site also carries a
**zero-enroll risk** scorecard (zero-months + latest gap + declining
run-rate → low/elevated/high) — the observable half of ML site-behavior
prediction.

- **Try it:** Monitoring tab (auto-runs). Expect SITE-002 red with alert
  KRIs + visit recommendation, SITE-001 green, SITE-003 amber watch —
  plus zero-enroll badges (002 high, 001/003 low).
- **API:** `GET /api/monitoring`.
- **Proof:** `KRITest`, `ZeroEnrollTests` ×1, e2e `monitoring flags
  SITE-002 only`, `zero-enroll risk bands separate sites`.

### 10. Trial finder — patient → trials, not trial → charts

Reverse matching: given one FHIR bundle, ranks all audited protocols
eligible-first with plain-language reasons and the blocking criteria for
non-matches. Reuses the exact site-side evaluator, so both views agree.

- **Try it:** Find trials tab → pick `patient_004_her2.json`. Expect the
  breast trial #1 ELIGIBLE; `patient_005_diabetes.json` ranks the
  diabetes trial #1.
- **API:** `POST /api/find-trials` `{bundle}`.
- **Proof:** `FinderTest`, e2e `finder ranks breast first for
  patient-004`.

### 11. External control — a documented comparator stub

Builds a comparator pool from the bundle pool by re-evaluating with
explicitly relaxed criteria (never silent), reporting pool vs near-miss,
comparability mix tables, and a pre-specified methods note with caveats.

- **Try it:** External control tab → Build control pool (default
  `INC-04, EXC-01`). Expect pool n=2 (001 strict + 002 via relaxation),
  near-miss n=3, mix tables, methods note naming the relaxations.
- **API:** `POST /api/external-control`
  `{protocol_id, relax_ids, bundles?}`.
- **Proof:** `ExternalControlTest`, e2e `control pool grows with
  relaxation`.

### 12. Enrollment forecast — P10/P50/P90 instead of point estimates

Poisson-Gamma model: each site's accrual rate gets a Gamma posterior
(weak prior + observed enrollments/months); 20,000 seeded Monte Carlo
draws yield months-to-target percentiles and P(hitting a deadline).
With `use_site_history`, assumed run-rates are replaced by measured
accrual from the `site_metrics` history (empirical-Bayes priors), and
the response tags each site `observed` vs `provided`.

- **Try it:** Site feasibility tab → scroll to the forecast. Expect
  ordered P10 ≤ P50 ≤ P90 months with simulation count + seed. Tick
  "Use observed site history" to blend in measured run-rates.
- **API:** `POST /api/forecast`
  `{sites: [{accrual, months_observed}], target_enrollment,
  enrolled_so_far?, deadline_months?, seed?, use_site_history?}`.
- **Proof:** `Tier12Tests` (contract, determinism, monotonicity ×3),
  e2e `forecast returns ordered percentiles`,
  `forecast blends observed site history`, `STrackTests` priors ×1.

### 13. Trial outlook — calibrated success odds with named drivers

Literature-calibrated logistic (v2 bootloader): phase base rates enter
as log-odds priors, discounted by fragility, burden, and organ-safety
load with fully disclosed coefficients — HINT's probabilistic framing
without the fitted network. 4-way TrialBench failure split with
published efficacy-heavy anchors. Graduate path: fit coefficients on
TrialBench's public approval-outcome task data.

- **Try it:** Protocol audit tab → scroll to Trial outlook. Expect a
  success probability (≈ 0.30 for PROT-TNX-001) with failure shares
  that sum to 1 and 4 drivers quoting log-odds contributions.
- **API:** `GET /api/trial-outlook/PROT-TNX-001`.
- **Proof:** `Tier12Tests.test_outlook_contract`,
  `OutlookTests` ×2 (contract, fragility-monotonicity), e2e `outlook
  returns success probability + breakdown`,
  `outlook calibrated log-odds drivers`.

### 14. Synthetic twins — measurement-sensitivity stress test

Clones one bundle up to 500× with ±15% seeded jitter on numeric labs and
re-evaluates each twin: how much of the verdict survives measurement
variation? Fully in-memory — nothing is stored. Design exploration only;
twins never speak to efficacy or safety.

- **Try it:** Synthetic twins tab → Generate twins (patient-001, n=500).
  Expect a mostly-eligible mix with counts summing to n.
- **API:** `POST /api/twins` `{protocol_id, bundle | bundle_id, n, seed}`.
- **Proof:** `Tier12Tests.test_twins_contract`, e2e `twins distribution
  sums to n`.

### 15. mCODE summary — a standard oncology snapshot

Extracts mCODE-inspired elements (cancer type, stage, histology,
biomarkers, ECOG, metastasis sites) with a completeness % and named gaps.
Field names echo mCODE; not a certified exporter.

- **Try it:** mCODE summary tab → pick `patient_004_her2.json`. Expect
  breast cancer, HER2 biomarker, ECOG 0, completeness % + gaps.
- **API:** `POST /api/mcode` `{bundle}`.
- **Proof:** `Tier12Tests` (lung + breast ×2), e2e `mCODE profile
  extracted`.

### 16. Model validity — the matcher, independently benchmarked

Scores the matcher's rules on the n2c2 2018 cohort-selection task
(13 criteria) as micro-averaged F1. Ships with a tiny synthetic fixture
(F1 = 1.0); the full labeled set is DUA-gated and never downloaded —
drop it under `data/n2c2/` (`{id}.txt` + `labels.csv`) and run
`python -m backend.agents.n2c2_harness data/n2c2`.

- **Try it:** Model validity tab → Refresh benchmark. Expect fixture
  micro-F1 1.0 across 13 criteria + real-data status + DUA instructions.
- **API:** `GET /api/n2c2-status`.
- **Proof:** `Tier12Tests.test_n2c2_fixture_perfect`, e2e `validity
  benchmark reports fixture F1`.

### 17. Relaxation sweep — which threshold is actually binding?

Re-runs the matcher over a twin cohort at progressively relaxed
thresholds per numeric (sub-)rule and reports eligibility ladders:
who newly flips to ELIGIBLE at each step, plus marginal flips
(patients failing ONLY that criterion at baseline). Flat ladders are
honest output — the threshold simply isn't binding for that cohort.

- **Try it:** Cohort matching tab → Run relaxation sweep (patient-001
  seed, 20 twins). Expect 5 criteria with ladders over 20 twins and a
  baseline eligible count near 19.
- **API:** `POST /api/relax-sweep`
  `{protocol_id, twin_seed_bundle_id?, twins_n?, seed?, bundles?}`.
- **Proof:** `STrackTests` sweep ×3, e2e `sweep returns ladders over twins`.

### 18. Failure forensics — why are we screen-failing?

Aggregates every stored cohort run into per-criterion fail / missing /
trigger rates with ranked top drivers — the evidence base for
amendment discussions ("EXC-01 triggers X% of screens").

- **Try it:** History & export tab → run Cohort matching first, then
  Refresh forensics. Expect per-criterion rates plus a ranked driver
  list over all stored evaluations.
- **API:** `GET /api/forensics?protocol_id=PROT-TNX-001`.
- **Proof:** `STrackTests` forensics ×1, e2e `forensics aggregates
  stored runs`.

### 19. Retention risk — dropout radar per patient

Deterministic bootloader scorer combining visit burden with frailty
proxies (age, ECOG, polypharmacy, comorbidity count) into a 0–100
score with low/moderate/high bands, named factors, and a what-if
rescore with convertible visits done remotely.

- **Try it:** Cohort matching tab → Retention panel, pick
  `patient_001_breast_cancer.json`. Expect a moderate-band score with
  ≥ 2 factors and a what-if delta ≤ 0 (remote visits never hurt).
- **API:** `POST /api/retention` `{protocol_id, bundle}`.
- **Proof:** `STrackTests` retention ×1, e2e `retention scores with
  what-if`.

Trial-level companion: **attrition prediction** (`GET
/api/attrition/{id}`) estimates expected dropout % from an 18%
literature baseline adjusted for trial demands (the duration proxy —
strongest published predictor), observed SAEs, and DCT relief, with a
heuristic interval and named drivers. Rendered under the retention
panel; proof `AttritionTests` ×1, e2e `attrition predicts bounded
dropout`.

### 20. Outcome benchmark — what did similar trials achieve?

Benchmarks the indication against completed CT.gov trials: counts,
results-reporting rate, median enrollment, and outcome-measure
patterns, with `live` / `cache` / `offline-fallback` source chips.

- **Try it:** Protocol audit tab → Outcome benchmark (condition
  prefilled from the protocol). Expect hundreds of completed NSCLC
  trials with a results rate and median enrollment.
- **API:** `GET /api/outcome-benchmark?condition=…&phase=…`.
- **Proof:** `STrackTests` outcomes ×1, e2e `outcome benchmark returns
  registry shape`.

### 21. PDF protocol ingestion — audit the original file

Extracts text from uploaded protocol PDFs (pypdf, capped at 30 pages /
120K chars / 25 MB) and runs the standard audit over it — same rules,
same JSON, stored under a `PDF-<name>` protocol id. Transported as
base64 JSON, so no multipart dependency. Scanned-image PDFs without a
text layer fail with a plain-language message, not a traceback.

- **Try it:** Protocol audit tab → choose any text-based PDF → Audit
  PDF. Expect the id set to `PDF-<name>` and the full audit render
  (criteria, flaws, structure, burden, outlook) below.
- **API:** `POST /api/audit-pdf`
  `{filename, pdf_base64, protocol_id?}`.
- **Proof:** `PdfIngestTests` ×3 (round-trip, non-PDF, empty),
  `DeleteProtocolTests` ×1, e2e `PDF audit matches text audit`,
  `PDF protocol deletes cleanly` (`DELETE /api/protocols/{id}`).

### 22. PubMed literature — grounding for safety calls

NCBI Entrez esearch + esummary lookup (no API key): hit counts plus
PMID/title/journal/year cards with `live` / `cache` / `offline-fallback`
source chips, disk-cached like the CT.gov lookups.

- **Try it:** Safety triage tab → Literature → Search (prefilled with
  an EGFR hepatotoxicity term). Expect hit counts plus linked PMID
  cards, or an honest empty state offline.
- **API:** `GET /api/pubmed?term=…&retmax=5`.
- **Proof:** `PubMedTests` ×2 (offline parsers, never-crashes fetch),
  e2e `pubmed returns literature shape`.

### 23. Safety signal detection — ROR/PRR over drug-event pairs

Frequentist disproportionality screening: PRR + χ² (Evans criteria:
n ≥ 3, PRR ≥ 2, χ² ≥ 4) and ROR with 95% CI per (suspect drug,
MedDRA preferred term) pair, with 0.5 continuity correction. Honest
small-trial behavior: watch/insufficient-comparator instead of
manufactured signals. AE seeds span TNX-101 vs Placebo arms so the
liver cluster screens as a watch (PRR 5.0).

- **Try it:** Safety triage tab → Screen records above. Expect 0
  signals, a watch list topped by the TNX-101 liver pair, and the
  basis note.
- **API:** `POST /api/safety-signals` `{records}`.
- **Proof:** `SignalTests` ×3 (known-table math, zero-cell, statuses),
  e2e `signals flag liver cluster as watch`.

### 24. DCT readiness — which visits can go remote, and how

Maps each visit's procedures onto decentralized modalities (eConsent,
ePRO, local labs, home nursing, wearables, televisit) vs must-stay
on-site work (dosing, invasive, intensive same-day PK), with a trial
readiness score. Follows the 2025 DCT adoption pattern.

- **Try it:** Protocol audit tab → scroll to DCT readiness. Expect
  score 67: Day 1 on-site (PK series), Day 14 via home
  nursing/local imaging, Day 16 televisit.
- **API:** `GET /api/dct-readiness/PROT-TNX-001`.
- **Proof:** `DctTests` ×1, e2e `dct readiness grades visits`.

### 25. Criteria design feedback — grade every rule A/B/C

Rule-based edition of TrialBench's criteria-design task: vague
qualifiers, bundled multi-rule lines, missing units, and windowless
therapy statements each cost points, with concrete rewrite
suggestions per flag.

- **Try it:** Protocol audit tab → scroll to Criteria design. Expect
  score 64 with INC-04 graded C (vague "adequate" + 3 bundled
  sub-rules) and fix suggestions.
- **API:** `GET /api/criteria-feedback/PROT-TNX-001`.
- **Proof:** `CriteriaTests` ×1, e2e `criteria feedback grades INC-04
  worst`.

### Also: snapshot, demo feed, health

- `GET /health` → `{"status": "healthy", "mode": "zero-cost-local"}`.
- `GET /api/snapshot` → protocol/site/bundle/record/evaluation counts.
- `GET /api/demo-data` → prefill payload (sites, bundles, AE records).
- UI: http://localhost:8000/ · OpenAPI docs: http://localhost:8000/docs

## Testing guide

Three layers, cheapest first. Counts are for `main`
(`mvp` runs the 4-agent subset: 20 unit + 12 e2e).

```bat
:: Layer 1 — fast offline unit tests (no server): 69 tests (1 CI-only browser skip)
python -m unittest discover -s tests

:: Layer 2 — lint + format gate (dev only):
ruff check backend tests seed_data.py
ruff format --check backend tests seed_data.py

:: Layer 3 — live problem-statement checks (server running): 45 checks
uvicorn backend.app:app --port 8000     :: separate terminal, leave running
python tests/test_e2e_live.py          :: prints PASS/FAIL per check + FAILURES: 0
```

Every push to `main` or `mvp` runs all three layers plus a **core-parity
check** on GitHub Actions (see `.github/workflows/ci.yml`): the 4 cookbook
agents + synonyms + database + seed script must stay byte-identical across
both branches. `main` additionally runs a **browser pixel check**
(`tests/test_ui_pixel.py` in real Chromium, screenshot artifact).
Watch the Actions tab — green in ~4 minutes.

Local pixel run (no download when reusing a system browser):

```bat
pip install -r requirements-dev.txt
set TRIALNEXUS_BROWSER_TEST=1
set PLAYWRIGHT_CHANNEL=msedge   &:: or chrome
python -m unittest tests.test_ui_pixel -v
```

Manual testing per feature is covered above (each feature's **Try it**);
`TEST_GUIDE.md` keeps the same walkthrough as 13 numbered scenarios.

## Branches

| Branch | Contents | Tests |
|---|---|---|
| `main` | Full product: everything in this README | 69 unit + 45 e2e |
| `mvp` | Cookbook core: 4 agents, 8 endpoints, 4-tab UI | 20 unit + 12 e2e |

Rules: `main` evolves freely; `mvp` stays lean — never merge `main`
into it. Shared core fixes travel by checkout from `main`
(`git checkout main -- <core files>`) so the parity gate keeps passing.

## Storage footprint

| Item | Size |
|---|---|
| Repo tracked (code + seeds + docs) | ≈ 0.4 MB |
| SQLite DB after seeding | < 200 KB (generated; git-ignored) |
| CT.gov + PubMed caches | capped at 200 entries each, oldest forgotten first |
| Twins / simulations | in-memory only, never written to disk |
| Datasets downloaded | none (n2c2 real data is user-supplied, optional) |
| Core `.venv` (4 packages) | ~120 MB (only install cost) |
| Models downloaded | none |

## Configuration

All in `backend/config.py`: filesystem paths (DB, FHIR, protocols,
frontend), `CTGV_CACHE_MAX_ENTRIES = 200`,
`PUBMED_CACHE_MAX_ENTRIES = 200`, `N2C2_DATA_DIR`, and
`SCHEMA_VERSION` (bump when tables change; `init_db` stamps fresh and
old databases automatically).

Optional API token: set `TRIALNEXUS_API_TOKEN` before starting the
server and every `/api/*` call needs
`Authorization: Bearer <token>` (`/health`, `/`, `/docs` stay open).
Unset = fully open, as before. The UI prompts for the token once per
session when the server demands it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `API offline` pill / e2e "not reachable" | Start the server from `trialnexus/`: `uvicorn backend.app:app --port 8000` |
| Port 8000 busy | A stale server holds it — stop that python process, then start again |
| Match returns 400 "not audited yet" | Run the protocol audit once first (UI does this automatically) |
| API returns 401 "API token required" | Server was started with `TRIALNEXUS_API_TOKEN` — send it as a Bearer token (UI prompts once) |
| Counts look stale after edits | `python seed_data.py` re-seeds; the DB is disposable |
| Live CT.gov shows `offline-fallback` | No network or registry hiccup — scoring falls back gracefully |
| Fresh clone behaves oddly | `pip install -r requirements.txt` + `python seed_data.py`, then retest |

## Known limits (honest list)

- Washout windows cover dated TKI/medication statements; undated
  matches trigger conservatively; non-drug windows still use text evidence.
- Exotic multi-rule phrasings may split imperfectly — the audit JSON
  shows the parsed sub-rules for review.
- Diversity defaults are illustrative; plug in protocol-specific DAP targets.
- Twins probe measurement sensitivity only — never efficacy or safety.
- Outlook/attrition are calibrated bootloaders (disclosed coefficients) until fitted on TrialBench public data.
- Full n2c2 validation needs a data-use agreement; only the synthetic
  fixture ships.
- Single shared API token only — no per-user accounts or roles.
- Lexical retrieval (TF-IDF + synonym map), not embeddings; predictions use
  disclosed priors until fitted on sponsor history; no EHR/CTMS feeds.
- See "Where it falls short (gaps)" above for the full list.

## Companion docs

- `TEST_GUIDE.md` — the same tour as 13 numbered UI scenarios.
- `DELIVERY_STATUS.md` — cookbook input vs delivered, verification
  evidence, bug log.
- `PRODUCT_VALUE_MAP.md` — per-feature deliverables × product value.
