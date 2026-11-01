"""Agent 3 - Patient Cohort Matcher. FHIR bundles vs structured I/E criteria.

Deterministic, stdlib only. Output matches the cookbook JSON contract.
ELIGIBLE = all inclusions pass, no exclusion triggers.
INELIGIBLE = a hard fail. REVIEW_REQUIRED = critical data missing.
"""

from __future__ import annotations

import base64
import re
from datetime import date
from typing import Any

from backend.agents.synonyms import normalize

REF_DATE = date(2025, 6, 1)  # simulated enrollment target date (deterministic)

CELL_COUNT_UNITS = ("10^9", "/ul", "k/ul", "thou/ul", "cells/ul")
STOPWORDS = {
    "male",
    "female",
    "patients",
    "with",
    "without",
    "prior",
    "confirmed",
    "documented",
    "within",
    "history",
    "active",
    "stable",
    "days",
    "day",
    "must",
    "have",
    "than",
    "from",
    "that",
    "this",
    "are",
    "was",
    "were",
}


def _entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(bundle, dict):
        return []
    return [
        e.get("resource", {}) for e in bundle.get("entry", []) if isinstance(e, dict)
    ]


def _patient(bundle: dict[str, Any]) -> dict[str, Any]:
    for r in _entries(bundle):
        if r.get("resourceType") == "Patient":
            return r
    return {}


def patient_id(bundle: dict[str, Any]) -> str:
    p = _patient(bundle)
    return str(bundle.get("id") or p.get("id") or "UNKNOWN")


def patient_age(bundle: dict[str, Any], ref: date = REF_DATE) -> int | None:
    birth = _patient(bundle).get("birthDate")
    if not birth:
        return None
    try:
        b = date.fromisoformat(str(birth)[:10])
        return (ref - b).days // 365
    except ValueError:
        return None


def patient_sex(bundle: dict[str, Any]) -> str:
    return str(_patient(bundle).get("gender", "unknown")).lower()


def _obs_text(obs: dict[str, Any]) -> str:
    parts = []
    code = obs.get("code", {}) if isinstance(obs.get("code"), dict) else {}
    if code.get("text"):
        parts.append(str(code["text"]))
    for c in code.get("coding", []) or []:
        if isinstance(c, dict) and c.get("display"):
            parts.append(str(c["display"]))
    return " | ".join(parts)


