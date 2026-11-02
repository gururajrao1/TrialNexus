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
