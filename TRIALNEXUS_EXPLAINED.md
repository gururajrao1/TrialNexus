# TrialNexus OS — the one-document explainer

**Name:** TrialNexus OS — zero-cost local clinical trials intelligence.

**One-liner:** a multi-agent clinical-trials workspace that runs entirely on
your machine: protocol auditing, site feasibility, cohort matching, and
safety triage, plus a full product layer (diversity planning, startup
tracking, monitoring, trial finding, synthetic twins, and more).

**The 10-second pitch:** bringing a drug from Phase I to approval averages
10–12 years and over $2.6B, much of it operational friction — amendments,
sites that never enroll, screen failures, safety-query lag. TrialNexus turns
each of those into a deterministic, cited computation that runs offline for
$0: no LLM calls, no API keys, no model downloads, no paid services. Every
"agent" is a pure function — the same input always produces the same result,
so every output is auditable.

Open the app at `http://127.0.0.1:8000/` (start it with
`python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`).
Interactive API docs live at `http://127.0.0.1:8000/docs`.
All 13 tabs auto-run on page load, and the **Run full workup** button in the
snapshot header re-runs the whole chain with progress status.

## The problem it solves

| Pain | Number | TrialNexus answer |
|---|---|---|
| Protocol amendments | 57% of protocols amended; ~$535K + 3 months per Phase III amendment | Protocol Auditor: machine-readable I/E rules, fragility index, $ exposure |
| Sites miss enrollment | ~80% of trials miss timelines; ~50% of sites under-/zero-enroll | Site Scout: 35/25/20/20 scoring + live CT.gov benchmarking |
| Screen failures | 30–50% (70%+ in precision oncology) | Cohort Matcher: FHIR-based prescreening with cited evidence |
| Safety/query lag | Manual triage under 7/15-day clocks | Safety Triage: MedDRA coding, SAE detection, drafted site queries |
| Diversity mandates | FDORA requires Diversity Action Plans | Diversity planner: mix-vs-goal gaps + catch-up math |
| Startup drag | 7–8 months site ID → activation | Startup tracker, enrollment forecast, trial outlook |

## How it works without LLMs

| Cookbook agent | This build |
|---|---|
| Protocol Auditor | Regex I/E parser → INC/EXC rules, fragility index, schedule-clash checks, readability metrics |
| Site Scout | 35/25/20/20 feasibility formula; CT.gov lookup cached with offline fallback |
| Cohort Matcher | FHIR R4 evaluator (labs, conditions, meds, age, notes) → ELIGIBLE / INELIGIBLE / REVIEW_REQUIRED; negation- and synonym-aware, with per-criterion provenance |
| Safety Triage | MedDRA SOC keyword map + SAE rules + 7/15-day clocks + drafted site queries + temporality/attribution/certainty enrichment |
| EngineRouter | `ZeroCostRouter`: local Ollama if you run one, else deterministic stub (agents never need it) |

Design rules: deterministic (seeded RNG, no clocks in logic), offline-first
(network only for the optional CT.gov / PubMed lookups, with cache +
fallback), storage-light (no datasets on disk; twins and simulations are
in-memory).

## Feature tour — test every tab

Seeded demo state: 3 protocols, 3 sites, 5 FHIR patient bundles, 10 safety
records. Protocol `PROT-TNX-001` is a Phase 3 NSCLC trial, target n=450.

### 1. Protocol audit — "will this protocol need an amendment?"

