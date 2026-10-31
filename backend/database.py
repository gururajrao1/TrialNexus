"""SQLite persistence in WAL mode. Standard library only."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.config import DB_PATH as DEFAULT_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS protocols (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    phase TEXT NOT NULL,
    indication TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    structured_ie_criteria JSON,
    audit_results JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    city TEXT NOT NULL,
    historical_activation_days INTEGER,
    regulatory_tier TEXT,
    active_competing_trials INTEGER,
    feasibility_score REAL,
    feasibility_analysis JSON,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS patient_evaluations (
    id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL,
    patient_fhir_id TEXT NOT NULL,
    eligibility_status TEXT NOT NULL,
    inclusion_match_score REAL,
    exclusion_conflict_count INTEGER,
    rationale JSON,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(protocol_id) REFERENCES protocols(id)
);
CREATE TABLE IF NOT EXISTS safety_queries (
    id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL,
    patient_id TEXT,
    reported_term TEXT NOT NULL,
    suspected_meddra_soc TEXT,
    severity TEXT NOT NULL,
    is_sae BOOLEAN NOT NULL,
    reporting_timeline_hours INTEGER,
    query_text TEXT,
    resolution_status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS site_startup (
    site_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    history JSON,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS site_metrics (
    site_id TEXT NOT NULL,
    month TEXT NOT NULL,
    enrolled INTEGER NOT NULL,
    screened INTEGER NOT NULL,
    open_queries INTEGER NOT NULL,
    deviations INTEGER NOT NULL,
    sae INTEGER NOT NULL,
    PRIMARY KEY (site_id, month)
);
"""


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db(db_path: Optional[Path] = None) -> Path:
    path = Path(db_path) if db_path else DEFAULT_DB
    conn = get_connection(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return path


def insert_protocol(
    protocol_id: str,
    title: str,
    phase: str,
    indication: str,
    raw_content: str,
    db_path: Optional[Path] = None,
) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO protocols (id, title, phase, indication, raw_content)"
            " VALUES (?, ?, ?, ?, ?)",
            (protocol_id, title, phase, indication, raw_content),
        )
        conn.commit()
    finally:
        conn.close()


def get_protocol(protocol_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM protocols WHERE id = ?", (protocol_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_protocol_audit(
    protocol_id: str,
    structured_ie: Dict[str, Any],
    audit: Dict[str, Any],
    db_path: Optional[Path] = None,
) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE protocols SET structured_ie_criteria = ?, audit_results = ? WHERE id = ?",
            (json.dumps(structured_ie), json.dumps(audit), protocol_id),
        )
        conn.commit()
    finally:
        conn.close()


def upsert_site(site: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT INTO sites (id, name, country, city, historical_activation_days,
                                  regulatory_tier, active_competing_trials)
               VALUES (:id, :name, :country, :city, :historical_activation_days,
                       :regulatory_tier, :active_competing_trials)
               ON CONFLICT(id) DO UPDATE SET
                 name=excluded.name, country=excluded.country, city=excluded.city,
                 historical_activation_days=excluded.historical_activation_days,
                 regulatory_tier=excluded.regulatory_tier,
                 active_competing_trials=excluded.active_competing_trials,
                 updated_at=CURRENT_TIMESTAMP""",
            {
                "id": site["id"],
                "name": site["name"],
                "country": site["country"],
                "city": site["city"],
                "historical_activation_days": site.get("historical_activation_days"),
                "regulatory_tier": site.get("regulatory_tier"),
                "active_competing_trials": site.get("active_competing_trials"),
            },
        )
        conn.commit()
    finally:
        conn.close()


def save_site_feasibility(
    site_id: str, score: float, analysis: Dict[str, Any], db_path: Optional[Path] = None
) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE sites SET feasibility_score = ?, feasibility_analysis = ?,"
            " updated_at=CURRENT_TIMESTAMP WHERE id = ?",
            (score, json.dumps(analysis), site_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_sites(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM sites").fetchall()]
    finally:
        conn.close()


def table_counts(db_path: Optional[Path] = None) -> Dict[str, int]:
    conn = get_connection(db_path)
    try:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("protocols", "sites", "patient_evaluations", "safety_queries")
        }
    finally:
        conn.close()


def insert_patient_evaluation(row: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO patient_evaluations
               (id, protocol_id, patient_fhir_id, eligibility_status,
                inclusion_match_score, exclusion_conflict_count, rationale)
               VALUES (:id, :protocol_id, :patient_fhir_id, :eligibility_status,
                       :inclusion_match_score, :exclusion_conflict_count, :rationale)""",
            {
                "id": row["id"],
                "protocol_id": row["protocol_id"],
                "patient_fhir_id": row["patient_fhir_id"],
                "eligibility_status": row["eligibility_status"],
                "inclusion_match_score": row.get("inclusion_match_score"),
                "exclusion_conflict_count": row.get("exclusion_conflict_count", 0),
                "rationale": json.dumps(row.get("rationale", {})),
            },
        )
        conn.commit()
    finally:
        conn.close()