def observations(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in _entries(bundle):
        if r.get("resourceType") != "Observation":
            continue
        val: Any = None
        unit: str | None = None
        vq = r.get("valueQuantity")
        if isinstance(vq, dict) and vq.get("value") is not None:
            val, unit = vq["value"], vq.get("unit") or vq.get("code")
        elif r.get("valueInteger") is not None:
            val = r["valueInteger"]
        elif r.get("valueString") is not None:
            val = r["valueString"]
        out.append(
            {
                "text": _obs_text(r),
                "value": val,
                "unit": unit,
                "date": r.get("effectiveDateTime", ""),
            }
        )
    return out


def conditions(bundle: dict[str, Any]) -> list[str]:
    out = []
    for r in _entries(bundle):
        if r.get("resourceType") != "Condition":
            continue
        code = r.get("code", {}) if isinstance(r.get("code"), dict) else {}
        bits = []
        if code.get("text"):
            bits.append(str(code["text"]))
        for c in code.get("coding", []) or []:
            if isinstance(c, dict) and c.get("display"):
                bits.append(str(c["display"]))
        if r.get("notes"):
            bits.append(str(r["notes"]))
        out.append(" | ".join(bits))
    return out


def medications(bundle: dict[str, Any]) -> list[str]:
    out = []
    for r in _entries(bundle):
        if r.get("resourceType") not in ("MedicationStatement", "MedicationRequest"):
            continue
        med = r.get("medicationCodeableConcept", {})
        if isinstance(med, dict):
            if med.get("text"):
                out.append(str(med["text"]))
            for c in med.get("coding", []) or []:
                if isinstance(c, dict) and c.get("display"):
                    out.append(str(c["display"]))
    return out


def clinical_notes(bundle: dict[str, Any]) -> list[dict[str, str]]:
    """Free-text notes from DocumentReference + note Observations."""
    out = []
    for r in _entries(bundle):
        rt = r.get("resourceType")
        if rt == "DocumentReference":
            t = r.get("type", {})
            section = str(t.get("text", "Note")) if isinstance(t, dict) else "Note"
            for c in r.get("content", []) or []:
                if not isinstance(c, dict):
                    continue
                att = c.get("attachment", {})
                raw = c.get("text") or (
                    att.get("data") if isinstance(att, dict) else ""
                )
                if raw and isinstance(att, dict) and att.get("data"):
                    try:
                        raw = base64.b64decode(str(raw)).decode("utf-8", "ignore")
                    except Exception:
                        pass
                if raw:
                    out.append({"section": section, "text": str(raw)})
        elif rt == "Observation":
            code = r.get("code", {}) if isinstance(r.get("code"), dict) else {}
            if "note" in str(code.get("text", "")).lower() and r.get("valueString"):
                out.append(
                    {"section": str(code["text"]), "text": str(r["valueString"])}
                )
    return out


def _notes_hit(ctx: dict[str, Any], *terms: str) -> str | None:
    """First note snippet affirming any term (negation-aware), or None."""
    for n in ctx.get("notes", []):
        low = n["text"].lower()
        for t in terms:
            for m in re.finditer(r"\b" + re.escape(t), low):
                window = low[max(0, m.start() - 45) : m.start()]
                if not any(x in window for x in NEGATIONS):
                    i = m.start()
                    return f"note ({n['section']}): ...{n['text'][max(0, i - 40) : i + 60]}..."
    return None


def _cmp(op: str, actual: float, expected: Any) -> bool:
    if op == ">=":
        return actual >= float(expected)
    if op == "<=":
        return actual <= float(expected)
    if op == ">":
        return actual > float(expected)
    if op == "<":
        return actual < float(expected)
    if op == "IN":
        return actual in list(expected)
    return actual == float(expected)


def _to_ul(value: float, unit: str | None) -> tuple[float, bool]:
    """Normalize cell counts to /uL. Returns (value, recognized)."""
    u = (unit or "").lower().replace(" ", "")
    if "10^9" in u or u in ("k/ul", "thou/ul", "cells/ul"):
        return value * 1000.0, True
    if u in ("/ul", "ul"):
        return value, True
    return value, False


def _has(blob: str, *keywords: str) -> bool:
    """Left word-boundary match over synonym-normalized text."""
    nb = normalize(blob)
    return any(re.search(r"\b" + re.escape(normalize(k)), nb) for k in keywords)


NEGATIONS = (
    "no ",
    "not ",
    "denies",
    "denied",
    "ruled out",
    "ruling out",
    "without",
    "negative for",
    "absence of",
    "free of",
    "never",
    "none ",
    "no evidence of",
)


def _affirmed(blob: str, *terms: str) -> bool:
    """Affirmed-term match over synonym-normalized text."""
    nb = normalize(blob)
    for t in terms:
        for m in re.finditer(r"\b" + re.escape(normalize(t)), nb):
            window = nb[max(0, m.start() - 45) : m.start()]
            if not any(n in window for n in NEGATIONS):
                return True
    return False


def _find_lab(obs: list[dict[str, Any]], *keywords: str) -> dict[str, Any] | None:
    for o in obs:
        if _has(o["text"].lower(), *keywords):
            return o
    return None


def _check_numeric(
    crit: dict[str, Any], lab: dict[str, Any] | None, label: str
) -> tuple[bool, str, bool]:
    """Returns (passed, evidence, missing)."""
    if lab is None or lab["value"] is None:
        return False, f"{label} not documented in FHIR record", True
    try:
        actual = float(lab["value"])
    except (TypeError, ValueError):
        return False, f"{label} value non-numeric: {lab['value']}", True
    expected = crit["value"]
    if isinstance(expected, list):
        ok = _cmp(crit["operator"], actual, expected)
    else:
        exp_f = float(expected)
        act_n, act_rec = _to_ul(actual, lab.get("unit"))
        exp_n, exp_rec = _to_ul(exp_f, crit.get("unit"))
        if act_rec or exp_rec:
            actual, exp_f = act_n, exp_n
        elif label == "Creatinine":
            act_c, act_ok = _to_mgdl(actual, lab.get("unit"))
            exp_c, exp_ok = _to_mgdl(exp_f, crit.get("unit"))
            if act_ok and exp_ok:
                actual, exp_f = act_c, exp_c
        ok = _cmp(crit["operator"], actual, exp_f)
    ev = (
        f"{label} was {lab['value']} {lab.get('unit') or ''} "
        f"on {lab.get('date') or 'undated'}; rule {crit['operator']} {expected}"
    )
    return ok, ev.strip(), False


def _content_words(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9\-]+", text.lower())
    return [w for w in words if len(w) > 4 and w not in STOPWORDS]


LAB_KEYS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("neutrophil", "anc"), "ANC"),
    (("platelet",), "Platelets"),
    (("hemoglobin", "hb"), "Hemoglobin"),
    (("creatinine",), "Creatinine"),
    (("crcl", "creatinine clearance"), "CrCl"),
    (("alt", "alanine"), "ALT"),
    (("ast", "aspartate"), "AST"),
    (("bilirubin",), "Bilirubin"),
    (("a1c", "hba1c", "hemoglobin a1c"), "HbA1c"),
)