Click **01 Protocol audit → Run audit** (or Audit PDF with any text-based
protocol PDF; image-only scans fail with a plain message, not a traceback).
Expect: 5 inclusion + 4 exclusion rules as coded tables, fragility index
20.5/100 (Low band), 1 operational flaw (Day 14 vs Day 16 window clash),
amendment exposure ≈ $110,000 (fragility-scaled share of the $535K median).
Scrolling down: M11-inspired structured export with Download/Copy JSON,
visit-burden table (Day 1 = 18 from 6 PK draws, Day 14 = 10, Day 16 = 3,
33.3% remote-convertible), trial-outlook success probability with failure
breakdown, DCT-readiness matrix, criteria-design grades, adaptive-design
spending table, consent readability + jargon hits, and an outcome benchmark
against the live registry. Cross-links jump to site scoring, cohort
matching, and safety triage for the same protocol.
Same tab, lower down: **Sample size & budget** — size two proportions or
two means with dropout inflation (defaults p1 0.5 vs p2 0.4 give 864
total), check an NI margin against the 50%-preserved rule, and price a
site budget from your own rate card (the app only multiplies your numbers;
defaults price one 225-subject arm at screening + 6 cycles).
Same tab: an **amendment diff** — paste the current and amended protocol
texts and get added/dropped/rewritten criteria plus the fragility delta,
so the amendment call is answered criterion by criterion.

### 2. Site feasibility — "which sites will actually enroll?"

Click **04 Site feasibility → Score sites** (target 450). Expect: SITE-001
GO (80.5), SITE-003 CONDITIONAL (64.6), SITE-002 NO-GO (43.8), each with the
35/25/20/20 breakdown (velocity / competition / regulatory / capacity),
risks, a portfolio months-to-last-patient-in estimate, and a Poisson-Gamma
enrollment forecast (P10/P50/P90 from 20,000 simulations), plus a
history check: the same Gamma posterior hindcast against past site months
(MAE in patients/month — the forecast graded against its own past). Tick
**Use live CT.gov counts** to benchmark competitors against the real registry
(source chips read `live`, `cache`, or `offline-fallback`). Cross-links open
study startup and monitoring KRIs.

### 3. Cohort matching — "who can we enroll?"

Click **07 Cohort matching → Match cohort**. Expect: patient-001 ELIGIBLE
100%, patient-002 INELIGIBLE (low ANC + prior TKI trigger), patient-003
REVIEW_REQUIRED (missing ECOG, QTc, pregnancy test) with physician action
items. Open patient-003's exclusion evaluations to confirm the negation
check: "No evidence of brain metastases" does NOT trigger EXC-02. Same tab:
relaxation sweep (which threshold to relax, how many patients each step
buys), retention-risk score with a remote-visit what-if, and trial-level
attrition. Every criterion row carries provenance (match type + confidence),
resolved through a synonym table ("MI" = "myocardial infarction") and
DocumentReference notes. Same tab: prescreen queue ranks the coordinator
worklist by missing-data value (which lab unblocks the most patients
first).

### 4. Safety triage — "what needs a clock, and what needs a query?"

Click **12 Safety triage → Triage**. Expect: DISC-902 flagged SAE with
MedDRA Blood SOC, a 360-hour expedited clock, and a drafted site query; the
other records routine with correct SOC/grade mapping and no false alerts.
Further down: database-lock readiness, literature search (Safety → Search,
linked PMID cards), and an ROR/PRR signal screen that flags the liver
cluster as watch. Each AE row carries temporality, attribution, and
certainty enrichment. Same tab: CRF trace maps eCRF fields to criteria
coverage, and the query-aging upload re-ages any query file by owner with
SLA-breach rates. New in this tab: E2B export on every SAE record,
a DSUR shell compiled from the database ([FILL] marks prose you must write),
a risk register ranked from screened signals, and reviewer dispositions
(accept/refute/monitor) with an audit trail. Further down: **SAE
narratives & escalation** — one click drafts the narrative for the first
triaged SAE (template + [FILL], medical writer verifies) and routes the
aged queries up the site → CRA → sponsor chain; and a
**concomitant-med screen** that pulls the suspect drug's live FDA label
sections (ibuprofen + aspirin fires a warnings pointer; osimertinib
correctly fires nothing — its label speaks in drug-class terms).
Same feeds now also take **pasted CSV**: a real CTMS/EDC export is
alias-mapped to deviation or query rows (unmapped columns reported, never
silently dropped). Same tab: **site query letters** — every triaged record
with a site query becomes a copy-ready letter with [FILL] sign-off.

### 5. Diversity plan — "can we defend our enrollment mix?"

