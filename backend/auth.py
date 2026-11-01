"""Optional bearer-token guard for /api/* (single-user local tool).

Off by default: set TRIALNEXUS_API_TOKEN to require
``Authorization: Bearer <token>`` on every /api/* call. The UI stays
open; only data endpoints are guarded. /health and /docs stay public
so liveness probes and schema browsing keep working.
"""

from __future__ import annotations

import os

HEADER = "authorization"
PREFIX = "bearer "


def api_token() -> str:
    """Live read so tests can monkeypatch the env var per case."""
    return os.environ.get("TRIALNEXUS_API_TOKEN", "")


def authorized(path: str, authorization: str | None) -> bool:
    """True when the request may proceed. Pure logic, unit-tested."""
    if not path.startswith("/api/"):
        return True
    token = api_token()
    if not token:
        return True
    if not authorization:
        return False
    return (
        authorization.lower().startswith(PREFIX)
        and authorization[len(PREFIX) :].strip() == token
    )