def _eval_sub_rules(
    subs: list[dict[str, Any]],
    crit: dict[str, Any],
    ctx: dict[str, Any],
    done: Any,
) -> dict[str, Any]:
    """Multi-threshold lines: every sub-rule evaluated, combined by logic."""
    logic = crit.get("rule_logic", "all")
    results = []
    for s in subs:
        var = str(s.get("variable", ""))
        keys = next((k for k, _lbl in LAB_KEYS if _has(var.lower(), *k)), None)
        label = next((lbl for k, lbl in LAB_KEYS if k == keys), var) if keys else var
        lab = _find_lab(ctx["obs"], *keys) if keys else None
        sub = {
            "operator": s.get("operator"),
            "value": s.get("value"),
            "unit": s.get("unit"),
        }
        results.append(_check_numeric(sub, lab, label or "lab"))
    ev = "; ".join(e for _, e, _ in results)
    if logic == "any":
        if any(ok for ok, _, _ in results):
            return done(True, ev)
        if any(m for _, _, m in results):
            return done(False, ev, True)
        return done(False, ev)
    if all(ok for ok, _, _ in results):
        return done(True, ev)
    if any(not ok and not m for ok, _, m in results):
        return done(False, ev)
    return done(False, ev, True)


def _to_mgdl(value: float, unit: str | None) -> tuple[float, bool]:
    """Creatinine unit normalization to mg/dL. Returns (value, recognized)."""
    u = (unit or "").lower().replace(" ", "").replace("µ", "u").replace("μ", "u")
    if u in ("mg/dl", "mgdl"):
        return value, True
    if u in ("umol/l", "umol", "micromol/l"):
        return value / 88.4, True
    if u in ("mmol/l", "mmol"):
        return value * 11.312, True
    return value, False


