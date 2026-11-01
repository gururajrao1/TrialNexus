# TrialNexus — Input vs Delivered

## What was given as input

A cookbook spec for **TrialNexus OS**, a multi-agent clinical trials platform:

- 4 agents (Protocol Auditor, Site Scout, Cohort Matcher, Safety Triage) with
  system prompts and strict JSON contracts
- `EngineRouter`: OpenRouter Hermes-3-405B primary → Nemotron-70B fallback →
  NVIDIA NIM local fallback
- SQLite schema (4 tables: protocols, sites, patient_evaluations, safety_queries)
- FastAPI backend + Streamlit dashboard + Synthea FHIR seeds + CT.gov/PubMed hooks
- Prescribed `trialnexus/` file layout, seed script, and run commands

Session constraints added on top: **zero cost** (no OpenRouter / Nemotron / NIM
at all), **storage-light** (tiny repo, split dependencies, no model downloads),
built directly in this folder (no background agents after the direct-build switch).

## What is done (111 files, ≈ 1 MB working tree; SQLite DB generated)

| Cookbook item | Status | Delivered as |
|---|---|---|
| File layout | Done, adapted | `backend/`, `backend/agents/`, `frontend/`, `data/`, plus `tests/` and split requirements |
| SQLite 4-table schema | Done, exact | `backend/database.py` (WAL mode, stdlib only) |
| EngineRouter | Replaced per constraint | `backend/router.py` → `ZeroCostRouter`: optional local Ollama probe, else deterministic stub; agents never need it |
| Protocol Auditor + JSON | Done, deterministic | `backend/agents/protocol_auditor.py`: I/E parser, fragility index, SoA clash checks, Tufts-based $ exposure |
| Site Scout + JSON | Done, deterministic | `backend/agents/site_scout.py`: 35/25/20/20 formula, GO/CONDITIONAL/NO-GO; CT.gov helper cached with offline fallback |
| Cohort Matcher + JSON | Done, deterministic | `backend/agents/cohort_matcher.py`: FHIR R4 labs/conditions/meds/age → ELIGIBLE / INELIGIBLE / REVIEW_REQUIRED, negation-aware |
| Safety Triage + JSON | Done, deterministic | `backend/agents/safety_triage.py`: MedDRA SOC map, SAE rules, 7-day / 15-day clocks, drafted site queries |
| FastAPI app | Done, extended | `backend/app.py`: `/health`, `audit-protocol`, `score-sites`, `match-cohort`, `triage-safety` |
| Seed data + DB | Done, verified | `seed_data.py` (stdlib only) → 1 protocol, 2 sites |
| Sample protocol / AE stream / 2 FHIR bundles | Done | Under `data/` (1.2 KB, 1 KB, 2.1 KB each) |
| Browser UI | Done, served at `/` | Static `frontend/` (index.html, styles.css, app.js), zero extra deps; Streamlit removed |
| Live CT.gov lookup | Done, opt-in | Checkbox in Sites; cached counts with offline fallback + source chips |
| Diversity planner | Done | `backend/agents/diversity_planner.py` + 5th tab; OMB mix vs DAP-style goals |
| History + export | Done | Match/triage runs persisted; History tab + cohort/safety CSV endpoints |
| Structured export | Done | `structured_export.py`; M11-inspired JSON + download in Audit tab |
| Burden + DCT fit | Done | `burden_scorer.py`; per-visit scores + remote-fit verdict in Audit tab |
| Startup tracker | Done | `startup_tracker.py` + 7th tab; pipeline stages + benchmark flags |
| Monitoring lite | Done | `kri_monitor.py` + 8th tab; 5 KRIs vs tolerance limits, alert list |
| Trial finder | Done | `trial_finder.py` + 9th tab; reverse-rank 3 protocols per patient |
| External control | Done | `external_control.py` + 10th tab; relaxed pool + comparability + methods |
| Enrollment forecast | Done | `enrollment_forecast.py` + Sites panel; Poisson-Gamma P10/P50/P90 |
| Trial outlook | Done | `risk_models.py` + Audit panel; success P + 4-way failure split |
| Synthetic twins | Done | `twin_generator.py` + 11th tab; seeded jitter, in-memory, capped 500 |
| mCODE summary | Done | `mcode.py` + 12th tab; profile + completeness + gaps |
| n2c2 validity | Done | `n2c2_harness.py` + 13th tab; fixture F1 1.0, DUA path for real data |
| Note-aware matching | Done | Synonym table + DocumentReference search in matcher |
| Storage discipline | Done | 74 files ≈ 617 KB total; CT.gov cache capped at 200 entries |
| Central config | Done | `backend/config.py`; single source for paths + caps |
| Route modules | Done | `backend/routes/` core/product/tier; slim `app.py` |
| Schema versioning | Done | `schema_version` table; old DBs self-upgrade |
| Ruff gate | Done | `pyproject.toml` + `requirements-dev.txt`; tree normalized |
| CI | Done | `.github/workflows/ci.yml`: lint, seed, unit, e2e, core parity |
| Frontend modules | Done | `frontend/js/` ES modules; no build step |
| Multi-rule lines (V2) | Done | Auditor emits sub-rules + AND/OR logic; matcher evaluates all |
| Washout windows (V2) | Done | `within N days` parsed; TKI date math vs Day 1 |
| Creatinine units (V2) | Done | mg/dL ↔ µmol/L/mmol/L conversion in numeric checks |
| Note ECOG (V2) | Done | ECOG/KPS fallback from clinical notes |
| UI smoke test (V2) | Done | `tests/test_ui_smoke.mjs` + CI node step |
| Relaxation sweep (S1) | Done | `relaxation_sweep.py` + `/api/relax-sweep`; ladders + marginal flips over twins |
| Failure forensics (S2) | Done | `failure_forensics.py` + `/api/forensics`; rates + drivers over stored runs |
| Retention risk (S3) | Done | `retention.py` + `/api/retention`; 0–100 score + remote what-if |
| AE enrichment (S4) | Done | Temporality/attribution/certainty on every triage record + Signal column |
| Forecast priors (S5) | Done | `site_priors_from_metrics` + `use_site_history`; observed/provided tags |
| Outcome benchmark (S6) | Done | `fetch_ctgov_outcomes` + `/api/outcome-benchmark`; live/cache/fallback chips |
| Match provenance (S7) | Done | Per-evaluation match_type/confidence via `ENTAILMENT_BACKEND=rules-v1` |
| UI polish | Done | Portfolio stats, site-query fields, Yes/No cells — no stray JSON |
| Value map | Done | `PRODUCT_VALUE_MAP.md`: per-feature deliverables × product value |
| Smoke tests | Done, green | `tests/test_smoke.py`, stdlib unittest, 5/5 passing |
| Run docs | Done | `README.md` (VS Code quickstart, storage table, endpoints) |