Click **02 Diversity plan**. Expect: enrollment mix vs goals per dimension
(race, ethnicity, sex, age) with gaps, on-track/at-risk/behind/off-track
status, catch-up numbers, and top-3 focus areas. Demo n is small, so most
groups show gaps — that is expected, and it is exactly the FDORA Diversity
Action Plan arithmetic.
Same tab: **enrolled actuals vs plan** — tick the enrolled bundles and
read the achieved mix against the same goals, so gaps show up as numbers
before the FDA asks.

### 6. History & export — "prove what we ran."

Run Cohort matching and Safety triage once, then click
**13 History & export → Refresh history**. Expect: persisted evaluation and
query rows with timestamps, CSV download links for both tables, and a
screen-failure forensics block ranking per-criterion fail/missing/trigger
rates with top drivers over all stored runs. Same tab, lower down:
**Portfolio, DSMB & competition** — a protocol rollup from the database,
a one-click DSMB pack shell (enrollment + safety counts, [FILL] for the
recommendation), and a live CT.gov competition check per indication
(NSCLC currently shows ~500 recruiting trials in the US).
Same tab: a **morning digest** (query pressure, at-risk startups, live
competition, ranked overdue-first — the standup screen) and a
**screening funnel** (eligible share plus week-by-week trail from stored
evaluations).

### 7. Study startup — "where is activation stuck?"

Click **05 Study startup**. Expect: SITE-002 carrying the at-risk flag,
SITE-001 clean. Advance SITE-003 to `activated` with a note and watch the
pipeline update against contract/IRB/activation benchmarks.
Same tab: milestone rollup (counts, flagged sites, next action per flag)
and an SIV checklist built from the audited protocol criteria. Same tab:
an **inspection readiness pack** — the BIMO-style exhibit list compiled
from the database (protocol on file, deviation count you enter, query and
SAE counts live) with TMF-only items honestly marked [FILL].
Same tab: a **study closeout pack** — the closeout mirror (lock
certificate, SAE reconciliations, deviation log with CAPA closures,
retention years you set) under the same honesty contract.

### 8. Monitoring — "which sites need a visit?"

Click **06 Monitoring** (auto-runs from monthly site metrics). Expect:
SITE-002 red with alert KRIs and a visit recommendation, SITE-001 green
with no action, SITE-003 amber watch — plus central statistical monitoring
flags and zero-enroll risk bands that separate the sites (low / high / low),
each with a Cox-Stuart trend read on the run-rate. Same tab: deviation
watch flags out-of-window visits, missing assessments, and consent
violations, with a binomial rate signal calling out outlier sites.
Same tab: a monitoring plan generated from the scored tiers (SDV depth and
visit cadence per site, escalation rule included); KRIs now extend to
consent/eligibility deviations and overdue queries when the feed carries them.
Same tab: a **visit report** built from the screened findings (counts by
severity plus the standard follow-up actions), a **deviation code & 5
whys** box mapping types to CDISC-style categories with a root-cause
scaffold and effectiveness check for the CAPA, and a **cross-site KRI
heatmap** — one row per site, one column per KRI, so the outlier site
reads across instead of down.

### 9. Find trials — "which trial fits this patient?"

Click **08 Find trials**, pick `patient_004_her2.json`, run; then
`patient_005_diabetes.json`. Expect: 004 ranks the breast trial #1 ELIGIBLE
with reasons, 005 ranks the diabetes trial #1 ELIGIBLE, others trailing as
INELIGIBLE with blocking criteria named. Same evaluator as site-side
matching, so both views can never disagree.

### 10. External control — "what do we compare a single arm against?"

Click **09 External control** (default relaxation `INC-04, EXC-01`).
Expect: comparator pool n=2 (001 strict + 002 via relaxation), near-miss
set, pool-mix comparability tables, and a methods note naming the relaxed
criteria and caveats. Relaxations are explicit, never silent.

### 11. Synthetic twins — "how sensitive is eligibility to measurement noise?"