def dated_medications(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Medication statements with parsed dates (None when undated)."""
    out = []
    for r in _entries(bundle):
        if r.get("resourceType") not in ("MedicationStatement", "MedicationRequest"):
            continue
        med = r.get("medicationCodeableConcept", {})
        text = ""
        if isinstance(med, dict):
            text = str(med.get("text") or "")
            if not text:
                for c in med.get("coding", []) or []:
                    if isinstance(c, dict) and c.get("display"):
                        text = str(c["display"])
                        break
        raw = r.get("effectiveDateTime") or (r.get("effectivePeriod", {}) or {}).get(
            "start"
        )
        when = None
        if raw:
            try:
                when = date.fromisoformat(str(raw)[:10])
            except ValueError:
                when = None
        if text:
            out.append({"text": text, "date": when})
    return out


def _eval_tki_washout(
    terms: tuple[str, ...],
    bundle: dict[str, Any],
    ctx: dict[str, Any],
    window: int,
    done: Any,
) -> dict[str, Any]:
    """Prior-TKI exclusion with real date math against the window."""
    ref = ctx.get("ref_date") or REF_DATE
    hits = [
        m for m in dated_medications(bundle) if _affirmed(m["text"].lower(), *terms)
    ]
    for h in hits:
        if h["date"] is None:
            return done(
                True,
                f"TKI '{h['text']}' undated; conservatively within {window}d window",
            )
    dated = [(h["text"], (ref - h["date"]).days) for h in hits if h["date"] is not None]
    within = [(t, d) for t, d in dated if d <= window]
    if within:
        t, d = min(within, key=lambda x: x[1])
        return done(True, f"TKI '{t}' {max(d, 0)} days before Day 1 (window {window}d)")
    if dated:
        t, d = min(dated, key=lambda x: x[1])
        return done(False, f"Last TKI '{t}' {d}d ago; outside {window}d window")
    if not ctx.get("meds", []):
        return done(False, "No medication history in record", True)
    return done(False, "No third-generation EGFR TKI in medication list")


def _negated_window(low: str, pos: int, width: int = 30) -> bool:
    return any(n in low[max(0, pos - width) : pos] for n in NEGATIONS)


KPS_TO_ECOG = ((100, 0), (80, 1), (60, 2), (40, 3), (20, 4), (0, 5))


def _note_performance(notes: list[dict[str, str]]) -> tuple[int, str] | None:
    """ECOG/KPS documented only in notes. Returns (ecog, snippet)."""
    for n in notes:
        low = n["text"].lower()
        m = re.search(r"\becog\b[^0-9]{0,10}(\d)", low) or re.search(
            r"performance status[^0-9]{0,10}(\d)", low
        )
        if m and not _negated_window(low, m.start()):
            i = m.start()
            return int(m.group(1)), n["text"][max(0, i - 20) : m.end() + 10].strip()
        k = re.search(r"\bk(?:arnofsky|ps)\b[^0-9]{0,10}(\d+)", low)
        if k and not _negated_window(low, k.start()):
            kv = int(k.group(1))
            eco = next(e for t, e in KPS_TO_ECOG if kv >= t)
            i = k.start()
            return eco, n["text"][max(0, i - 20) : k.end() + 10].strip()
    return None


def _eval_inclusion(
    crit: dict[str, Any], bundle: dict[str, Any], ctx: dict[str, Any]
) -> dict[str, Any]:
    cid = crit.get("id", "?")
    cat = str(crit.get("category", ""))
    blob = f"{crit.get('variable', '')} {crit.get('raw_text', '')}".lower()
    obs, conds = ctx["obs"], ctx["conds"]
    patient_text = ctx["patient_text"]
    missing = {
        "criterion_id": cid,
        "passed": False,
        "clinical_evidence_found": "",
        "missing_data": True,
    }

    def done(passed: bool, ev: str, miss: bool = False) -> dict[str, Any]:
        return {
            "criterion_id": cid,
            "passed": passed,
            "clinical_evidence_found": ev,
            "missing_data": miss,
        }

    if _has(blob, "age") or cat == "Demographic":
        age = ctx["age"]
        if age is None:
            return done(False, "birthDate missing; age unknown", True)
        pairs = re.findall(r"(>=|<=|>|<|=)\s*(\d+(?:\.\d+)?)", crit.get("raw_text", ""))
        if not pairs:
            pairs = [(crit.get("operator", ">="), str(crit.get("value", 0)))]
        oks = [(_cmp(op, float(age), float(n)), f"age {op} {n}") for op, n in pairs]
        if all(o for o, _ in oks):
            return done(True, f"Age {age} satisfies {', '.join(d for _, d in oks)}")
        failed = ", ".join(d for o, d in oks if not o)
        return done(False, f"Age {age} violates {failed}")
    if _has(blob, "ecog", "performance", "karnofsky"):
        lab = _find_lab(obs, "ecog", "performance", "karnofsky")
        noted = None
        if lab is None or lab.get("value") is None:
            noted = _note_performance(ctx.get("notes", []))
            if noted is not None:
                lab = {"value": noted[0], "unit": None, "date": None}
        passed, ev, miss = _check_numeric(crit, lab, "ECOG")
        if noted is not None and not miss:
            ev = f"ECOG {noted[0]} from clinical note ({noted[1]}); " + ev
        return done(passed, ev, miss)
    subs = crit.get("sub_rules") or []
    if len(subs) > 1:
        return _eval_sub_rules(subs, crit, ctx, done)
    for keys, label in LAB_KEYS:
        if cat not in ("Histology", "Biomarker") and _has(blob, *keys):
            passed, ev, miss = _check_numeric(crit, _find_lab(obs, *keys), label)
            return done(passed, ev, miss)
    # Histology / biomarker / fallback: key-term search in patient text.
    if not conds and not obs and not ctx["notes"]:
        missing["clinical_evidence_found"] = (
            "No conditions/observations/notes in record"
        )
        return missing
    for w in _content_words(normalize(crit.get("raw_text", ""))):
        if _affirmed(patient_text, w):
            i = patient_text.find(w)
            if i == -1:
                return done(
                    True, f"Criterion term '{w}' documented (via synonym normalization)"
                )
            return done(
                True,
                f"Criterion term '{w}' documented: ...{patient_text[max(0, i - 40) : i + 60]}...",
            )
        hit = _notes_hit(ctx, w)
        if hit:
            return done(True, hit)
    return done(
        False,
        "No supporting documentation found for: " + crit.get("raw_text", "")[:120],
    )


def _eval_exclusion(
    crit: dict[str, Any], bundle: dict[str, Any], ctx: dict[str, Any]
) -> dict[str, Any]:
    cid = crit.get("id", "?")
    blob = f"{crit.get('variable', '')} {crit.get('raw_text', '')}".lower()
    obs, conds, meds = ctx["obs"], ctx["conds"], ctx["meds"]
    med_text = " ".join(meds).lower()
    cond_text = " ".join(conds).lower()

    def done(triggered: bool, ev: str, miss: bool = False) -> dict[str, Any]:
        return {
            "criterion_id": cid,
            "triggered": triggered,
            "clinical_evidence_found": ev,
            "missing_data": miss,
        }

    if _has(blob, "tki", "tyrosine kinase", "egfr") and _has(blob, "prior"):
        tki = (
            "osimertinib",
            "erlotinib",
            "gefitinib",
            "afatinib",
            "dacomitinib",
            "tki",
            "tyrosine kinase",
        )
        window = crit.get("washout_days")
        if window:
            return _eval_tki_washout(tki, bundle, ctx, window, done)
        for m in meds:
            if _affirmed(m.lower(), *tki):
                return done(True, f"Prior TKI documented: {m}")
        if not meds:
            return done(False, "No medication history in record", True)
        return done(False, "No third-generation EGFR TKI in medication list")
    if _has(blob, "prior", "previous", "washout"):
        if not meds:
            return done(False, "No medication history in record", True)
        return done(False, "Medication list reviewed; no disqualifying prior therapy")
    if any(k in blob for k in ("brain", "cns", "spinal cord")):
        if not conds and not ctx["notes"]:
            return done(False, "No condition history in record", True)
        cond_hit = _affirmed(cond_text, "brain", "cns", "spinal")
        note_hit = _notes_hit(ctx, "brain", "cns", "spinal")
        if (cond_hit or note_hit) and not _has(cond_text, "stable", "treated"):
            ev = cond_text[:150] if cond_hit else note_hit
            return done(True, "Active CNS disease documented: " + ev)
        return done(False, "No active CNS metastases in condition/notes history")
    if _has(blob, "qtc", "qt", "cardiac", "heart failure"):
        lab = _find_lab(obs, "qtc", "qt interval", "ecg")
        if lab is not None and lab["value"] is not None:
            try:
                ms = float(lab["value"])
                limit = float(crit.get("value", 470))
                if ms > limit:
                    return done(True, f"QTc {ms} msec exceeds {limit} msec")
                return done(False, f"QTc {ms} msec within limit")
            except (TypeError, ValueError):
                pass
        if _affirmed(cond_text, "heart failure", "cardiac failure"):
            return done(True, "Heart failure documented: " + cond_text[:150])
        if lab is None:
            return done(False, "No ECG/QTc in record; cardiac history negative", True)
        return done(False, "Cardiac history negative")
    if _has(blob, "pregnan", "breastfeeding"):
        if _affirmed(cond_text, "pregnan") or _notes_hit(ctx, "pregnan") is not None:
            return done(True, "Pregnancy documented")
        age, sex = ctx["age"], ctx["sex"]
        if sex == "female" and age is not None and age < 50:
            if _find_lab(obs, "pregnancy", "hcg", "bhcg") is None:
                return done(
                    False, "Childbearing potential; no pregnancy test on file", True
                )
        return done(False, "No pregnancy documented" + (f"; age {age}" if age else ""))
    # Fallback: trigger only on explicit term match.
    for w in _content_words(normalize(crit.get("raw_text", ""))):
        if _affirmed(cond_text, w) or _affirmed(med_text, w):
            return done(True, f"Exclusion term '{w}' present in record")
        if _notes_hit(ctx, w):
            return done(True, f"Exclusion term '{w}' present in clinical note")
    return done(False, "No exclusion evidence in record")


def evaluate_patient(
    criteria: dict[str, Any],
    bundle: dict[str, Any],
    ref_date: date = REF_DATE,
) -> dict[str, Any]:
    """Evaluate one FHIR bundle against structured I/E criteria."""
    obs = observations(bundle)
    conds = conditions(bundle)
    ctx = {
        "obs": obs,
        "conds": conds,
        "meds": medications(bundle),
        "age": patient_age(bundle, ref_date),
        "sex": patient_sex(bundle),
        "patient_text": " ".join(conds + [o["text"] for o in obs]).lower(),
        "notes": clinical_notes(bundle),
        "ref_date": ref_date,
    }
    inc_evals = [
        _eval_inclusion(c, bundle, ctx) for c in criteria.get("inclusion_criteria", [])
    ]
    exc_evals = [
        _eval_exclusion(c, bundle, ctx) for c in criteria.get("exclusion_criteria", [])
    ]
    hard_fail = any(
        not e["passed"] and not e["missing_data"] for e in inc_evals
    ) or any(e["triggered"] for e in exc_evals)
    any_missing = any(e["missing_data"] for e in inc_evals) or any(
        e["missing_data"] for e in exc_evals
    )
    if hard_fail:
        status = "INELIGIBLE"
    elif any_missing:
        status = "REVIEW_REQUIRED"
    else:
        status = "ELIGIBLE"
    total_inc = len(inc_evals) or 1
    pct = round(100.0 * sum(1 for e in inc_evals if e["passed"]) / total_inc, 1)
    actions: list[str] = []
    for e in inc_evals:
        if e["missing_data"]:
            actions.append(
                f"Obtain missing data for {e['criterion_id']}: {e['clinical_evidence_found']}"
            )
        elif not e["passed"]:
            actions.append(f"Counsel: inclusion {e['criterion_id']} not met.")
    for e in exc_evals:
        if e["missing_data"]:
            actions.append(
                f"Rule out exclusion {e['criterion_id']}: {e['clinical_evidence_found']}"
            )
        elif e["triggered"]:
            actions.append(f"Counsel: exclusion {e['criterion_id']} triggered.")
    return {
        "patient_id": patient_id(bundle),
        "overall_status": status,
        "match_percentage": pct,
        "inclusion_evaluations": inc_evals,
        "exclusion_evaluations": exc_evals,
        "physician_action_items": actions,
    }


def evaluate_cohort(
    criteria: dict[str, Any],
    bundles: list[dict[str, Any]],
    ref_date: date = REF_DATE,
) -> dict[str, Any]:
    """Evaluate many FHIR bundles; matches the cookbook JSON contract."""
    return {
        "matching_results": [evaluate_patient(criteria, b, ref_date) for b in bundles]
    }
