"""Plain-English trial matcher: free-text description -> live CT.gov trials.

Given "66-year-old woman, EGFR-mutant lung adenocarcinoma, prior osimertinib",
this searches recruiting trials on clinicaltrials.gov, ranks them with stdlib
term-vectors (TF-IDF cosine — no dense-embedding dependency by design), and
explains each top hit in plain English against its own eligibility criteria.

Fail-closed like everything else in this app: verdicts are "worth discussing"
or "needs clinician review" — never "eligible". A doctor makes the call.
Disk-cached with offline fallback; never raises on bad input or bad network.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from typing import Any

from backend.config import REALWORLD_CACHE, REALWORLD_CACHE_MAX_ENTRIES

CTGV_STUDIES = "https://clinicaltrials.gov/api/v2/studies"
CACHE_PREFIX = "match|"
#: Slim payload: only the modules match_description parses. Verified against
#: the live API (327 bytes vs ~75KB per study unfiltered).
CTGV_FIELDS = (
    "NCTId,BriefTitle,OverallStatus,Condition,Phase,BriefSummary,"
    "EligibilityCriteria,Sex,MinimumAge,MaximumAge,"
    "LocationCity,LocationState,LocationCountry"
)
MAX_EXCERPT = 280
MAX_TRIALS = 10

MODEL_SYSTEM = (
    "You draft a one-sentence plain-English note for a clinical trial "
    "eligibility check. Reply with strict JSON only, no other text: "
    '{"plain": "<one sentence, plain words>", '
    '"quotes": ["<verbatim substrings of the criterion>"], '
    '"verdict": "likely met|possible conflict|check with the team"}. '
    "Quote ONLY the criterion text provided. The verdict MUST restate the "
    "given deterministic outcome. This is a draft for human review, never "
    "an eligibility decision."
)

RERANK_SYSTEM = (
    "You re-order clinical trial candidates for one patient description. "
    "Reply with strict JSON only, no other text: "
    '{"order": ["<nct ids, every input id exactly once>"], '
    '"reasons": {"<nct id>": "<one sentence quoting that trial\'s text>"}}. '
    "Every reason MUST contain a verbatim substring (15+ characters) of the "
    "trial's title, summary, or criteria shown. Never invent trials."
)

MODEL_BUDGET_DEFAULT = 6
RERANK_TOP_N = 6

_STOP = frozenset(
    "the a an and or of to in for on with is are was were be been by as at "
    "from that this it its into over under such each per our your their his her "
    "will shall may can not no more most than then there here which who whom "
    "what when where have has had do does did s t re ll ve d m year years old "
    "with has had".split()
)

_NEGATIONS = frozenset(
    {"no", "not", "without", "never", "none", "denies", "denied", "absence"}
)

#: Person-words and bare numbers carry no search signal (an age like "66"
#: AND-kills every query) — dropped when distilling prose into CT.gov terms.
_GENERIC_PERSON = frozenset(
    {
        "woman",
        "man",
        "female",
        "male",
        "patient",
        "patients",
        "person",
        "people",
        "adult",
        "adults",
        "child",
        "children",
        "elderly",
    }
)


def _distill(description: str, limit: int = 8) -> list[str]:
    """Prose -> short distinctive CT.gov terms (CT.gov rejects raw prose)."""
    seen, out = set(), []
    for t in _tokens(description or ""):
        if t in _GENERIC_PERSON or t.isdigit() or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


#: Canonical forms for clinical synonyms/subtypes (TrialGPT's E2 error
#: class: missing that "mutant" is "mutation"). Applied at token level so
#: search terms, overlap, and scoring share one vocabulary. Deliberately
#: small and auditable — not a terminology server.
_CANON = {
    "mutant": "mutation",
    "mutated": "mutation",
    "mutations": "mutation",
    "progressed": "progression",
    "progressive": "progression",
    "refractory": "resistant",
    "chemo": "chemotherapy",
    "metastases": "metastasis",
    "metastatic": "metastasis",
    "tumors": "tumor",
    "tumour": "tumor",
    "tumours": "tumor",
    "evaluable": "measurable",
    "previously": "prior",
    "previous": "prior",
    "sufficient": "adequate",
}

#: Criteria that can be *not applicable* (TrialGPT's fourth label) under a
#: narrow, auditable rule: pregnancy/lactation/contraception clauses when
#: the description identifies the patient as male.
_NA_PATTERNS = re.compile(r"pregnan|lactat|breastfe|nursing mother|contracept")
_MALE_PATTERN = re.compile(r"\bman\b|\bmale\b|\bmen\b")


def _is_not_applicable(bullet: str, description: str) -> bool:
    low_desc = (description or "").lower()
    if "woman" in low_desc or "female" in low_desc:
        return False
    return bool(_NA_PATTERNS.search(bullet.lower())) and bool(
        _MALE_PATTERN.search(low_desc)
    )


def _tokens(text: str) -> list[str]:
    raw = [
        w for w in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if w not in _STOP
    ]
    return [_CANON.get(w, w) for w in raw]


def _tf(tokens: list[str]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    n = len(tokens) or 1
    return {t: c / n for t, c in counts.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _read_cache() -> dict[str, Any]:
    try:
        if REALWORLD_CACHE.exists():
            data = json.loads(REALWORLD_CACHE.read_text())
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def _write_cache(cache: dict[str, Any]) -> None:
    try:
        keys = list(cache)[-REALWORLD_CACHE_MAX_ENTRIES:]
        REALWORLD_CACHE.write_text(json.dumps({k: cache[k] for k in keys}))
    except OSError:
        pass


def _default_http(params: dict[str, Any], timeout: float) -> dict[str, Any]:
    import httpx  # core dep, imported lazily

    r = httpx.get(CTGV_STUDIES, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else {}


def search_ctgov(
    query: str,
    location: str = "",
    condition: str = "",
    page_size: int = 15,
    timeout: float = 12.0,
    http_get: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Recruiting CT.gov studies for distilled terms; cached, offline fallback.

    Tries specific-to-broad rungs (terms shrink, then location drops) and
    stops at the first rung with hits, so a detailed description backs off
    to a searchable query instead of returning nothing.
    """
    loc = location.strip()[:120]
    key = (
        f"{CACHE_PREFIX}{query.lower().strip()}|{loc.lower()}|"
        f"{condition.lower().strip()}"
    )
    cache = _read_cache()
    if key in cache and isinstance(cache[key], dict):
        return {**cache[key], "source": "cache"}
    blank = {
        "studies": [],
        "total": 0,
        "source": "offline-fallback",
        "widened": False,
        "searched_terms": "",
    }
    terms = _distill(query)
    if not terms:
        return blank
    rungs: list[tuple[list[str], str]] = [(terms, loc)]
    if len(terms) > 5:
        rungs.append((terms[:5], loc))
    if len(terms) > 3:
        rungs.append((terms[:3], loc))
    if loc:
        rungs.append((terms[:3] if len(terms) > 3 else terms, ""))
    try:
        for i, (rung_terms, rung_loc) in enumerate(rungs):
            params: dict[str, Any] = {
                "query.term": " ".join(rung_terms),
                "filter.overallStatus": "RECRUITING",
                "pageSize": max(1, min(page_size, 25)),
                "countTotal": "true",
                "fields": CTGV_FIELDS,
            }
            if condition.strip():
                params["query.cond"] = condition.strip()[:200]
            if rung_loc:
                params["query.locn"] = rung_loc
            data = (http_get or _default_http)(params, timeout)
            studies = data.get("studies", []) or []
            total = int(data.get("totalCount", len(studies)))
            last = i == len(rungs) - 1
            if total > 0 or last:
                result = {
                    "studies": studies,
                    "total": total,
                    "widened": (rung_loc == "" and loc != ""),
                    "searched_terms": " ".join(rung_terms),
                }
                cache[key] = result
                _write_cache(cache)
                return {**result, "source": "live"}
        return blank
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return blank


