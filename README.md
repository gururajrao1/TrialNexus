# TrialNexus OS — zero-cost local build

Multi-agent clinical trials intelligence (protocol audit, site feasibility,
cohort matching, safety triage) running fully offline. No OpenRouter, no
Nemotron, no NIM, no API keys, no model downloads.

## How it works without LLMs

Each cookbook agent is a deterministic function instead of a model call:

| Cookbook agent | This build |
|---|---|
| Protocol Auditor | Regex I/E parser → INC/EXC rules, fragility index, SoA clash checks |
| Site Scout | 35/25/20/20 feasibility formula; CT.gov lookup cached with offline fallback |
| Cohort Matcher | FHIR R4 bundle evaluator (labs, conditions, meds, age) → ELIGIBLE / INELIGIBLE / REVIEW_REQUIRED |
| Safety Triage | MedDRA SOC keyword map + SAE rules + 7-day / 15-day clocks + drafted site queries |
| EngineRouter | `ZeroCostRouter`: local Ollama if you run one, else deterministic stub (agents never need it) |

One rule per criterion line parses best; multi-rule lines (e.g. ANC + platelets
in one bullet) evaluate the first detected rule.

## Layout

```
trialnexus/
├── backend/                   # FastAPI app, router, SQLite layer
│   └── agents/                # 4 deterministic agents
├── frontend/                  # static browser UI (index.html, styles.css, app.js)
├── data/                      # protocol txt, AE stream, 2 FHIR bundles, SQLite DB
├── tests/test_smoke.py        # stdlib unittest suite
├── seed_data.py               # DB init + seed (stdlib only)
└── requirements.txt           # only install: fastapi, uvicorn, pydantic, httpx
```

## VS Code quickstart

Open this folder in VS Code, then in a terminal:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python seed_data.py
python -m unittest discover -s tests
uvicorn backend.app:app --port 8000
```

Then open the UI and API docs in your browser:

- UI: http://localhost:8000/
- API docs: http://localhost:8000/docs

## Storage footprint

| Item | Size |
|---|---|
| Repo (code + seeds) | < 100 KB |
| SQLite DB after seeding | < 100 KB |
| Core `.venv` (4 packages) | ~120 MB |
| Browser UI | 0 extra (static files served by the API) |
| Models downloaded | none (Ollama hook is optional and off by default) |

OneDrive tip: right-click `.venv` → "Free up space" to keep it on-demand.

## Endpoints

- `GET /health`
- `POST /api/audit-protocol/{protocol_id}`
- `POST /api/score-sites`
- `POST /api/match-cohort`
- `POST /api/triage-safety`
- `GET /api/snapshot`, `GET /api/demo-data` (UI feeds)
- `POST /api/diversity-plan`, `GET /api/diversity-defaults`
- `GET /api/history/cohort`, `/api/history/safety`, `/api/export/*.csv`
- `GET /api/protocol-structure/{id}`, `/api/burden/{id}`
- `GET /api/startup`, `POST /api/startup/{site}/advance`
- `GET /api/monitoring`, `POST /api/find-trials`, `/api/external-control`
