"""Central paths and runtime settings.

Single source of truth for filesystem locations and storage caps.
Always run from the project root (``uvicorn backend.app:app``,
``python seed_data.py``, ``python -m unittest discover -s tests``)
so ``from backend.config import ...`` resolves everywhere.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "local_db" / "trialnexus_state.db"
FHIR_DIR = DATA_DIR / "fhir" / "synthea"
PROTOCOLS_DIR = DATA_DIR / "raw" / "protocols"
QUERIES_DIR = DATA_DIR / "raw" / "queries"
AE_STREAM = QUERIES_DIR / "adverse_events_stream.json"
OUTPUTS_DIR = DATA_DIR / "outputs"
CTGV_CACHE = OUTPUTS_DIR / "ctgov_cache.json"
CTGV_CACHE_MAX_ENTRIES = 200
PUBMED_CACHE = OUTPUTS_DIR / "pubmed_cache.json"
PUBMED_CACHE_MAX_ENTRIES = 200
CLINVAR_CACHE = OUTPUTS_DIR / "clinvar_cache.json"
CLINVAR_CACHE_MAX_ENTRIES = 200
OPENFDA_CACHE = OUTPUTS_DIR / "openfda_cache.json"
OPENFDA_CACHE_MAX_ENTRIES = 200
REALWORLD_CACHE = OUTPUTS_DIR / "realworld_cache.json"
REALWORLD_CACHE_MAX_ENTRIES = 300
#: Run-history retention: keeps the SQLite store bounded on long-lived
#: demo DBs while leaving ample rows for forensics and monitoring.
HISTORY_CAP = 2000
INBOX_DIR = DATA_DIR / "inbox"
INBOX_BUNDLES_DIR = INBOX_DIR / "bundles"
N2C2_DATA_DIR = DATA_DIR / "n2c2"
N2C2_FIXTURE = ROOT / "tests" / "fixtures" / "n2c2_mini.json"

#: Bump when SCHEMA gains tables/columns; init_db stamps fresh and old DBs.
SCHEMA_VERSION = 2
