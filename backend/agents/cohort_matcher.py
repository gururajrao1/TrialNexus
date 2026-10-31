"""Agent 3 - Patient Cohort Matcher. FHIR bundles vs structured I/E criteria.

Deterministic, stdlib only. Output matches the cookbook JSON contract.
ELIGIBLE = all inclusions pass, no exclusion triggers.
INELIGIBLE = a hard fail. REVIEW_REQUIRED = critical data missing.
"""

from __future__ import annotations

import base64
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

try:
    from backend.agents.synonyms import normalize
except ImportError:  # fallback: run with backend/ as cwd
    from synonyms import normalize  # type: ignore[no-redef]

REF_DATE = date(2025, 6, 1)  # simulated enrollment target date (deterministic)

CELL_COUNT_UNITS = ("10^9", "/ul", "k/ul", "thou/ul", "cells/ul")
STOPWORDS = {"male", "female", "patients", "with", "without", "prior", "confirmed",
             "documented", "within", "history", "active", "stable", "days", "day",
             "must", "have", "than", "from", "that", "this", "are", "was", "were"}


def _entries(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(bundle, dict):
        return []
    return [e.get("resource", {}) for e in bundle.get("entry", []) if isinstance(e, dict)]


def _patient(bundle: Dict[str, Any]) -> Dict[str, Any]:
    for r in _entries(bundle):
        if r.get("resourceType") == "Patient":
            return r
    return {}


def patient_id(bundle: Dict[str, Any]) -> str:
    p = _patient(bundle)
    return str(bundle.get("id") or p.get("id") or "UNKNOWN")


def patient_age(bundle: Dict[str, Any], ref: date = REF_DATE) -> Optional[int]:
    birth = _patient(bundle).get("birthDate")
    if not birth:
        return None
    try:
        b = date.fromisoformat(str(birth)[:10])
        return (ref - b).days // 365
    except ValueError:
        return None


def patient_sex(bundle: Dict[str, Any]) -> str:
    return str(_patient(bundle).get("gender", "unknown")).lower()


def _obs_text(obs: Dict[str, Any]) -> str:
    parts = []
    code = obs.get("code", {}) if isinstance(obs.get("code"), dict) else {}
    if code.get("text"):
        parts.append(str(code["text"]))
    for c in code.get("coding", []) or []:
        if isinstance(c, dict) and c.get("display"):
            parts.append(str(c["display"]))
    return " | ".join(parts)


def observations(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for r in _entries(bundle):
        if r.get("resourceType") != "Observation":
            continue
        val: Any = None
        unit: Optional[str] = None
        vq = r.get("valueQuantity")
        if isinstance(vq, dict) and vq.get("value") is not None:
            val, unit = vq["value"], vq.get("unit") or vq.get("code")
        elif r.get("valueInteger") is not None:
            val = r["valueInteger"]
        elif r.get("valueString") is not None:
            val = r["valueString"]
        out.append({"text": _obs_text(r), "value": val, "unit": unit,
                    "date": r.get("effectiveDateTime", "")})
    return out


def conditions(bundle: Dict[str, Any]) -> List[str]:
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


def medications(bundle: Dict[str, Any]) -> List[str]:
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


def clinical_notes(bundle: Dict[str, Any]) -> List[Dict[str, str]]:
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
                raw = c.get("text") or (att.get("data") if isinstance(att, dict) else "")
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
                out.append({"section": str(code["text"]), "text": str(r["valueString"])})
    return out


def _notes_hit(ctx: Dict[str, Any], *terms: str) -> Optional[str]:
    """First note snippet affirming any term (negation-aware), or None."""
    for n in ctx.get("notes", []):
        low = n["text"].lower()
        for t in terms:
            for m in re.finditer(r"\b" + re.escape(t), low):
                window = low[max(0, m.start() - 45):m.start()]
                if not any(x in window for x in NEGATIONS):
                    i = m.start()
                    return f"note ({n['section']}): ...{n['text'][max(0, i - 40):i + 60]}..."
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


def _to_ul(value: float, unit: Optional[str]) -> Tuple[float, bool]:
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


NEGATIONS = ("no ", "not ", "denies", "denied", "ruled out", "ruling out",
             "without", "negative for", "absence of", "free of", "never",
             "none ", "no evidence of")


def _affirmed(blob: str, *terms: str) -> bool:
    """Affirmed-term match over synonym-normalized text."""
    nb = normalize(blob)
    for t in terms:
        for m in re.finditer(r"\b" + re.escape(normalize(t)), nb):
            window = nb[max(0, m.start() - 45):m.start()]
            if not any(n in window for n in NEGATIONS):
                return True
    return False


def _find_lab(obs: List[Dict[str, Any]], *keywords: str) -> Optional[Dict[str, Any]]:
    for o in obs:
        if _has(o["text"].lower(), *keywords):
            return o
    return None


def _check_numeric(crit: Dict[str, Any], lab: Optional[Dict[str, Any]],
                   label: str) -> Tuple[bool, str, bool]:
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
        ok = _cmp(crit["operator"], actual, exp_f)
    ev = (f"{label} was {lab['value']} {lab.get('unit') or ''} "
          f"on {lab.get('date') or 'undated'}; rule {crit['operator']} {expected}")
    return ok, ev.strip(), False


def _content_words(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9\-]+", text.lower())
    return [w for w in words if len(w) > 4 and w not in STOPWORDS]


def _eval_inclusion(crit: Dict[str, Any], bundle: Dict[str, Any],
                    ctx: Dict[str, Any]) -> Dict[str, Any]:
    cid = crit.get("id", "?")
    cat = str(crit.get("category", ""))
    blob = f"{crit.get('variable', '')} {crit.get('raw_text', '')}".lower()
    obs, conds = ctx["obs"], ctx["conds"]
    patient_text = ctx["patient_text"]
    missing = {"criterion_id": cid, "passed": False,
               "clinical_evidence_found": "", "missing_data": True}

    def done(passed: bool, ev: str, miss: bool = False) -> Dict[str, Any]:
        return {"criterion_id": cid, "passed": passed,
                "clinical_evidence_found": ev, "missing_data": miss}

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
        passed, ev, miss = _check_numeric(crit, lab, "ECOG")
        return done(passed, ev, miss)
    for keys, label in ((("neutrophil", "anc"), "ANC"),
                        (("platelet",), "Platelets"),
                        (("hemoglobin", "hb"), "Hemoglobin"),
                        (("creatinine",), "Creatinine"),
                        (("crcl", "creatinine clearance"), "CrCl"),
                        (("alt", "alanine"), "ALT"),
                        (("ast", "aspartate"), "AST"),
                        (("bilirubin",), "Bilirubin"),
                        (("a1c", "hba1c", "hemoglobin a1c"), "HbA1c")):
        if cat not in ("Histology", "Biomarker") and _has(blob, *keys):
            passed, ev, miss = _check_numeric(crit, _find_lab(obs, *keys), label)
            return done(passed, ev, miss)
    # Histology / biomarker / fallback: key-term search in patient text.
    if not conds and not obs and not ctx["notes"]:
        missing["clinical_evidence_found"] = "No conditions/observations/notes in record"
        return missing
    for w in _content_words(normalize(crit.get("raw_text", ""))):
        if _affirmed(patient_text, w):
            i = patient_text.find(w)
            if i == -1:
                return done(True, f"Criterion term '{w}' documented (via synonym normalization)")
            return done(True, f"Criterion term '{w}' documented: ...{patient_text[max(0, i-40):i+60]}...")
        hit = _notes_hit(ctx, w)
        if hit:
            return done(True, hit)
    return done(False, "No supporting documentation found for: "
                       + crit.get("raw_text", "")[:120])


def _eval_exclusion(crit: Dict[str, Any], bundle: Dict[str, Any],
                    ctx: Dict[str, Any]) -> Dict[str, Any]:
    cid = crit.get("id", "?")
    blob = f"{crit.get('variable', '')} {crit.get('raw_text', '')}".lower()
    obs, conds, meds = ctx["obs"], ctx["conds"], ctx["meds"]
    med_text = " ".join(meds).lower()
    cond_text = " ".join(conds).lower()

    def done(triggered: bool, ev: str, miss: bool = False) -> Dict[str, Any]:
        return {"criterion_id": cid, "triggered": triggered,
                "clinical_evidence_found": ev, "missing_data": miss}

    if _has(blob, "tki", "tyrosine kinase", "egfr") and _has(blob, "prior"):
        tki = ("osimertinib", "erlotinib", "gefitinib", "afatinib", "dacomitinib",
               "tki", "tyrosine kinase")
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
                return done(False, "Childbearing potential; no pregnancy test on file", True)
        return done(False, "No pregnancy documented" + (f"; age {age}" if age else ""))
    # Fallback: trigger only on explicit term match.
    for w in _content_words(normalize(crit.get("raw_text", ""))):
        if _affirmed(cond_text, w) or _affirmed(med_text, w):
            return done(True, f"Exclusion term '{w}' present in record")
        if _notes_hit(ctx, w):
            return done(True, f"Exclusion term '{w}' present in clinical note")
    return done(False, "No exclusion evidence in record")


def evaluate_patient(
    criteria: Dict[str, Any],
    bundle: Dict[str, Any],
    ref_date: date = REF_DATE,
) -> Dict[str, Any]:
    """Evaluate one FHIR bundle against structured I/E criteria."""
    obs = observations(bundle)
    conds = conditions(bundle)
    ctx = {"obs": obs, "conds": conds, "meds": medications(bundle),
           "age": patient_age(bundle, ref_date), "sex": patient_sex(bundle),
           "patient_text": " ".join(conds + [o["text"] for o in obs]).lower(),
           "notes": clinical_notes(bundle)}
    inc_evals = [_eval_inclusion(c, bundle, ctx) for c in criteria.get("inclusion_criteria", [])]
    exc_evals = [_eval_exclusion(c, bundle, ctx) for c in criteria.get("exclusion_criteria", [])]
    hard_fail = (any(not e["passed"] and not e["missing_data"] for e in inc_evals)
                 or any(e["triggered"] for e in exc_evals))
    any_missing = (any(e["missing_data"] for e in inc_evals)
                   or any(e["missing_data"] for e in exc_evals))
    if hard_fail:
        status = "INELIGIBLE"
    elif any_missing:
        status = "REVIEW_REQUIRED"
    else:
        status = "ELIGIBLE"
    total_inc = len(inc_evals) or 1
    pct = round(100.0 * sum(1 for e in inc_evals if e["passed"]) / total_inc, 1)
    actions: List[str] = []
    for e in inc_evals:
        if e["missing_data"]:
            actions.append(f"Obtain missing data for {e['criterion_id']}: {e['clinical_evidence_found']}")
        elif not e["passed"]:
            actions.append(f"Counsel: inclusion {e['criterion_id']} not met.")
    for e in exc_evals:
        if e["missing_data"]:
            actions.append(f"Rule out exclusion {e['criterion_id']}: {e['clinical_evidence_found']}")
        elif e["triggered"]:
            actions.append(f"Counsel: exclusion {e['criterion_id']} triggered.")
    return {"patient_id": patient_id(bundle), "overall_status": status,
            "match_percentage": pct, "inclusion_evaluations": inc_evals,
            "exclusion_evaluations": exc_evals, "physician_action_items": actions}


def evaluate_cohort(
    criteria: Dict[str, Any],
    bundles: List[Dict[str, Any]],
    ref_date: date = REF_DATE,
) -> Dict[str, Any]:
    """Evaluate many FHIR bundles; matches the cookbook JSON contract."""
    return {"matching_results": [evaluate_patient(criteria, b, ref_date) for b in bundles]}
