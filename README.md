# TrialNexus OS — zero-cost local clinical trials intelligence

TrialNexus is a multi-agent clinical trials platform that runs **entirely on
your machine**: protocol auditing, site feasibility, cohort matching, and
safety triage, plus a full product layer (diversity planning, startup
tracking, monitoring, trial finding, synthetic twins, and more).

There are no LLM calls, no API keys, no model downloads, and no paid
services. Every "agent" is a **deterministic function** with cited,
reproducible output — the same input always produces the same result.

## The problem it solves

Bringing a drug from Phase I to approval averages 10–12 years and over
$2.6B, much of it operational friction:

| Pain | Number | TrialNexus answer |
|---|---|---|
| Protocol amendments | 57% of protocols amended; ~$535K + 3 months per Phase III amendment | Protocol Auditor: machine-readable I/E rules, fragility index, $ exposure |
| Sites miss enrollment | ~80% of trials miss timelines; ~50% of sites under-/zero-enroll | Site Scout: objective 35/25/20/20 scoring + live CT.gov benchmarking |
| Screen failures | 30–50% (70%+ in precision oncology) | Cohort Matcher: FHIR-based prescreening with cited evidence |
| Safety/query lag | Manual triage under 7/15-day clocks | Safety Triage: MedDRA coding, SAE detection, drafted site queries |
| Diversity mandates | FDORA requires Diversity Action Plans | Diversity planner: mix-vs-goal gaps + catch-up math |
| Startup drag | 7–8 months site ID → activation | Startup tracker, enrollment forecast, trial outlook |

## 30-second tour — the 13 tabs

| # | Tab | What it does |
|---|---|---|
| 1 | Protocol audit | I/E extraction, fragility, $ exposure, M11 export, burden, outlook, outcome benchmarks, PDF upload |
| 2 | Site feasibility | Ranked sites + Poisson-Gamma forecast (optional observed-history priors) |
| 3 | Cohort matching | FHIR patients → ELIGIBLE / INELIGIBLE / REVIEW_REQUIRED + sweep + retention |
| 4 | Safety triage | AE triage with SAE flags, clocks, Signal column, enrichment, site queries, PubMed |
| 5 | Diversity plan | Enrollment mix vs goals, gaps, focus areas |
| 6 | History & export | Every run persisted; forensics; CSV downloads |
| 7 | Study startup | Pipeline stages vs benchmark flags |
| 8 | Monitoring | Central KRIs with alert/watch/ok per site |
| 9 | Find trials | Reverse match: patient → ranked trials |
| 10 | External control | Relaxed-criteria comparator pool + methods note |
| 11 | Synthetic twins | Measurement-sensitivity stress test (in-memory) |
| 12 | mCODE summary | Standard oncology profile + completeness |
| 13 | Model validity | Independent n2c2 benchmark of the matcher |

All tabs auto-run when the page loads. No login, no setup beyond the
quickstart below.

## Quickstart (VS Code)

Prerequisite: Python 3.11+.

```bat
:: 1. Open the trialnexus folder in VS Code, then in a terminal:
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt        :: 5 packages: fastapi, uvicorn, pydantic, httpx, pypdf

:: 2. Seed the database and run the fast suite (no server needed):
python seed_data.py
python -m unittest discover -s tests  :: 60 tests, ~40 seconds (1 CI-only browser skip)

:: 3. Start the API (leave running) and open the app:
uvicorn backend.app:app --port 8000
```

- UI: http://localhost:8000/
- Interactive API docs: http://localhost:8000/docs
- Live checks: `python tests/test_e2e_live.py` (39 checks, needs the server)

OneDrive tip: right-click `.venv` → "Free up space" to keep it on-demand.

## How it works without LLMs

| Cookbook agent | This build |
|---|---|
| Protocol Auditor | Regex I/E parser → INC/EXC rules, fragility index, SoA clash checks, readability metrics |
| Site Scout | 35/25/20/20 feasibility formula; CT.gov lookup cached with offline fallback; completed-trial outcome benchmarks |
| Cohort Matcher | FHIR R4 evaluator (labs, conditions, meds, age, notes) → ELIGIBLE / INELIGIBLE / REVIEW_REQUIRED, negation- and synonym-aware, with per-criterion provenance |
| Safety Triage | MedDRA SOC keyword map + SAE rules + 7-day / 15-day clocks + drafted site queries + temporality/attribution/certainty enrichment |
| EngineRouter | `ZeroCostRouter`: local Ollama if you run one, else deterministic stub (agents never need it) |

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
        │                      outcome-benchmark, pubmed
        └── routes/tier.py     outlook, forecast (+history), sweep, twins,
                               mcode, n2c2-status
        │
        ▼
