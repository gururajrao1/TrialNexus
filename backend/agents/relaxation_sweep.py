"""Criterion-relaxation sweep: eligible-n elasticity per threshold.

For each numeric inclusion (sub-)rule, re-evaluates ONLY that rule over
a cohort at progressively relaxed thresholds and reports how many
patients flip to ELIGIBLE. Incremental by construction: one full
baseline pass, then single-rule re-evals against cached per-patient
contexts — identical eligible sets to full re-evaluation at ~1/8 the
cost. Also reports marginal flips: patients failing ONLY that
criterion at baseline. Flat ladders are honest output: the threshold
simply isn't binding for that cohort. Deterministic, stdlib only.
"""

from __future__ import annotations

import copy
from typing import Any

from backend.agents.cohort_matcher import (
    eval_inclusion_rule,
    evaluate_cohort,
    match_context,
    patient_id,
)
from backend.agents.twin_generator import make_twins

LEVELS_DOWN = (0.9, 0.75, 0.6)
LEVELS_UP = (1.15, 1.35, 1.6)
MAX_IDS = 10
MAX_TWINS = 500


def ladder_for(operator: str, value: Any) -> list[Any]:
    """Relaxed thresholds for one rule. Empty when not relaxable."""
    if isinstance(value, bool):
        return []
    if operator in (">=", ">") and isinstance(value, int | float):
        return [round(value * f, 3) for f in LEVELS_DOWN]
    if operator in ("<=", "<") and isinstance(value, int | float):
        return [round(value * f, 3) for f in LEVELS_UP]
    if (
        operator == "IN"
        and isinstance(value, list)
        and value
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    ):
        return [max(value) + 1, max(value) + 2]
    return []


def _relaxed_rule(
    criterion: dict[str, Any], sub_idx: int | None, new_value: Any
) -> dict[str, Any]:
    crit = copy.deepcopy(criterion)
    subs = crit.get("sub_rules") or []
    if sub_idx is not None and len(subs) > 1:
        subs[sub_idx]["value"] = new_value
    elif crit.get("operator") == "IN":
        crit["value"] = sorted(set(list(crit.get("value", [])) + [new_value]))
    else:
        crit["value"] = new_value
    return crit


def _eligible_set(results: list[dict[str, Any]]) -> set[str]:
    return {r["patient_id"] for r in results if r["overall_status"] == "ELIGIBLE"}


def sweep(
    criteria: dict[str, Any],
    bundles: list[dict[str, Any]],
    twins_n: int = 0,
    seed: int = 7,
) -> dict[str, Any]:
    pool = bundles
    source = f"{len(bundles)} bundles"
    if twins_n > 0:
        if not bundles:
            raise ValueError("twins mode needs one seed bundle")
        pool = make_twins(bundles[0], min(twins_n, MAX_TWINS), seed)
        source = f"{len(pool)} twins of {patient_id(bundles[0])}"
    base_results = evaluate_cohort(criteria, pool)["matching_results"]
    base_ids = _eligible_set(base_results)
    by_id = {r["patient_id"]: r for r in base_results}
    # Per-patient cached contexts + baseline criterion outcomes, so each
    # ladder level re-evaluates only the relaxed rule (same code path as
    # full evaluation, identical eligible sets).
    ctx_by_id = {patient_id(b): match_context(b) for b in pool}
    bundle_by_id = {patient_id(b): b for b in pool}
    ok_rest: dict[str, dict[str, bool]] = {}
    for pid, r in by_id.items():
        inc_ok = {
            e["criterion_id"]: bool(e["passed"]) and not e["missing_data"]
            for e in r.get("inclusion_evaluations", [])
        }
        exc_ok = not any(
            e["triggered"] or e["missing_data"]
            for e in r.get("exclusion_evaluations", [])
        )
        ok_rest[pid] = {"exc_ok": exc_ok, **{f"inc:{k}": v for k, v in inc_ok.items()}}

    def _level_ids(cid: str, rule: dict[str, Any]) -> set[str]:
        ids = set()
        for pid in by_id:
            rest = ok_rest[pid]
            if not rest["exc_ok"]:
                continue
            if any(
                not v
                for k, v in rest.items()
                if k.startswith("inc:") and k != f"inc:{cid}"
            ):
                continue
            e = eval_inclusion_rule(rule, bundle_by_id[pid], ctx_by_id[pid])
            if e["passed"] and not e["missing_data"]:
                ids.add(pid)
        return ids

    out_criteria = []
    for c in criteria.get("inclusion_criteria", []):
        cid = c["id"]
        marginal = sorted(pid for pid, r in by_id.items() if _only_hard_fail(r, cid))
        subs = c.get("sub_rules") or []
        if len(subs) > 1:
            targets = [
                (i, s.get("variable"), s.get("operator"), s.get("value"), s.get("unit"))
                for i, s in enumerate(subs)
            ]
        else:
            targets = [
                (
                    None,
                    c.get("variable"),
                    c.get("operator"),
                    c.get("value"),
                    c.get("unit"),
                )
            ]
        ladders = []
        for sub_idx, variable, op, val, unit in targets:
            levels = []
            for new_value in ladder_for(op, val):
                rule = _relaxed_rule(c, sub_idx, new_value)
                ids = _level_ids(cid, rule)
                new = sorted(ids - base_ids)
                levels.append(
                    {
                        "threshold": new_value,
                        "eligible_n": len(ids),
                        "newly_n": len(new),
                        "newly_eligible": new[:MAX_IDS],
                    }
                )
            ladders.append(
                {
                    "variable": variable,
                    "operator": op,
                    "base": val,
                    "unit": unit,
                    "ladder": levels,
                }
            )
        out_criteria.append(
            {
                "id": cid,
                "raw_text": c.get("raw_text", "")[:140],
                "marginal_flips": marginal,
                "marginal_n": len(marginal),
                "sub_sweeps": ladders,
            }
        )
    return {
        "source": source,
        "n_patients": len(pool),
        "baseline_eligible_n": len(base_ids),
        "criteria": out_criteria,
        "note": (
            "Each ladder relaxes one threshold at a time; newly_eligible counts "
            "patients flipping to ELIGIBLE. Marginal flips fail only that "
            "criterion with no missing data anywhere. Bundles must carry "
            "distinct patient ids (twins do by construction)."
        ),
    }


def _only_hard_fail(result: dict[str, Any], cid: str) -> bool:
    hard = [
        e["criterion_id"]
        for e in result.get("inclusion_evaluations", [])
        if not e["passed"] and not e["missing_data"]
    ]
    if hard != [cid]:
        return False
    if any(e["missing_data"] for e in result.get("inclusion_evaluations", [])):
        return False
    return not any(
        e["triggered"] or e["missing_data"]
        for e in result.get("exclusion_evaluations", [])
    )
