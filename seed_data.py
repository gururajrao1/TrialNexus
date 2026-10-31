"""Seed TrialNexus SQLite state. Stdlib only. Run from the project root:

python seed_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.database import (  # noqa: E402
    init_db,
    insert_protocol,
    insert_site_metric,
    table_counts,
    upsert_site,
    upsert_startup_site,
)

PROTOCOL_ID = "PROT-TNX-001"

SITES = [
    {
        "id": "SITE-001",
        "name": "City Cancer Center",
        "country": "USA",
        "city": "Boston",
        "historical_activation_days": 75,
        "regulatory_tier": "Tier 1",
        "active_competing_trials": 3,
    },
    {
        "id": "SITE-002",
        "name": "Regional Oncology Hospital",
        "country": "India",
        "city": "Mumbai",
        "historical_activation_days": 140,
        "regulatory_tier": "Tier 3",
        "active_competing_trials": 7,
    },
    {
        "id": "SITE-003",
        "name": "Metro Research Institute",
        "country": "UK",
        "city": "London",
        "historical_activation_days": 95,
        "regulatory_tier": "Tier 2",
        "active_competing_trials": 4,
    },
]


def main() -> None:
    db = init_db()
    proto_file = ROOT / "data" / "raw" / "protocols" / "protocol_oncology_phase3.txt"
    raw_text = proto_file.read_text(encoding="utf-8")
    insert_protocol(
        PROTOCOL_ID,
        "Phase III Advanced NSCLC EGFR+ Trial",
        "Phase 3",
        "Non-Small Cell Lung Cancer",
        raw_text,
    )
    for pid, title, phase, ind, fname in [
        (
            "PROT-TNX-002",
            "Phase II HER2+ Breast Cancer Trial",
            "Phase 2",
            "Breast Cancer",
            "protocol_breast_phase2.txt",
        ),
        (
            "PROT-TNX-003",
            "Phase II Type 2 Diabetes Trial",
            "Phase 2",
            "Type 2 Diabetes Mellitus",
            "protocol_diabetes_phase2.txt",
        ),
    ]:
        insert_protocol(
            pid,
            title,
            phase,
            ind,
            (ROOT / "data" / "raw" / "protocols" / fname).read_text(encoding="utf-8"),
        )
    for site in SITES:
        upsert_site(site)
    from datetime import date, timedelta

    today = date.today()
    histories = {
        "SITE-001": [
            ("identified", 400),
            ("feasibility", 360),
            ("contract", 300),
            ("irb", 260),
            ("activated", 40),
        ],
        "SITE-002": [("identified", 300), ("feasibility", 200)],
        "SITE-003": [("identified", 120), ("feasibility", 80), ("contract", 30)],
    }
    for sid, hist in histories.items():
        for stage, days_ago in hist:
            upsert_startup_site(
                sid, stage, day=(today - timedelta(days=days_ago)).isoformat()
            )
    metrics = {
        "SITE-001": [
            ("2025-02", 3, 4, 3, 0, 0),
            ("2025-03", 3, 4, 4, 1, 0),
            ("2025-04", 4, 5, 4, 0, 0),
            ("2025-05", 3, 4, 3, 1, 0),
        ],
        "SITE-002": [
            ("2025-02", 1, 2, 8, 3, 0),
            ("2025-03", 0, 2, 9, 4, 1),
            ("2025-04", 1, 3, 7, 2, 0),
            ("2025-05", 0, 2, 8, 5, 1),
        ],
        "SITE-003": [
            ("2025-02", 2, 3, 5, 1, 0),
            ("2025-03", 2, 4, 6, 1, 0),
            ("2025-04", 3, 4, 5, 2, 0),
            ("2025-05", 2, 3, 6, 1, 0),
        ],
    }
    for sid, rows in metrics.items():
        for month, enrolled, screened, queries, deviations, sae in rows:
            insert_site_metric(
                {
                    "site_id": sid,
                    "month": month,
                    "enrolled": enrolled,
                    "screened": screened,
                    "open_queries": queries,
                    "deviations": deviations,
                    "sae": sae,
                }
            )
    print(f"DB: {db} ({db.stat().st_size / 1024:.1f} KB)")
    print(f"Protocol: {PROTOCOL_ID} ({len(raw_text)} chars from {proto_file.name})")
    print(f"Table counts: {table_counts()}")
    print("Seed complete.")


if __name__ == "__main__":
    main()