Click **10 Synthetic twins**, generate ~100 twins of patient-001. Expect a
mostly-eligible mix with the ineligible share coming from jittered labs,
plus a Wilson 95% interval, Monte-Carlo SE, and a flip-driver table naming
the criterion that moves the verdict most. Change the seed and the number
moves; widen jitter from ±5% to ±25% and eligibility collapses (~100% to
~59%) — that is the sensitivity story. Up to 2,000 twins per run.
Design exploration only: twins probe measurement sensitivity, never efficacy
or safety, and nothing is stored.

### 12. mCODE summary — "is the oncology record complete?"

Click **11 mCODE summary**, pick patient-004. Expect: breast cancer, HER2
biomarker, ECOG 0, and a completeness percentage with gaps listed — the
standard oncology profile in one block. Contrast patient-005 (diabetes):
correctly 0% with no cancer fields and no EGFR hit — the kidney lab eGFR
no longer counts as the gene.

### 13. Model validity — "is the matcher itself any good?"

Click **03 Model validity**. Expect: fixture micro-F1 1.0 across 13
criteria, real-data status, and DUA instructions for the full n2c2 set —
an independent benchmark of the matcher, shipped in the product.

### 14. Warning letters — "has FDA already cited this failure?"

Click **13 Warning letters** in the sidebar. Expect: your five saved letters indexed by firm, CMS number, and violation themes (CAPA, design control, promotion…), then a cross-check box — type a finding in plain words ("site closed a CAPA with no effectiveness check") and get the ranked FDA violations it resembles, with the cited text, the trial-world analogue, and a suggested deviation tier that links to the owning panel.
Same tab: a **promotion copy check** — paste recruitment copy plus the approved indication and get off-indication terms plus FDA-cited promotion language flagged before anything goes out.

### 15. Trial matcher — "which real trials fit this patient?"

Click **15 Trial matcher** (Live search group). Type a plain-English description ("66-year-old woman, EGFR-mutant lung adenocarcinoma, prior osimertinib…") plus an optional location. The app distills searchable terms (raw prose is rejected by the registry), backs off from specific to broad when a rung returns nothing, ranks recruiting trials from clinicaltrials.gov, and explains each top hit against its own criteria — "likely met / possible conflict / check with the team", always with quotes, never "eligible".
Optional model layer, off by default: tick "Draft with my model endpoint" and the app also drafts note phrasing and a re-ranked order through your configured endpoint (TRIALNEXUS_MODEL_BASE_URL + TRIALNEXUS_LLM_ENABLED=1). Every draft is verified — verdict echo, verbatim quotes, permutation check — or discarded with a named warning; templates always decide.
Each hit now shows a 3-fact "at a glance" snapshot, a nearby-sites travel check (text match on your city — no geocoding), a referral letter, and a yes/no/unknown screening checklist. Watched searches persist in your browser; re-run them to catch newly posted trials.
Design debt to NIH TrialGPT (PMC11574183): four-label criterion verdicts (met / conflict / unknown / not-applicable), a synonym canonicalizer for its E2 error class (mutant = mutation…), exclusion-weighted trial scoring, and quoted explanations per criterion. Retrieval stays lexical (CT.gov `fields`-slimmed payloads, ~0.3KB vs ~75KB per study) instead of TrialGPT's LLM retrieval — the deterministic half of its retrieve → match → rank pipeline.

## 5-minute demo script (for explaining it to someone else)

1. Open the app. Point at the snapshot: "3 protocols, 3 sites, 5 patients,
   10 safety records — all local, all seeded, nothing leaves this machine."
2. Hit **Run full workup**. "One button runs the whole operations loop:
   design → select → enroll → monitor → document → optimize."
3. Open Protocol audit. "Fragility 20.5, one schedule clash, $110K
   exposure — this is the amendment we kill before it costs half a million."
4. Open Site feasibility. "GO / CONDITIONAL / NO-GO with the math shown —
   objective ranking instead of relationship picks."
5. Open Cohort matching. "001 eligible, 002 out on labs, 003 needs three
   tests — and note the negation: 'no brain mets' correctly does not
   trigger the brain-mets exclusion."
6. Open Safety triage. "One SAE with a 360-hour clock and a drafted query —
   the rest routine. That is the triage queue."
7. Close: "Every step is a deterministic function with cited output. Same
   input, same result, auditable by design — and it runs air-gapped inside
   a hospital firewall for zero dollars."

