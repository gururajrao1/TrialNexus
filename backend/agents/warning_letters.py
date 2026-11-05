"""Warning-letter cross-check: learn from FDA enforcement, applied to trials.

Reads the user's own FDA warning letters from ``data/inbox/warning-letter-*.txt``
(there is no public bulk API for these, so the user saves them by hand) and
does two deterministic, stdlib-only things:

1. Indexes each letter: CMS number, date, recipient firm, issuing office,
   cited CFR sections, and violation *themes* (CAPA, design control, ...).
2. Cross-checks a user finding ("site closed a CAPA with no effectiveness
   check") against the indexed violations by shared themes, shared CFR
   sections, and plain term overlap — then maps the hit to the trial-world
   analogue with a suggested deviation tier (critical/major/minor, the same
   vocabulary as deviation_watch) and the panel that owns the fix.

Never raises on bad files; skips what it cannot parse.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.config import INBOX_DIR

LETTER_GLOB = "warning-letter-*.txt"
MAX_EXCERPT = 600

_MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December"
)

# theme -> keywords (matched case-insensitively), trial analogue, tier, owning panel.
THEMES: dict[str, dict[str, Any]] = {
    "capa": {
        "keywords": [
            "capa",
            "corrective and preventive",
            "effectiveness check",
            "corrective action",
        ],
        "label": "CAPA effectiveness",
        "trial_analogue": "Deviation CAPAs closed without proof the fix worked",
        "tier": "major",
        "panel": "monitoring",
    },
    "design_control": {
        "keywords": [
            "design validation",
            "design control",
            "risk management",
            "hazard",
            "820.30",
        ],
        "label": "Design control / risk management",
        "trial_analogue": "Protocol and amendment design control under a risk-based QMS",
        "tier": "major",
        "panel": "audit",
    },
    "complaint_vigilance": {
        "keywords": [
            "complaint",
            "medical device report",
            "adverse event reporting",
            "820.198",
            "vigilance",
        ],
        "label": "Complaint / vigilance handling",
        "trial_analogue": "SAE/AE reporting clock and follow-up (safety triage severity)",
        "tier": "major",
        "panel": "safety",
    },
    "process_validation": {
        "keywords": [
            "process validation",
            "820.75",
            "installation qualification",
            "operational qualification",
        ],
        "label": "Process validation",
        "trial_analogue": "Site procedures validated before first patient in (startup checklist)",
        "tier": "major",
        "panel": "startup",
    },
    "management_oversight": {
        "keywords": ["management review", "quality system", "820.20", "quality policy"],
        "label": "Management oversight / QMS",
        "trial_analogue": "QMS oversight gaps that block database lock readiness",
        "tier": "major",
        "panel": "monitoring",
    },
    "training": {
        "keywords": ["training", "personnel qualification", "820.25"],
        "label": "Training records",
        "trial_analogue": "Site staff training and delegation log currency",
        "tier": "minor",
        "panel": "startup",
    },
    "premarket_auth": {
        "keywords": [
            "510(k)",
            "pma",
            "501(f)",
            "premarket approval",
            "investigational device exemption",
            "unapproved",
        ],
        "label": "Premarket authorization",
        "trial_analogue": "Regulatory authorization gate (IND/IDE in place before enrollment)",
        "tier": "critical",
        "panel": "startup",
    },
    "promotion": {
        "keywords": [
            "misbrand",
            "misbranded",
            "promotion",
            "opdp",
            "off-label",
            "false or misleading",
        ],
        "label": "Promotion / intended use",
        "trial_analogue": "Recruitment-material claims staying inside the approved protocol",
        "tier": "major",
        "panel": "audit",
    },
    "sterile_mfg": {
        "keywords": [
            "sterile",
            "aseptic",
            "part 211",
            "part 212",
            "21 cfr 212",
            "pyrogen",
            "endotoxin",
        ],
        "label": "Sterile manufacturing",
        "trial_analogue": "IMP handling, storage, and pharmacy accountability at sites",
        "tier": "major",
        "panel": "monitoring",
    },
}

_STOP = frozenset(
    "the a an and or of to in for on with is are was were be been by as at "
    "from that this it its into over under such each per our your their his her "
    "will shall may can not no more most than then there here which who whom "
    "what when where have has had do does did s t re ll ve d m".split()
)

TIER_RANK = {"minor": 0, "major": 1, "critical": 2}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in _STOP}


def _themes_of(text: str) -> list[str]:
    low = text.lower()
    return [
        name for name, spec in THEMES.items() if any(k in low for k in spec["keywords"])
    ]


def _cfr_cites(text: str) -> list[str]:
    cites = re.findall(r"21\s*CFR\s*(\d+)\.(\d+)", text, re.I)
    out = sorted({f"21 CFR {p}.{s}" for p, s in cites})
    usc = re.findall(r"21\s*U\.?S\.?C\.?\s*§*\s*(\d+[a-z]?)", text, re.I)
    out += sorted({f"21 USC {u}" for u in usc})[:4]
    return out


def _metadata(text: str) -> dict[str, str]:
    meta = {
        "cms": "",
        "date": "",
        "recipient": "",
        "firm": "",
        "office": "",
        "product_area": "",
    }
    m = re.search(r"CMS\s*#\s*([\w-]+)", text)
    if m:
        meta["cms"] = m.group(1)
    m = re.search(rf"\b({_MONTHS})\s+\d{{1,2}},\s+\d{{4}}\b", text)
    if m:
        meta["date"] = m.group(0)
    m = re.search(r"^Dear\s+([^:\n]{1,80}):", text, re.M)
    if m:
        meta["recipient"] = m.group(1).strip()
    else:
        m = re.search(r"Recipient:\s*\n\s*([^\n]{1,80})", text)
        if m:
            meta["recipient"] = m.group(1).strip()
    firm_pat = re.compile(
        r"([A-Z][\w&'’.,\- ]{2,60}?(?:Corporation|Incorporated|Inc\.|LLC|"
        r"Ltd\.|GmbH|Company))"
    )
    m = firm_pat.search(text)
    if m:
        meta["firm"] = re.sub(
            r",?\s+(LLC|Inc|Ltd|GmbH|Co)\.?$", "", m.group(1), flags=re.I
        ).strip()
    if not meta["firm"]:
        m = re.search(r"firm located in ([A-Z][\w .'\-]+, [A-Z]{2})", text)
        if m:
            meta["firm"] = "Unnamed firm — " + m.group(1)
    m = re.search(r"Issuing Office:\s*\n\s*([^\n]{1,120})", text)
    if m:
        meta["office"] = m.group(1).strip()
    else:
        m = re.search(
            r"(Center for Drug Evaluation and Research|Center for Devices "
            r"and Radiological Health|Office of Prescription Drug Promotion"
            r"|Center for Biologics Evaluation and Research)",
            text,
        )
        if m:
            meta["office"] = m.group(1)
    low = text.lower()
    if "drug evaluation and research" in (meta["office"] or "").lower():
        meta["product_area"] = "drugs"
    elif "devices and radiological" in (meta["office"] or "").lower():
        meta["product_area"] = "devices"
    elif (
        "prescription drug promotion" in (meta["office"] or "").lower() or "opdp" in low
    ):
        meta["product_area"] = "promotion"
    elif re.search(
        r"21\s*CFR\s*820|quality system regulation|medical device", text, re.I
    ):
        meta["product_area"] = "devices"
    elif re.search(r"21\s*CFR\s*21[12]|compounding|pet drug", text, re.I):
        meta["product_area"] = "drugs"
    else:
        meta["product_area"] = "general"
    return meta


def _violation_paragraphs(text: str) -> list[dict[str, Any]]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out = []
    for p in paras:
        cites = _cfr_cites(p)
        themes = _themes_of(p)
        hot = bool(cites) or "failure to" in p.lower() or "violation" in p.lower()
        if hot and len(p) > 120:
            out.append({"excerpt": p[:MAX_EXCERPT], "cfr": cites, "themes": themes})
    return out


def parse_letter(text: str, source: str) -> dict[str, Any]:
    """Parse one letter file into metadata + violation paragraphs."""
    meta = _metadata(text)
    paras = _violation_paragraphs(text)
    # Theme support is counted over the whole letter (section headers like
    # "Design Control Violations" carry signal) with a 3+ hit gate, so lone
    # boilerplate mentions cannot tag the whole letter.
    low = text.lower()
    counts = {
        t: sum(low.count(k) for k in spec["keywords"]) for t, spec in THEMES.items()
    }
    themes = sorted([t for t, c in counts.items() if c >= 3])
    if not themes:
        themes = sorted({t for p in paras for t in p["themes"]})
    return {
        "id": source,
        "firm": meta["firm"] or meta["recipient"] or source,
        "cms": meta["cms"],
        "date": meta["date"],
        "recipient": meta["recipient"],
        "office": meta["office"],
        "product_area": meta["product_area"],
        "themes": themes,
        "n_violations": len(paras),
        "violations": paras,
    }


def check_promo_draft(draft: str, indication: str = "") -> dict[str, Any]:
    """Screen recruitment/promotion copy against the approved indication.

    Flags condition terms in the draft that do not appear in the indication
    (possible off-label promotion) plus any promotion-theme language the
    FDA has cited (superiority claims, misleading efficacy). Lexical only —
    a flag is a prompt to check, never a violation finding.
    """
    draft_low = (draft or "").lower()
    ind_terms = set(_tokens(indication or ""))
    draft_terms = set(_tokens(draft or ""))
    generic = {
        "drug",
        "treatment",
        "treat",
        "patients",
        "patient",
        "trial",
        "study",
        "clinical",
        "new",
        "now",
        "ask",
        "doctor",
        "today",
    }
    off_label = sorted(draft_terms - ind_terms - generic)
    promo_hits = sorted({k for k in THEMES["promotion"]["keywords"] if k in draft_low})
    flags = []
    for t in off_label[:8]:
        flags.append(
            {
                "kind": "off-indication term",
                "text": t,
                "note": f"'{t}' appears in the draft but not in the "
                "approved indication — verify before use.",
            }
        )
    for k in promo_hits:
        flags.append(
            {
                "kind": "promotion language",
                "text": k,
                "note": "FDA has cited this language class in promotion "
                "warning letters — verify the claim is fair-balance.",
            }
        )
    verdict = "needs review" if flags else "no lexical flags"
    return {
        "verdict": verdict,
        "flags": flags,
        "basis": (
            "Token overlap vs the indication plus the promotion-theme "
            "keyword set behind tab 13. Human review decides."
        ),
    }


def load_letters(inbox_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load and parse every warning-letter-*.txt in the inbox."""
    root = inbox_dir or INBOX_DIR
    letters = []
    if not root.exists():
        return letters
    for path in sorted(root.glob(LETTER_GLOB)):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if not text.strip():
            continue
        try:
            letters.append(parse_letter(text, path.name))
        except Exception:
            continue
    return letters