def parse_study(raw: dict[str, Any]) -> dict[str, Any]:
    """Slim CT.gov record down to what matching and display need."""
    proto = raw.get("protocolSection", {}) or {}
    ident = proto.get("identificationModule", {}) or {}
    status = proto.get("statusModule", {}) or {}
    cond = proto.get("conditionsModule", {}) or {}
    design = proto.get("designModule", {}) or {}
    desc = proto.get("descriptionModule", {}) or {}
    elig = proto.get("eligibilityModule", {}) or {}
    locs = (proto.get("contactsLocationsModule", {}) or {}).get("locations", []) or []
    cities = []
    for loc in locs[:6]:
        if not isinstance(loc, dict):
            continue
        city = str(loc.get("city", "") or "")
        state = str(loc.get("state", "") or "")
        country = str(loc.get("country", "") or "")
        label = ", ".join(p for p in (city, state, country) if p)
        if label and label not in cities:
            cities.append(label)
    phases = design.get("phases", []) or []
    return {
        "nct_id": str(ident.get("nctId", "") or ""),
        "title": str(ident.get("briefTitle", "") or ""),
        "status": str(status.get("overallStatus", "") or ""),
        "conditions": [str(c) for c in (cond.get("conditions", []) or [])],
        "phase": ", ".join(str(p) for p in phases),
        "summary": str(desc.get("briefSummary", "") or ""),
        "eligibility": str(elig.get("eligibilityCriteria", "") or ""),
        "sex": str(elig.get("sex", "") or ""),
        "min_age": str(elig.get("minimumAge", "") or ""),
        "max_age": str(elig.get("maximumAge", "") or ""),
        "locations": cities,
        "url": (
            f"https://clinicaltrials.gov/study/{ident.get('nctId', '')}"
            if ident.get("nctId")
            else ""
        ),
    }