## Architecture (one picture in words)

```
browser (static ES modules, zero deps)
        │  same-origin JSON
        ▼
FastAPI  backend/app.py ── UI + static + routers
        ├── routes/core.py     health, snapshot, demo-data, audit,
        │                      audit-pdf, score-sites, match-cohort,
        │                      triage-safety
        ├── routes/product.py  diversity, history/export, structure,
        │                      burden, startup, monitoring, finder,
        │                      external-control, forensics, retention,
        │                      outcome-benchmark, pubmed, signals,
        │                      dct-readiness, criteria-feedback, attrition,
        │                      consent-check, csm, lock-readiness
        └── routes/tier.py     outlook, forecast, sweep, twins,
                               mcode, n2c2-status, adaptive-design
        ▼
agents  backend/agents/*.py ── 30 pure deterministic modules
        ▼
SQLite (WAL)  data/local_db/trialnexus_state.db ── via backend/database.py
```

Key endpoints: `POST /api/audit-protocol/{id}`, `POST /api/score-sites`,
`POST /api/match-cohort`, `POST /api/triage-safety`,
`POST /api/diversity-plan`, `GET /api/history/cohort`,
`GET /api/history/safety`, `GET /api/startup`,
`POST /api/startup/{site}/advance`, `GET /api/monitoring`,
`POST /api/find-trials`, `POST /api/external-control`,
`POST /api/relax-sweep`, `POST /api/retention`, `POST /api/twins`,
`POST /api/mcode`, `GET /api/n2c2-status`, `POST /api/audit-pdf`,
`GET /api/pubmed`, `POST /api/safety-signals`, `GET /api/forensics`.

## Data, setup, and proof

- Setup: `pip install -r requirements.txt` (5 packages: fastapi, uvicorn,
  pydantic, httpx, pypdf), `python seed_data.py`, then
  `python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`.
- Proof it works: `python -m unittest discover -s tests` (80 tests),
  `node tests/test_ui_smoke.mjs` (all panels render, 0 errors),
  `python tests/test_e2e_live.py` (45 live checks, 0 failures).
- Working agreements: stdlib-first, no new dependencies without asking;
  every run is reproducible; history persists in SQLite and exports as CSV.
- clinicaltrials.gov API v2 reuse map (one API, several features): 15 Trial
  matcher (search + rank + explain) and the outcomes benchmark (completed
  studies) already use it; mapped next are 04 Site feasibility (real
  candidate sites from each study's locations module, not just counts),
  05 Study startup (start/completion dates as activation benchmarks),
  08 Find trials (live protocols as an extra rankable corpus beside the
  seeded ones), and 06 Monitoring (competing-trial load per site as a
  workload signal). Same cache + source-chip pattern everywhere.

## Glossary for non-clinical audiences

- **FHIR** — the standard format for electronic health records; patients
  enter the app as FHIR bundles.
- **I/E criteria** — inclusion/exclusion rules defining who may join a trial.
- **MedDRA / SAE** — the standard dictionary for coding adverse events;
  an SAE (serious adverse event) starts regulatory clocks (7/15-day).
- **ICH M11** — the coming mandate for machine-readable protocols; the app
  exports one from any audited protocol.
- **DCT** — decentralized trial elements (e-visits, remote consent); the app
  scores per-visit remote fitness.
- **KRI** — key risk indicator; central monitoring watches a handful per
  site instead of checking everything everywhere.
- **ROR/PRR** — disproportionality statistics that flag drug–event pairs
  reported more often than background.
- **mCODE** — the standard minimal oncology record format.
- **n2c2** — a public de-identified clinical-NLP benchmark; the matcher is
  tested against its 2018 cohort-selection fixture.

## What it is not (honest limits)

- No real patient data ships with it — all bundles are synthetic seeds.
- Twins and forecasts are planning math, not clinical evidence.
- Live CT.gov and PubMed lookups need network and degrade to cache/offline
  gracefully; everything else is fully air-gapped.
- It drafts site queries and flags risks; a clinician still signs every
  decision.

