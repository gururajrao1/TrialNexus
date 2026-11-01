"""Decentralized-trial (DCT) readiness per visit. Deterministic, stdlib only.

Maps each visit's procedures (from the burden scorer) onto decentralized
modalities — eConsent, ePRO/eDiary, local labs, home nursing, wearable /
remote monitoring, televisit — versus must-stay-on-site work (dosing,
invasive procedures, complex imaging). Follows the 2025 DCT adoption
pattern: remote follow-ups, local labs, and eConsent first; invasive and
infusion work stays on-site. Produces a per-visit matrix plus a trial
DCT-readiness score (0-100).
"""

from __future__ import annotations

from typing import Any

# procedure keyword -> (modality, on_site?)
MODALITIES = (
    ("consent", "eConsent with comprehension check", False),
    ("questionnaire", "ePRO / eDiary", False),
    ("diary", "ePRO / eDiary", False),
    ("survey", "ePRO / eDiary", False),
    ("labs", "local labs", False),
    ("blood draw", "home nursing / local labs", False),
    ("pk draws", "home nursing (timed draws)", False),
    ("ecg", "wearable / remote ECG", False),
    ("vitals", "wearable / remote monitoring", False),
    ("televisit", "televisit", False),
    ("follow-up", "televisit", False),
    ("imaging", "local imaging partner", False),
    ("infusion/dosing", "on-site dosing", True),
    ("biopsy", "on-site invasive", True),
)


def _modality(procedure: str, pk_units: int = 0) -> tuple[str, bool]:
    if "pk draws" in procedure and pk_units > 2:
        return "on-site: intensive same-day PK series", True
    for key, modality, on_site in MODALITIES:
        if key in procedure:
            return modality, on_site
    return "routine assessment", False


def dct_readiness(burden: dict[str, Any], raw_text: str = "") -> dict[str, Any]:
    """Per-visit DCT matrix + trial readiness score from burden output."""
    visits = []
    for v in burden.get("visits", []) or []:
        procs = v.get("procedures", []) or []
        mods = [_modality(p, int(v.get("pk_units", 0) or 0)) for p in procs] or [
            ("routine visit", False)
        ]
        on_site = [m for m, s in mods if s]
        remote = [m for m, s in mods if not s]
        if on_site:
            verdict = "on-site"
            reason = "requires " + ", ".join(sorted(set(on_site)))
        elif remote and remote != ["routine visit"]:
            verdict = "remote-capable"
            reason = "via " + ", ".join(sorted(set(remote)))
        else:
            verdict = "remote-capable"
            reason = "televisit candidate"
        visits.append(
            {
                "day": v.get("day"),
                "procedures": procs,
                "modalities": sorted(set(m for m, _ in mods)),
                "verdict": verdict,
                "reason": reason,
            }
        )
    n = len(visits)
    remote_n = sum(1 for v in visits if v["verdict"] == "remote-capable")
    score = round(100.0 * remote_n / n) if n else 0
    consent = "consent" in (raw_text or "").lower()
    return {
        "visits": visits,
        "remote_capable_n": remote_n,
        "total_visits": n,
        "readiness_score": score,
        "econsent_mentioned": consent,
        "basis": (
            "eConsent/ePRO/local-labs/home-nursing/televisit mapping follows "
            "2025 DCT adoption (remote follow-ups + local labs first); dosing "
            "and invasive work stays on-site."
        ),
    }