def _bullets(text: str) -> list[str]:
    lines = []
    for ln in text.splitlines():
        # Strip bullets and enumerators ("-", "3.", "b)") but never a bare
        # leading number ("18 years or older" must keep its 18).
        ln = re.sub(r"^(\s*[*•\-–—]\s*|\s*\d+[.)\]]\s*)+", "", ln).strip()
        low = ln.lower()
        if low.startswith(("inclusion criteria", "exclusion criteria")):
            continue
        if len(ln) > 12 and not ln.endswith(":"):
            lines.append(ln[:400])
    seen, out = set(), []
    for ln in lines:
        key = ln.lower()[:60]
        if key not in seen:
            seen.add(key)
            out.append(ln)
    return out


def split_eligibility(criteria: str) -> dict[str, list[str]]:
    """Split criteria text into inclusion / exclusion bullet lists."""
    if not criteria.strip():
        return {"inclusion": [], "exclusion": []}
    low = criteria.lower()
    cut = len(criteria)
    for marker in ("exclusion criteria", "exclusion:"):
        i = low.find(marker)
        if 0 <= i < cut:
            cut = i
    return {
        "inclusion": _bullets(criteria[:cut]),
        "exclusion": _bullets(criteria[cut:]),
    }


def _content_terms(bullet: str) -> set[str]:
    return set(_tokens(bullet))


def _template_na_note(bullet: str) -> tuple[str, str]:
    return (
        "not applicable",
        f"This requirement ('{_short(bullet)}') does not apply to the "
        "described patient, so it is set aside from the match math.",
    )


def _template_note(
    bullet: str, overlap: set[str], has_number: bool, exclusion: bool
) -> tuple[str, str]:
    """Deterministic verdict + note. Templates decide; models only rephrase."""
    if exclusion and overlap:
        return (
            "possible conflict",
            "This trial rules out people with "
            f"'{_short(bullet)}' — and your description mentions "
            f"{_join_quoted(sorted(overlap)[:3])}. Ask the study team whether "
            "this exclusion applies to you.",
        )
    if overlap and not exclusion:
        return (
            "likely met",
            f"Your description mentions {_join_quoted(sorted(overlap)[:3])}, "
            f"which lines up with this requirement: '{_short(bullet)}'.",
        )
    if has_number:
        return (
            "check with the team",
            f"This one has a number in it — '{_short(bullet)}'. Compare your "
            "exact value (age, lab result, weeks since treatment) with the "
            "study team.",
        )
    return (
        "check with the team",
        f"Nothing in your description confirms or rules out "
        f"'{_short(bullet)}' — bring records for this one.",
    )