agents  backend/agents/*.py  ── pure deterministic functions
        │  (protocol_auditor, site_scout, cohort_matcher, safety_triage,
        │   + 18 product/Tier/S/G modules; see Features)
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
│   └── agents/                  # 4 cookbook agents + 18 product/Tier/S/G modules
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
| `adverse_events_stream.json` | Routine liver signal, unexpected SAE, severe QTc, mild nausea |

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
(visit, remote check-in, or no action).

- **Try it:** Monitoring tab (auto-runs). Expect SITE-002 red with alert
  KRIs + visit recommendation, SITE-001 green, SITE-003 amber watch.
- **API:** `GET /api/monitoring`.
- **Proof:** `KRITest`, e2e `monitoring flags SITE-002 only`.

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

### 13. Trial outlook — success odds with named drivers

Transparent heuristic (HINT/TrialBench-inspired bootloader): literature
phase base rates discounted by fragility and burden, with a 4-way split
(success / enrollment / safety / efficacy failure) and plain-language
drivers. Disclosed as a heuristic until fitted on public HINT data.

- **Try it:** Protocol audit tab → scroll to Trial outlook. Expect a
  success probability (≈ 0.40 for PROT-TNX-001) with failure shares that
  sum to 1 and 4 drivers.
- **API:** `GET /api/trial-outlook/PROT-TNX-001`.
- **Proof:** `Tier12Tests.test_outlook_contract`, e2e `outlook returns
  success probability + breakdown`.

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

### Also: snapshot, demo feed, health

- `GET /health` → `{"status": "healthy", "mode": "zero-cost-local"}`.
- `GET /api/snapshot` → protocol/site/bundle/record/evaluation counts.
- `GET /api/demo-data` → prefill payload (sites, bundles, AE records).
- UI: http://localhost:8000/ · OpenAPI docs: http://localhost:8000/docs

## Testing guide

Three layers, cheapest first. Counts are for `main`
(`mvp` runs the 4-agent subset: 20 unit + 12 e2e).

```bat
:: Layer 1 — fast offline unit tests (no server): 60 tests (1 CI-only browser skip)
python -m unittest discover -s tests

:: Layer 2 — lint + format gate (dev only):
ruff check backend tests seed_data.py
ruff format --check backend tests seed_data.py

:: Layer 3 — live problem-statement checks (server running): 39 checks
uvicorn backend.app:app --port 8000     :: separate terminal, leave running
python tests/test_e2e_live.py          :: prints PASS/FAIL per check + FAILURES: 0
```

Every push to `main` or `mvp` runs all three layers plus a **core-parity
check** on GitHub Actions (see `.github/workflows/ci.yml`): the 4 cookbook
agents + synonyms + database + seed script must stay byte-identical across
both branches. Watch the Actions tab — green in ~2 minutes.

Manual testing per feature is covered above (each feature's **Try it**);
`TEST_GUIDE.md` keeps the same walkthrough as 13 numbered scenarios.

## Branches

| Branch | Contents | Tests |
|---|---|---|
| `main` | Full product: everything in this README | 60 unit + 39 e2e |
| `mvp` | Cookbook core: 4 agents, 8 endpoints, 4-tab UI | 20 unit + 12 e2e |

Rules: `main` evolves freely; `mvp` stays lean — never merge `main`
into it. Shared core fixes travel by checkout from `main`
(`git checkout main -- <core files>`) so the parity gate keeps passing.

## Storage footprint

| Item | Size |
|---|---|
| Repo working tree (code + seeds + docs) | ≈ 1 MB |
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
- Outlook is a transparent heuristic until fitted on HINT public data.
- Full n2c2 validation needs a data-use agreement; only the synthetic
  fixture ships.
- Single shared API token only — no per-user accounts or roles.

## Companion docs

- `TEST_GUIDE.md` — the same tour as 13 numbered UI scenarios.
- `DELIVERY_STATUS.md` — cookbook input vs delivered, verification
  evidence, bug log.
- `PRODUCT_VALUE_MAP.md` — per-feature deliverables × product value.