def list_patient_evaluations(
    protocol_id: Optional[str] = None, limit: int = 200, db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        if protocol_id:
            rows = conn.execute(
                "SELECT * FROM patient_evaluations WHERE protocol_id = ?"
                " ORDER BY evaluated_at DESC, rowid DESC LIMIT ?",
                (protocol_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM patient_evaluations ORDER BY evaluated_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def insert_safety_query(row: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO safety_queries
               (id, protocol_id, patient_id, reported_term, suspected_meddra_soc,
                severity, is_sae, reporting_timeline_hours, query_text, resolution_status)
               VALUES (:id, :protocol_id, :patient_id, :reported_term, :suspected_meddra_soc,
                       :severity, :is_sae, :reporting_timeline_hours, :query_text, :resolution_status)""",
            {
                "id": row["id"],
                "protocol_id": row["protocol_id"],
                "patient_id": row.get("patient_id"),
                "reported_term": row["reported_term"],
                "suspected_meddra_soc": row.get("suspected_meddra_soc"),
                "severity": row["severity"],
                "is_sae": bool(row.get("is_sae", False)),
                "reporting_timeline_hours": row.get("reporting_timeline_hours"),
                "query_text": row.get("query_text"),
                "resolution_status": row.get("resolution_status", "TRIAGED"),
            },
        )
        conn.commit()
    finally:
        conn.close()


def list_safety_queries(
    protocol_id: Optional[str] = None, limit: int = 200, db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        if protocol_id:
            rows = conn.execute(
                "SELECT * FROM safety_queries WHERE protocol_id = ?"
                " ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (protocol_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM safety_queries ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_startup_site(site_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM site_startup WHERE site_id = ?", (site_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_startup_site(
    site_id: str, stage: str, day: Optional[str] = None, note: str = "",
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Set a site's pipeline stage, appending to its dated history."""
    from datetime import date as _date

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM site_startup WHERE site_id = ?", (site_id,)
        ).fetchone()
        hist = json.loads(row["history"]) if row and row["history"] else []
        stamp = day or _date.today().isoformat()
        if stage == "identified":
            hist = []  # re-identification restarts the trail (also makes seeding idempotent)
        if not hist or hist[-1]["stage"] != stage:
            hist.append({"stage": stage, "date": stamp, "note": note})
        notes = ((row["notes"] + "\n" if row and row["notes"] else "") + note).strip() if note else (
            row["notes"] if row else "")
        conn.execute(
            """INSERT INTO site_startup (site_id, stage, history, notes, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(site_id) DO UPDATE SET stage=excluded.stage,
                 history=excluded.history, notes=excluded.notes,
                 updated_at=CURRENT_TIMESTAMP""",
            (site_id, stage, json.dumps(hist), notes),
        )
        conn.commit()
        fresh = conn.execute(
            "SELECT * FROM site_startup WHERE site_id = ?", (site_id,)
        ).fetchone()
        return dict(fresh)
    finally:
        conn.close()


def list_startup(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM site_startup ORDER BY site_id").fetchall()]
    finally:
        conn.close()


def list_protocols(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM protocols ORDER BY id").fetchall()]
    finally:
        conn.close()


def insert_site_metric(row: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """INSERT OR REPLACE INTO site_metrics
               (site_id, month, enrolled, screened, open_queries, deviations, sae)
               VALUES (:site_id, :month, :enrolled, :screened, :open_queries, :deviations, :sae)""",
            {
                "site_id": row["site_id"], "month": row["month"],
                "enrolled": row["enrolled"], "screened": row["screened"],
                "open_queries": row["open_queries"], "deviations": row["deviations"],
                "sae": row["sae"],
            },
        )
        conn.commit()
    finally:
        conn.close()


def list_site_metrics(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM site_metrics ORDER BY site_id, month").fetchall()]
    finally:
        conn.close()
