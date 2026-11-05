"""User inbox: the user's own files, picked up by the app.

`data/inbox/` holds what the internet cannot provide: your protocols,
FHIR bundles, site lists, safety exports, visit records, query exports,
and eCRF field lists. Contents are git-ignored (never commit patient
data) and read on demand — nothing is imported into the database.
Deterministic, stdlib only. Never raises on bad files; reports errors.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import INBOX_BUNDLES_DIR, INBOX_DIR

#: Slot -> filename. `ecrf` is one-field-per-line text; the rest are JSON lists.
SLOTS = {
    "sites": "sites.json",
    "ae": "ae_records.json",
    "visits": "visits.json",
    "queries": "queries.json",
    "ecrf": "ecrf_fields.txt",
}


def _read_json_list(path: Path) -> tuple[bool, Any, str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return False, None, f"unreadable JSON: {exc}"
    if not isinstance(data, list):
        return False, None, "top level must be a JSON list"
    return True, data, ""


def list_inbox(inbox_dir: Path | None = None) -> dict[str, Any]:
    """Inventory the inbox: presence, row counts, and errors per slot."""
    root = inbox_dir or INBOX_DIR
    slots: dict[str, Any] = {}
    for slot, filename in SLOTS.items():
        path = root / filename
        if not path.exists():
            slots[slot] = {"present": False}
            continue
        if slot == "ecrf":
            try:
                lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
            except OSError as exc:
                slots[slot] = {"present": True, "error": f"unreadable: {exc}"}
                continue
            slots[slot] = {"present": True, "lines": len(lines)}
            continue
        ok, data, error = _read_json_list(path)
        if not ok:
            slots[slot] = {"present": True, "error": error}
        else:
            slots[slot] = {"present": True, "rows": len(data)}
    return {"slots": slots, "bundles": [b["name"] for b in scan_bundles(root)]}


def read_inbox_text(slot: str, inbox_dir: Path | None = None) -> tuple[bool, str]:
    """Raw inbox text for pasting into a form. (False, reason) when unusable."""
    if slot not in SLOTS:
        return False, f"unknown slot: {slot}"
    root = inbox_dir or INBOX_DIR
    path = root / SLOTS[slot]
    if not path.exists():
        return False, "not in your inbox yet — see data/inbox/README.md"
    if slot == "ecrf":
        try:
            text = path.read_text()
        except OSError as exc:
            return False, f"unreadable: {exc}"
        if not [ln for ln in text.splitlines() if ln.strip()]:
            return False, "inbox file is empty"
        return True, text
    ok, data, error = _read_json_list(path)
    if not ok:
        return False, error
    if not data:
        return False, "inbox file is empty"
    return True, json.dumps(data, indent=1)


#: CSV header aliases (lowercased, spaces/dashes stripped) per feed.
VISIT_ALIASES = {
    "site_id": ("site", "siteid", "sitecode", "center", "centerid"),
    "subject": ("subject", "subjectid", "patient", "patientid", "subjid"),
    "visit": ("visit", "visitname", "event", "eventname", "folder"),
    "planned_day": ("planned", "plannedday", "targetday", "scheduledday", "windowday"),
    "actual_day": ("actual", "actualday", "visitday", "performedday", "accountday"),
    "consent_date": ("consent", "consentdate", "icfdate", "signeddate"),
    "visit_date": ("visitdate", "date", "dos", "assessmentdate"),
    "assessments_required": (
        "required",
        "assessmentsrequired",
        "expected",
        "plannedassessments",
    ),
    "assessments_done": (
        "done",
        "assessmentsdone",
        "performed",
        "completedassessments",
    ),
}
QUERY_ALIASES = {
    "id": ("id", "queryid", "qid", "dataname", "query"),
    "created_at": ("created", "createdat", "date", "opendate", "raisedate", "dos"),
    "resolution_status": ("status", "resolutionstatus", "state", "resolution"),
    "is_sae": ("sae", "issae", "serious", "seriousae"),
}
_LIST_SPLIT = (";", "|")


def _norm_header(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _split_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    for sep in _LIST_SPLIT:
        if sep in text:
            return [p.strip() for p in text.split(sep) if p.strip()]
    return [text]


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "sae",
        "serious",
    )


def map_csv_records(text: str, target: str) -> dict[str, Any]:
    """Map a real CTMS/EDC CSV export to deviation-watch or query-aging rows.

    Header matching is alias-based and case-insensitive; unmapped columns
    are reported, never dropped silently. Never raises — bad input is an
    ``error``, matching the inbox convention.
    """
    import csv
    from io import StringIO

    aliases = {"visits": VISIT_ALIASES, "queries": QUERY_ALIASES}.get(
        str(target or "").lower()
    )
    if aliases is None:
        return {"records": [], "error": "target must be 'visits' or 'queries'"}
    try:
        rows = list(csv.DictReader(StringIO(str(text or ""))))
    except (csv.Error, ValueError) as exc:
        return {"records": [], "error": f"unreadable CSV: {exc}"}
    if not rows:
        return {"records": [], "error": "no data rows found"}
    headers = [_norm_header(h) for h in (rows[0].keys() or [])]
    col_of: dict[str, str] = {}
    for key, names in aliases.items():
        for raw, norm in zip(rows[0].keys() or [], headers):
            if norm in names and key not in col_of:
                col_of[key] = raw
                break
    unmapped = [
        raw
        for raw, norm in zip(rows[0].keys() or [], headers)
        if raw not in set(col_of.values())
    ]
    records = []
    for row in rows:
        rec: dict[str, Any] = {}
        for key, col in col_of.items():
            val = (row.get(col) or "").strip()
            if key in ("assessments_required", "assessments_done"):
                rec[key] = _split_list(val)
            elif key == "is_sae":
                rec[key] = _truthy(val)
            else:
                rec[key] = val
        if any(str(v).strip() for v in rec.values() if not isinstance(v, list)) or any(
            rec.get(k) for k in ("assessments_required", "assessments_done")
        ):
            records.append(rec)
    if not col_of:
        return {
            "records": [],
            "unmapped_columns": unmapped,
            "error": "no recognized columns — see unmapped_columns",
        }
    return {
        "records": records,
        "mapped_columns": col_of,
        "unmapped_columns": unmapped,
        "n_rows": len(records),
        "basis": "Alias-mapped CSV headers; verify one row before trusting a feed.",
    }


def scan_bundles(inbox_dir: Path | None = None) -> list[dict[str, Any]]:
    """User FHIR bundles, named inbox/<file>. Skips unreadable files."""
    root = inbox_dir or INBOX_DIR
    bundles_dir = INBOX_BUNDLES_DIR if root == INBOX_DIR else root / "bundles"
    out = []
    if not bundles_dir.exists():
        return out
    for p in sorted(bundles_dir.glob("*.json")):
        try:
            bundle = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(bundle, dict):
            out.append({"name": f"inbox/{p.name}", "bundle": bundle})
    return out
