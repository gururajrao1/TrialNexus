"""Seeded synthetic twin generator for eligibility stress-testing. Stdlib only.

Method (standard Monte Carlo sensitivity analysis, as used in probabilistic
sensitivity analysis for trial modelling): clone the index bundle n times,
jitter each numeric FHIR observation uniformly within ±jitter (default 15%,
a stress band wider than typical laboratory analytical variation, which is
single-digit percent), and re-run the full eligibility evaluation on every
twin. Reported outputs are the eligibility distribution with a Wilson score
95% interval (the standard binomial-proportion interval — better coverage
than the Wald/normal approximation at small n), the Monte Carlo standard
error, and per-criterion flip counts (one-way sensitivity: which single
threshold moves the verdict most often). Design exploration only: twins
probe measurement sensitivity, never efficacy or safety.
"""

from __future__ import annotations

import copy
import math
import random
from typing import Any

from backend.agents.cohort_matcher import evaluate_patient

MAX_TWINS = 2000
DEFAULT_JITTER = 0.15


def _clamp_jitter(jitter: float) -> float:
    return min(max(float(jitter), 0.0), 0.5)


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def _criterion_outcomes(
    ev: dict[str, Any],
) -> list[tuple[str | None, str, bool]]:
    """Per-criterion met/not-met outcomes in a stable order."""
    out = []
    for e in ev.get("inclusion_evaluations", []) or []:
        out.append((e.get("criterion_id"), "inclusion", bool(e.get("passed"))))
    for e in ev.get("exclusion_evaluations", []) or []:
        out.append((e.get("criterion_id"), "exclusion", not bool(e.get("triggered"))))
    return out


def make_twins(
    bundle: dict[str, Any], n: int, seed: int = 7, jitter: float = DEFAULT_JITTER
) -> list[dict[str, Any]]:
    """Clone a bundle n times with jittered numeric observations."""
    jitter = _clamp_jitter(jitter)
    rng = random.Random(seed)
    twins = []
    for i in range(max(0, min(n, MAX_TWINS))):
        t = copy.deepcopy(bundle)
        for e in t.get("entry", []):
            r = e.get("resource", {}) if isinstance(e, dict) else {}
            if r.get("resourceType") != "Observation":
                continue
            vq = r.get("valueQuantity")
            if isinstance(vq, dict) and isinstance(vq.get("value"), int | float):
                vq["value"] = round(vq["value"] * (1 + rng.uniform(-jitter, jitter)), 1)
        base = str(bundle.get("id") or "twin")
        t["id"] = f"{base}-twin-{i + 1}"
        for e in t.get("entry", []):
            r = e.get("resource", {}) if isinstance(e, dict) else {}
            if r.get("resourceType") == "Patient":
                r["id"] = t["id"]
        twins.append(t)
    return twins


def twin_distribution(
    criteria: dict[str, Any],
    bundle: dict[str, Any],
    n: int = 100,
    seed: int = 7,
    jitter: float = DEFAULT_JITTER,
) -> dict[str, Any]:
    """Eligibility distribution of n twins against structured criteria."""
    jitter = _clamp_jitter(jitter)
    twins = make_twins(bundle, n, seed, jitter)
    base = evaluate_patient(criteria, bundle)
    base_outcomes = _criterion_outcomes(base)
    counts = {"ELIGIBLE": 0, "INELIGIBLE": 0, "REVIEW_REQUIRED": 0}
    flips: dict[tuple[str, str | None], int] = {}
    for t in twins:
        ev = evaluate_patient(criteria, t)
        counts[ev["overall_status"]] = counts.get(ev["overall_status"], 0) + 1
        for (_, _, twin_met), (cid, kind, base_met) in zip(
            _criterion_outcomes(ev), base_outcomes
        ):
            if twin_met != base_met:
                key = (kind, cid)
                flips[key] = flips.get(key, 0) + 1
    total = max(1, sum(counts.values()))
    eligible = counts["ELIGIBLE"]
    lo, hi = _wilson_ci(eligible, total)
    p = eligible / total
    flip_rows = sorted(
        (
            {
                "criterion_id": cid,
                "kind": kind,
                "flips": c,
                "flip_rate": round(c / total, 3),
            }
            for (kind, cid), c in flips.items()
        ),
        key=lambda r: -r["flips"],
    )
    return {
        "n": total,
        "seed": seed,
        "jitter": jitter,
        "counts": counts,
        "eligible_pct": round(100.0 * p, 1),
        "eligible_ci95": [round(100.0 * lo, 1), round(100.0 * hi, 1)],
        "mc_se": round(100.0 * math.sqrt(p * (1 - p) / total), 2),
        "base_status": base["overall_status"],
        "flips": flip_rows,
        "note": (
            "Monte Carlo sensitivity: Wilson 95% interval and flip counts "
            "quantify measurement-sensitivity of the verdict; design "
            "exploration only, never efficacy or safety."
        ),
    }