def _score_finding(
    finding_tokens: set[str], letter: dict[str, Any], finding_themes: list[str]
) -> tuple[float, dict[str, Any]]:
    shared_themes = [t for t in finding_themes if t in letter["themes"]]
    best: dict[str, Any] | None = None
    best_score = 0.0
    for v in letter["violations"]:
        v_themes = [t for t in finding_themes if t in v["themes"]]
        jt = _tokens(v["excerpt"])
        overlap = len(finding_tokens & jt)
        union = len(finding_tokens | jt) or 1
        score = 3.0 * len(v_themes) + overlap / union
        shared_cfr = [
            c for c in v["cfr"] if any(c.lower() in t for t in finding_tokens)
        ]
        score += 5.0 * len(shared_cfr)
        if score > best_score:
            best_score = score
            best = {
                "excerpt": v["excerpt"],
                "cfr": v["cfr"],
                "themes": v_themes or v["themes"][:2],
                "shared_cfr": shared_cfr,
            }
    theme_bonus = 1.5 * len(shared_themes)
    return best_score + theme_bonus, best or {}


def cross_check(
    text: str, letters: list[dict[str, Any]], top_n: int = 3
) -> list[dict[str, Any]]:
    """Rank letters against a free-text finding; deterministic."""
    finding_tokens = _tokens(text)
    finding_themes = _themes_of(text)
    ranked = []
    for letter in letters:
        score, best = _score_finding(finding_tokens, letter, finding_themes)
        matched = sorted(
            set(best.get("themes", [])) | (set(finding_themes) & set(letter["themes"]))
        )
        tiers = [THEMES[t]["tier"] for t in matched if t in THEMES]
        tier = max(tiers, key=lambda t: TIER_RANK[t]) if tiers else "minor"
        actions = sorted({THEMES[t]["trial_analogue"] for t in matched if t in THEMES})
        panels = sorted({THEMES[t]["panel"] for t in matched if t in THEMES})
        ranked.append(
            {
                "id": letter["id"],
                "firm": letter["firm"],
                "cms": letter["cms"],
                "date": letter["date"],
                "score": round(score, 3),
                "matched_themes": [
                    {"theme": t, "label": THEMES[t]["label"]}
                    for t in matched
                    if t in THEMES
                ],
                "excerpt": best.get("excerpt", ""),
                "cfr": best.get("cfr", []),
                "suggested_tier": tier,
                "trial_actions": actions,
                "panels": panels,
            }
        )
    ranked.sort(key=lambda r: -r["score"])
    return [r for r in ranked[:top_n] if r["score"] > 0]