def _verify_draft(
    response: Any, bullet: str, verdict: str
) -> tuple[str | None, str | None]:
    """Verify a model-drafted note. Returns (plain, warning)."""
    if not isinstance(response, dict):
        return None, "model_untrusted"
    plain = response.get("plain")
    quotes = response.get("quotes")
    if (
        not isinstance(plain, str)
        or not plain.strip()
        or len(plain.split()) > 60
        or not isinstance(quotes, list)
        or not quotes
        or not all(isinstance(q, str) and q and q in bullet for q in quotes)
        or response.get("verdict") != verdict
    ):
        if response.get("verdict") != verdict:
            return None, "model_verdict_mismatch"
        return None, "model_untrusted"
    return " ".join(plain.strip().split()), None


def explain_criterion(
    bullet: str,
    description: str,
    exclusion: bool = False,
    call_model: Callable[[str, str], dict[str, Any]] | None = None,
    budget: list[int] | None = None,
) -> dict[str, Any]:
    """One plain-English note on a single criterion vs the description.

    Verdicts: "likely met" (your words cover it), "possible conflict"
    (exclusion text overlaps your description), "check with the team"
    (numbers, thresholds, or nothing to go on), "not applicable" (narrow
    rule, e.g. pregnancy clauses for a male patient). Always quotes the
    criterion. A model may rephrase the note, but the template verdict
    stands and every draft is verified (verdict echo + verbatim quotes)
    or discarded.
    """
    if _is_not_applicable(bullet, description):
        verdict, plain = _template_na_note(bullet)
        return {
            "verdict": verdict,
            "plain": plain,
            "quote": bullet[:MAX_EXCERPT],
            "draft": False,
            "matched_terms": [],
        }
    desc_low = (description or "").lower()
    desc_terms = set(_tokens(description))
    terms = _content_terms(bullet)
    overlap = terms & desc_terms
    has_number = bool(re.search(r"\d", bullet))
    negated = bool(_NEGATIONS & desc_terms) or "no " in desc_low
    if exclusion and overlap and not negated:
        eff_overlap: set[str] = set(overlap)
        eff_exclusion = True
    elif overlap and not exclusion:
        eff_overlap, eff_exclusion = set(overlap), False
    else:
        eff_overlap, eff_exclusion = set(), exclusion
    verdict, plain = _template_note(bullet, eff_overlap, has_number, eff_exclusion)
    note: dict[str, Any] = {
        "verdict": verdict,
        "plain": plain,
        "quote": bullet[:MAX_EXCERPT],
        "matched_terms": sorted(eff_overlap)[:5],
        "draft": False,
    }
    if call_model is None or budget is None or budget[0] <= 0:
        if call_model is not None and budget is not None and budget[0] <= 0:
            note["model_warning"] = "model_skipped_budget"
        return note
    budget[0] -= 1
    prompt = (
        f"criterion: {bullet[:400]}\n"
        f"patient description: {(description or '')[:400]}\n"
        f"deterministic outcome: {verdict}\n"
        "Draft the note JSON."
    )
    try:
        response = call_model(MODEL_SYSTEM, prompt)
    except Exception:
        response = None
    drafted, warning = _verify_draft(response, bullet, verdict)
    if drafted is None:
        note["model_warning"] = warning
        return note
    note["plain"] = drafted
    note["draft"] = True
    return note


def _short(text: str, limit: int = 140) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _bare_quotes(text: str) -> str:
    for q in ("'", '"', "`", "\u2018", "\u2019", "\u201c", "\u201d"):
        text = text.replace(q, "")
    return text


def _join_quoted(words: list[str]) -> str:
    quoted = [f"'{w}'" for w in words]
    if len(quoted) > 1:
        return ", ".join(quoted[:-1]) + " and " + quoted[-1]
    return quoted[0] if quoted else "—"