## Verification evidence (observed, this machine)

- `compileall`: clean, no errors
- `seed_data.py`: DB 36.0 KB, `PROT-TNX-001` (1187 chars), counts
  `{protocols: 1, sites: 2, patient_evaluations: 0, safety_queries: 0}`
- `unittest`: 5/5 OK (1 cohort failure found and fixed during verification)
- Live API (`uvicorn backend.app:app --port 8000`): `/health` → healthy;
  live audit → fragility 20.5, 5 INC, 4 EXC, 1 flaw (Day 14/16 window clash)
- Interactive docs served at `http://127.0.0.1:8000/docs`
- Tier 1+2: `unittest` 26/26 OK; live e2e 30/30 PASS incl. outlook,
  forecast, twins, mCODE, n2c2-status, and complexity checks
- SE track: ruff clean; 26/26 unit + 30/30 e2e on main; 7/7 + 12/12 on mvp;
  main/mvp core parity exit 0
- V2: ruff clean; 39/39 unit + 30/30 e2e + UI smoke on main;
  20/20 unit + 12/12 e2e on mvp; parity exit 0
- S-track: ruff clean; 50/50 unit (incl. `STrackTests` ×11) + 36/36
  e2e + UI smoke on main; sweep e2e call hardened to 120 s timeout

## Bugs found and fixed during verification

1. `IN` operator on list values crashed numeric compare → direct membership check.
2. `"ast"` matched inside `"metastatic"` → histology criterion misrouted to AST
   lab check. Fixed with word-boundary matching + category-first dispatch.
3. `"anc"` matched inside `"performance"` → ANC compared against ECOG value.
   Fixed with word-boundary lab lookup.
4. Dead `patient_text[:0]` clause in pregnancy check → removed.
5. Same boundary hardening applied to auditor categories and MedDRA mapping
   (e.g. `"age"` vs `"stage"`, `"ast"` vs `"metastatic"`).
6. n2c2 MAKES-DECISIONS missed "makes own medical decisions" → rule now
   allows intervening words; fixture micro-F1 back to 1.0.
7. Test/twin code called a nonexistent matcher entry `evaluate` →
   corrected to `evaluate_patient`.
8. New UI panels assumed wrong module schemas → corrected to the real
   contracts (flat forecast percentiles, counts-based twins, nested
   mCODE profile, bootloader outlook).
9. E2E sweep call (12 s endpoint, 30 s budget) timed out 3× under machine
   load → per-call timeout (120 s) for that one heavy POST; suite green.

## Not done / remaining

- PubMed hookup (CT.gov live lookup is now wired into Sites; PubMed was lower value for the demo path).
- PDF protocol ingestion (txt/md only today).
- No auth / multi-user / deployment hardening (single-user local tool).

## Suggested next steps (domain)

1. Negation handling ("no prior TKI", "denies chest pain") before keyword hits.
2. Temporal washout checks (e.g. 28-day windows) using FHIR dates vs enrollment date.
3. Wider unit conversion (mg/dL ↔ µmol/L) and reference-range checks.
4. CT.gov live-competitor toggle in the dashboard; bulk Synthea import + CSV export.