def _trial_text_blob(study: dict[str, Any]) -> str:
    notes = study.get("notes", []) if isinstance(study, dict) else []
    quotes = " ".join(str(n.get("quote", "")) for n in notes if isinstance(n, dict))
    return " ".join(
        [
            str(study.get("title", "")),
            str(study.get("summary", "")),
            str(study.get("eligibility", "")),
            quotes,
        ]
    )


def rerank_trials(
    trials: list[dict[str, Any]],
    description: str,
    call_model: Callable[[str, str], dict[str, Any]] | None,
    budget: list[int] | None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Model re-order of the top candidates; verified or discarded.

    The response must be a permutation of the input NCT ids, and every
    per-trial reason must contain a 15+ character verbatim substring of that
    trial's own text. Anything else keeps the deterministic order.
    """
    if call_model is None or budget is None or budget[0] <= 0:
        return trials, None
    if len(trials) < 2:
        return trials, "model_rerank_skipped"
    budget[0] -= 1
    lines = []
    for t in trials:
        lines.append(
            f"{t['nct_id']}: {t['title'][:120]} "
            f"(deterministic score {t.get('score', 0)})"
        )
    prompt = (
        f"patient description: {(description or '')[:400]}\n"
        "candidates:\n" + "\n".join(lines) + "\n"
        "Re-order best first. Reply with the rerank JSON."
    )
    try:
        response = call_model(RERANK_SYSTEM, prompt)
    except Exception:
        return trials, "model_unavailable"
    if not isinstance(response, dict):
        return trials, "model_untrusted"
    order = response.get("order")
    reasons = response.get("reasons")
    ids = [t["nct_id"] for t in trials]
    if (
        not isinstance(order, list)
        or sorted(order) != sorted(ids)
        or not isinstance(reasons, dict)
    ):
        return trials, "model_rerank_rejected"
    by_id = {t["nct_id"]: t for t in trials}
    for nid in order:
        reason = reasons.get(nid)
        blob = _bare_quotes(_trial_text_blob(by_id[nid]))
        bare = _bare_quotes(reason) if isinstance(reason, str) else ""
        if (
            not isinstance(reason, str)
            or len(reason.split()) > 60
            or not any(
                # Full 20-char slices of the quote-stripped reason
                # (tails would match trivially): a cited trial phrase
                # always contains one sitting inside the trial's own text.
                len(s) == 20 and s in blob
                for s in (bare[i : i + 20] for i in range(len(bare)))
            )
        ):
            return trials, "model_rerank_rejected"
    ranked = []
    for nid in order:
        t = dict(by_id[nid])
        t["rerank_reason"] = " ".join(str(reasons[nid]).split())
        ranked.append(t)
    return ranked, None


def match_description(
    study: dict[str, Any],
    description: str,
    top_notes: int = 4,
    call_model: Callable[[str, str], dict[str, Any]] | None = None,
    budget: list[int] | None = None,
) -> dict[str, Any]:
    """Score one parsed study and explain its top criteria in plain English."""
    desc_tf = _tf(_tokens(description))
    body_tf = _tf(
        _tokens(
            " ".join(
                [study["title"]]
                + study["conditions"]
                + [study["summary"], study["eligibility"]]
            )
        )
    )
    relevance = round(_cosine(desc_tf, body_tf), 3)
    parts = split_eligibility(study["eligibility"])
    notes = []
    for b in parts["inclusion"][:3]:
        notes.append(
            {
                **explain_criterion(
                    b, description, call_model=call_model, budget=budget
                ),
                "kind": "inclusion",
            }
        )
    for b in parts["exclusion"][:2]:
        notes.append(
            {
                **explain_criterion(
                    b, description, exclusion=True, call_model=call_model, budget=budget
                ),
                "kind": "exclusion",
            }
        )
    # TrialGPT-style aggregation: met-inclusion rate ranks up, met-exclusion
    # rate ranks down (a met exclusion is the characteristic exclusion
    # signal), term relevance carries the rest. N/A notes sit out the math.
    judged = [n for n in notes if n["verdict"] != "not applicable"]
    incl = [n for n in judged if n.get("kind") == "inclusion"]
    excl = [n for n in judged if n.get("kind") == "exclusion"]
    conflicts = sum(1 for n in excl if n["verdict"] == "possible conflict")
    mets = sum(1 for n in incl if n["verdict"] == "likely met")
    incl_rate = mets / max(1, len(incl)) if incl else 0.5
    excl_clear = 1.0 - conflicts / max(1, len(excl)) if excl else 1.0
    score = round(100 * (0.5 * relevance + 0.3 * incl_rate + 0.2 * excl_clear), 1)
    if conflicts:
        verdict = "needs clinician review"
    elif mets:
        verdict = "worth discussing"
    else:
        verdict = "needs clinician review"
    summary = (
        f"{study['nct_id'] or 'This trial'} is recruiting for "
        f"{', '.join(study['conditions'][:2]) or 'your condition area'}"
        + (f" ({study['phase']})" if study["phase"] else "")
        + f". Of {len(judged)} applicable requirements, {mets} inclusion "
        f"line up with your description; "
        f"{conflicts} exclusion look like conflicts."
        " Only the study team can confirm eligibility — bring this list."
    )
    return {
        "score": score,
        "relevance": relevance,
        "verdict": verdict,
        "summary": summary,
        "notes": notes[:top_notes],
        "n_checked": len(judged),
        "inclusion_met_rate": round(incl_rate, 3),
        "exclusion_clear_rate": round(excl_clear, 3),
    }


def match_trials(
    description: str,
    condition: str = "",
    location: str = "",
    max_trials: int = 5,
    page_size: int = 15,
    http_get: Callable[[dict[str, Any], float], dict[str, Any]] | None = None,
    call_model: Callable[[str, str], dict[str, Any]] | None = None,
    model_budget: int = MODEL_BUDGET_DEFAULT,
    allow_rerank: bool = False,
) -> dict[str, Any]:
    """Full pipeline: search, parse, rank, explain. Never raises.

    call_model enables the optional model layer: verified note drafts first,
    then a verified re-order when allow_rerank is set. Templates always
    decide verdicts and order; the model only rephrases or re-orders with
    quoted justification, and every draft is verified or discarded.
    """
    if not description.strip():
        raise ValueError("Describe the patient's condition first.")
    query = condition.strip() or description.strip()
    found = search_ctgov(query, location, condition, page_size, http_get=http_get)
    parsed = []
    for raw in found["studies"]:
        try:
            parsed.append(parse_study(raw))
        except Exception:
            continue
    desc_tf = _tf(_tokens(description))
    scored = []
    for study in parsed:
        if not study["nct_id"]:
            continue
        body_tf = _tf(
            _tokens(
                " ".join(
                    [study["title"]]
                    + study["conditions"]
                    + [study["summary"], study["eligibility"]]
                )
            )
        )
        scored.append((_cosine(desc_tf, body_tf), study))
    scored.sort(key=lambda t: -t[0])
    budget = [max(0, int(model_budget))]
    top = []
    for _, study in scored[: max(1, min(max_trials, MAX_TRIALS))]:
        top.append(
            {
                **study,
                **match_description(
                    study, description, call_model=call_model, budget=budget
                ),
            }
        )
    warnings: list[str] = []
    for t in top:
        for n in t.get("notes", []):
            w = n.get("model_warning")
            if w and w not in warnings:
                warnings.append(str(w))
    reranked = False
    if allow_rerank and call_model is not None:
        head, rerank_warning = rerank_trials(
            top[:RERANK_TOP_N], description, call_model, budget
        )
        if rerank_warning:
            warnings.append(rerank_warning)
        else:
            top = head + top[RERANK_TOP_N:]
            reranked = True
    drafted = sum(1 for t in top for n in t.get("notes", []) if n.get("draft"))
    return {
        "query": query,
        "location": location.strip(),
        "total_recruiting": found["total"],
        "source": found["source"],
        "searched_terms": found.get("searched_terms", ""),
        "widened": found.get("widened", False),
        "explain_source": ("model-assisted" if drafted else "template"),
        "reranked": reranked,
        "model_warnings": warnings,
        "trials": top,
        "disclaimer": (
            "Matching aid only — not medical advice and not an eligibility "
            "determination. Confirm every criterion with the study team."
        ),
    }
