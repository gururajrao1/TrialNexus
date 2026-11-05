"""Real-world clinical data lookups: ClinVar variants + OpenFDA FAERS.

Cookbook integration: variant pathogenicity for biomarker criteria and
regulatory adverse-event counts for safety signals. Disk-cached with
offline fallback, mirroring PubMed/CT.gov. No API key; OpenFDA allows
240 requests/minute without one, NCBI 3/second. Never raises.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any

from backend.config import (
    CLINVAR_CACHE,
    CLINVAR_CACHE_MAX_ENTRIES,
    OPENFDA_CACHE,
    OPENFDA_CACHE_MAX_ENTRIES,
    REALWORLD_CACHE,
    REALWORLD_CACHE_MAX_ENTRIES,
)

CLINVAR_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
CLINVAR_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
OPENFDA_EVENT = "https://api.fda.gov/drug/event.json"
RXNORM_RXCUI = "https://rxnav.nlm.nih.gov/REST/rxcui.json"
DAILYMED_SPLS = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
NPI_REGISTRY = "https://npiregistry.cms.hhs.gov/api/"
TOOL = "TrialNexusOS"

#: Biomarker genes worth a ClinVar lookup when named in criteria text.
ONCO_GENES = frozenset(
    {
        "EGFR",
        "BRCA1",
        "BRCA2",
        "HER2",
        "ERBB2",
        "KRAS",
        "ALK",
        "ROS1",
        "BRAF",
        "MET",
        "RET",
        "NTRK1",
        "NTRK2",
        "NTRK3",
        "PIK3CA",
        "TP53",
        "CD274",
        "MSI",
        "KRAS",
        "NRAS",
        "KIT",
        "PDGFRA",
        "FGFR2",
        "IDH1",
    }
)


def genes_in_text(text: str) -> list[str]:
    """Known biomarker genes named in free text, longest-first dedup."""
    found = set()
    for gene in ONCO_GENES:
        if re.search(r"\b" + re.escape(gene) + r"\b", text or "", re.IGNORECASE):
            found.add("ERBB2" if gene == "HER2" else gene)
    found.discard("HER2")
    return sorted(found)


def _read_cache(path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text())
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def _write_cache(path, cache: dict[str, Any], cap: int) -> None:
    while len(cache) > cap:
        cache.pop(next(iter(cache)))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache))
    except OSError:
        pass


def parse_clinvar_esummary(payload: str) -> list[dict[str, str]]:
    """Variant cards from a ClinVar esummary response. Pure, offline.

    Parses DocSum items generically so ClinVar schema drift degrades to
    empty strings instead of crashes.
    """
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    out = []
    for doc in root.findall("DocSum"):
        items = {
            (el.get("Name") or ""): (el.text or "").strip()
            for el in doc.findall("Item")
        }

        def first(*names: str) -> str:
            for n in names:
                if items.get(n):
                    return items[n]
            return ""

        vid = (doc.findtext("Id") or "").strip()
        if vid:
            out.append(
                {
                    "id": vid,
                    "variation": first(
                        "VariationName", "variation_name", "Title", "accession"
                    ),
                    "condition": first("Condition", "condition", "Trait", "phenotype"),
                    "significance": first(
                        "ClinicalSignificance",
                        "clinical_significance",
                        "GermlineClassification",
                        "Classification",
                    ),
                }
            )
    return out


def fetch_clinvar(gene: str, retmax: int = 3, timeout: float = 10.0) -> dict[str, Any]:
    """ClinVar variants for one gene; cached, with offline fallback."""
    key = f"{gene.upper()}|{max(1, min(retmax, 10))}"
    cache = _read_cache(CLINVAR_CACHE)
    if key in cache and isinstance(cache[key], dict):
        return {**cache[key], "source": "cache"}
    blank: dict[str, Any] = {"gene": gene.upper(), "count": 0, "variants": []}
    try:
        import httpx  # core dep, imported lazily

        search = httpx.get(
            CLINVAR_ESEARCH,
            params={
                "db": "clinvar",
                "term": f"{gene}[gene]",
                "retmax": max(1, min(retmax, 10)),
                "retmode": "xml",
                "tool": TOOL,
            },
            timeout=timeout,
        )
        search.raise_for_status()
        root = ET.fromstring(search.text)
        count_el = root.find("Count")
        count = (
            int(count_el.text.strip())
            if count_el is not None and (count_el.text or "").strip().isdigit()
            else 0
        )
        pmids = [
            (e.text or "").strip()
            for e in root.findall("./IdList/Id")
            if (e.text or "").strip()
        ]
        variants: list[dict[str, str]] = []
        if pmids:
            summary = httpx.get(
                CLINVAR_ESUMMARY,
                params={
                    "db": "clinvar",
                    "id": ",".join(pmids),
                    "retmode": "xml",
                    "tool": TOOL,
                },
                timeout=timeout,
            )
            summary.raise_for_status()
            variants = parse_clinvar_esummary(summary.text)
        result = {"gene": gene.upper(), "count": count, "variants": variants}
        cache[key] = result
        _write_cache(CLINVAR_CACHE, cache, CLINVAR_CACHE_MAX_ENTRIES)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


def parse_faers_total(payload: str) -> int:
    """Total matching FAERS reports from an OpenFDA response. Pure."""
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return 0
    try:
        return int(((data.get("meta") or {}).get("results") or {}).get("total", 0))
    except (ValueError, TypeError):
        return 0


def fetch_faers(drug: str, event: str = "", timeout: float = 10.0) -> dict[str, Any]:
    """FAERS report counts for a drug (optionally + event). Cached."""
    key = f"{drug.lower()}|{event.lower()}"
    cache = _read_cache(OPENFDA_CACHE)
    if key in cache and isinstance(cache[key], dict):
        return {**cache[key], "source": "cache"}
    blank: dict[str, Any] = {"drug": drug, "event": event, "reports": 0}
    try:
        import httpx  # core dep, imported lazily

        term = f'patient.drug.medicinalproduct:"{drug}"'
        if event.strip():
            term += f'+AND+patient.reaction.reactionmeddrapt:"{event.strip()}"'
        r = httpx.get(
            OPENFDA_EVENT, params={"search": term, "limit": "1"}, timeout=timeout
        )
        r.raise_for_status()
        result = {"drug": drug, "event": event, "reports": parse_faers_total(r.text)}
        cache[key] = result
        _write_cache(OPENFDA_CACHE, cache, OPENFDA_CACHE_MAX_ENTRIES)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


MYGENE_QUERY = "https://mygene.info/v3/query"
MYVARIANT_QUERY = "https://myvariant.info/v1/query"
CIVIC_GRAPHQL = "https://civicdb.org/api/graphql"
OPENFDA_LABEL = "https://api.fda.gov/drug/label.json"
OPENFDA_ENFORCE = "https://api.fda.gov/drug/enforcement.json"
CTGV_STUDIES = "https://clinicaltrials.gov/api/v2/studies"


def _rw_cached(key: str):
    cache = _read_cache(REALWORLD_CACHE)
    hit = cache.get(key)
    return (cache, hit if isinstance(hit, dict) else None)


def _rw_store(key: str, cache: dict[str, Any], result: dict[str, Any]) -> None:
    cache[key] = result
    _write_cache(REALWORLD_CACHE, cache, REALWORLD_CACHE_MAX_ENTRIES)


def parse_mygene_hit(payload: dict[str, Any]) -> dict[str, str]:
    """Gene name + function summary from a MyGene.info hit. Pure."""
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    top = hits[0] if hits else {}
    return {
        "symbol": str(top.get("symbol", "")),
        "name": str(top.get("name", "")),
        "summary": str(top.get("summary", "") or ""),
    }


def parse_civic_gene(payload: dict[str, Any]) -> dict[str, str]:
    """Curated gene description from a CIViC gene query. Pure."""
    gene = (
        ((payload.get("data") or {}).get("gene") or {})
        if isinstance(payload, dict)
        else {}
    )
    return {
        "name": str(gene.get("name", "")),
        "description": str(gene.get("description", "") or ""),
    }


def parse_myvariant_hits(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Top variant annotations from a MyVariant.info gene query. Pure."""
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    out = []
    for h in hits[:5]:
        clin = h.get("clinvar", {}) if isinstance(h.get("clinvar"), dict) else {}
        out.append(
            {
                "id": str(h.get("_id", "?")),
                "significance": str(
                    clin.get("clinical_significance", "") or "unclassified"
                ),
                "condition": str(
                    clin.get("trait", "") or clin.get("condition", "") or ""
                ),
            }
        )
    return out


def fetch_gene_card(gene: str, timeout: float = 10.0) -> dict[str, Any]:
    """MyGene summary + CIViC curation + ClinVar variants for one gene."""
    key = f"gene|{gene.upper()}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    try:
        import httpx  # core dep, imported lazily

        mg = httpx.get(
            MYGENE_QUERY,
            params={
                "q": f"symbol:{gene}",
                "species": "human",
                "size": 1,
                "fields": "symbol,name,summary,entrezgene",
            },
            timeout=timeout,
        )
        mg.raise_for_status()
        parsed = parse_mygene_hit(mg.json())
        mg_src = "live"
    except Exception:
        parsed = {"symbol": "", "name": "", "summary": ""}
        mg_src = "offline-fallback"
    try:
        import httpx  # core dep, imported lazily

        cv = httpx.post(
            CIVIC_GRAPHQL,
            json={
                "query": f'{{ gene(entrezSymbol: "{gene}") {{ name description }} }}'
            },
            timeout=timeout,
        )
        cv.raise_for_status()
        civic = parse_civic_gene(cv.json())
        cv_src = "live" if civic["description"] else "offline-fallback"
    except Exception:
        civic = {"name": "", "description": ""}
        cv_src = "offline-fallback"
    try:
        clinvar = fetch_clinvar(gene, 3)
        cl_src = clinvar.get("source", "offline-fallback")
        clinvar = {
            "count": clinvar.get("count", 0),
            "variants": clinvar.get("variants", []),
        }
    except Exception:
        clinvar = {"count": 0, "variants": []}
        cl_src = "offline-fallback"
    result = {
        "gene": gene.upper(),
        "name": parsed["name"],
        "gene_summary": parsed["summary"],
        "civic_description": civic["description"],
        "clinvar": clinvar,
        "sources": {"mygene": mg_src, "civic": cv_src, "clinvar": cl_src},
    }
    _rw_store(key, cache, result)
    return {**result, "source": "live"}


def fetch_variant_highlights(gene: str, timeout: float = 10.0) -> dict[str, Any]:
    """Top annotated variants in a gene from MyVariant.info. Cached."""
    key = f"variants|{gene.upper()}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    blank: dict[str, Any] = {"gene": gene.upper(), "variants": []}
    try:
        import httpx  # core dep, imported lazily

        r = httpx.get(
            MYVARIANT_QUERY,
            params={"q": gene, "size": 5, "fields": "_id,clinvar"},
            timeout=timeout,
        )
        r.raise_for_status()
        result = {"gene": gene.upper(), "variants": parse_myvariant_hits(r.json())}
        _rw_store(key, cache, result)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


def parse_label_doc(payload: dict[str, Any]) -> dict[str, Any]:
    """Boxed warning + brand from an OpenFDA label doc. Pure."""
    results = payload.get("results", []) if isinstance(payload, dict) else []
    doc = results[0] if results else {}
    openfda = doc.get("openfda", {}) if isinstance(doc, dict) else {}
    boxed = doc.get("boxed_warning", [""])[0] if isinstance(doc, dict) else ""
    brand = openfda.get("brand_name", [""])[0]
    return {
        "brand": str(brand),
        "has_boxed": bool(str(boxed).strip()),
        "boxed_warning": str(boxed)[:600],
        "has_warnings": bool(doc.get("warnings")) if isinstance(doc, dict) else False,
    }


def fetch_drug_label(drug: str, timeout: float = 10.0) -> dict[str, Any]:
    """FDA label card for a drug: brand, boxed warning. Cached."""
    key = f"label|{drug.lower()}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    blank: dict[str, Any] = {
        "drug": drug,
        "brand": "",
        "has_boxed": False,
        "boxed_warning": "",
        "has_warnings": False,
    }
    try:
        import httpx  # core dep, imported lazily

        result = dict(blank)
        for field in ("openfda.generic_name", "openfda.brand_name"):
            r = httpx.get(
                OPENFDA_LABEL,
                params={"search": f'{field}:"{drug.upper()}"', "limit": "1"},
                timeout=timeout,
            )
            if r.status_code == 404:
                continue
            r.raise_for_status()
            parsed = parse_label_doc(r.json())
            if parsed["brand"] or parsed["has_boxed"] or parsed["has_warnings"]:
                result = {"drug": drug, **parsed}
                break
        else:
            return {**blank, "source": "offline-fallback"}
        _rw_store(key, cache, result)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


def _section_text(items: Any) -> str:
    xs = items if isinstance(items, list) else [items]
    return " ".join(str(x) for x in xs if str(x).strip())[:4000]


def _doc_names(doc: dict[str, Any]) -> str:
    if not isinstance(doc, dict):
        return ""
    names: list[str] = []
    openfda = doc.get("openfda", {})
    if isinstance(openfda, dict):
        for key in (
            "brand_name",
            "generic_name",
            "manufacturer_name",
            "substance_name",
        ):
            val = openfda.get(key, []) or []
            names.extend(str(x) for x in (val if isinstance(val, list) else [val]))
    spl = doc.get("spl_product_data_elements", []) or []
    names.extend(str(x) for x in (spl if isinstance(spl, list) else [spl]))
    return " ".join(names).lower()


def _is_own_label(doc: Any, drug: str) -> bool:
    """True when a label doc is the drug's own label, not a passing mention.

    Combination-product labels mention other drugs in their text; the
    product-data elements (or openfda names) are the identity anchor.
    """
    return isinstance(doc, dict) and drug.lower() in _doc_names(doc)


def parse_label_sections(payload: dict[str, Any]) -> dict[str, str]:
    """Warning sections from OpenFDA label docs. Pure.

    Scans every returned doc and keeps the first one that actually carries
    section text — the top hit is often a repackager label without any.
    Callers pre-filter free-text results to the drug's own labels (see
    ``fetch_label_sections``); unfiltered payloads may attribute a
    combination product's mention instead.
    """
    results = payload.get("results", []) if isinstance(payload, dict) else []
    for doc in results:
        if not isinstance(doc, dict):
            continue
        warnings = _section_text(doc.get("warnings", []) or [])
        inter = _section_text(doc.get("drug_interactions", []) or [])
        boxed = _section_text(doc.get("boxed_warning", []) or [])[:600]
        if warnings or inter or boxed:
            return {
                "warnings": warnings,
                "drug_interactions": inter,
                "boxed_warning": boxed,
            }
    return {"warnings": "", "drug_interactions": "", "boxed_warning": ""}


def fetch_label_sections(drug: str, timeout: float = 10.0) -> dict[str, Any]:
    """Warnings + interactions section text for a drug. Cached. Separate from
    the label card so the card contract stays frozen."""
    key = f"label-sections|{drug.lower()}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    blank: dict[str, Any] = {
        "drug": drug,
        "warnings": "",
        "drug_interactions": "",
        "boxed_warning": "",
    }
    try:
        import httpx  # core dep, imported lazily

        def located(payload: dict[str, Any], own_only: bool) -> dict[str, str]:
            results = payload.get("results", []) if isinstance(payload, dict) else []
            if own_only:
                results = [d for d in results if _is_own_label(d, drug)]
            return parse_label_sections({"results": results})

        result = dict(blank)
        queries = [
            (f'openfda.generic_name:"{drug.upper()}"', False),
            (f'openfda.brand_name:"{drug.upper()}"', False),
            # Salt forms and unindexed spellings miss the exact ladder;
            # free-text filtered to the drug's own labels catches them.
            (drug.upper(), True),
        ]
        for search, own_only in queries:
            r = httpx.get(
                OPENFDA_LABEL,
                params={"search": search, "limit": "10"},
                timeout=timeout,
            )
            if r.status_code == 404:
                continue
            r.raise_for_status()
            parsed = located(r.json(), own_only)
            if parsed["warnings"] or parsed["drug_interactions"]:
                result = {"drug": drug, **parsed}
                break
        else:
            return {**blank, "source": "offline-fallback"}
        _rw_store(key, cache, result)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


def parse_enforcement(payload: dict[str, Any]) -> dict[str, Any]:
    """Recall count + latest recall from an enforcement query. Pure."""
    total = 0
    try:
        total = int(((payload.get("meta") or {}).get("results") or {}).get("total", 0))
    except (ValueError, TypeError):
        total = 0
    results = payload.get("results", []) if isinstance(payload, dict) else []
    latest = {}
    if results:
        d = results[0]
        latest = {
            "recall_number": str(d.get("recall_number", "")),
            "reason": str(d.get("reason_for_recall", ""))[:300],
            "classification": str(d.get("classification", "")),
            "status": str(d.get("status", "")),
            "recalling_firm": str(d.get("recalling_firm", "")),
        }
    return {"count": total, "latest": latest}


def fetch_recalls(drug: str, timeout: float = 10.0) -> dict[str, Any]:
    """FDA enforcement/recalls for a drug. Cached."""
    key = f"recalls|{drug.lower()}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    blank: dict[str, Any] = {"drug": drug, "count": 0, "latest": {}}
    try:
        import httpx  # core dep, imported lazily

        r = httpx.get(
            OPENFDA_ENFORCE,
            params={"search": f'product_description:"{drug}"', "limit": "1"},
            timeout=timeout,
        )
        if r.status_code == 404:
            return {**blank, "source": "offline-fallback"}
        r.raise_for_status()
        parsed = parse_enforcement(r.json())
        result = {"drug": drug, **parsed}
        _rw_store(key, cache, result)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


def parse_live_studies(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Recruiting studies with locations from a CT.gov v2 response. Pure."""
    out = []
    studies = payload.get("studies", []) if isinstance(payload, dict) else []
    for s in studies:
        proto = s.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        locs = proto.get("contactsLocationsModule", {}).get("locations", []) or []
        first = locs[0] if locs else {}
        out.append(
            {
                "nct": str(ident.get("nctId", "")),
                "title": str(ident.get("briefTitle", "")),
                "status": str(proto.get("statusModule", {}).get("overallStatus", "")),
                "city": str(first.get("city", "")),
                "country": str(first.get("country", "")),
                "n_locations": len(locs),
            }
        )
    return out


def fetch_live_studies(
    condition: str, phase: str = "", timeout: float = 15.0
) -> dict[str, Any]:
    """Recruiting CT.gov studies for a condition, with locations. Cached."""
    key = f"studies|{condition.lower()}|{phase.lower()}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    blank: dict[str, Any] = {"condition": condition, "phase": phase, "studies": []}
    try:
        import httpx  # core dep, imported lazily

        params = {
            "query.cond": condition,
            "filter.overallStatus": "RECRUITING",
            "pageSize": "5",
            "fields": "NCTId,BriefTitle,OverallStatus,LocationCity,LocationCountry",
        }
        if phase.strip():
            params["filter.phase"] = phase.strip().upper()
        r = httpx.get(CTGV_STUDIES, params=params, timeout=timeout)
        r.raise_for_status()
        result = {
            "condition": condition,
            "phase": phase,
            "studies": parse_live_studies(r.json()),
        }
        _rw_store(key, cache, result)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


def parse_rxnorm(payload: Any) -> str:
    """RxCUI for a drug name from an RxNorm rxcui.json payload. Pure."""
    try:
        ids = payload["idGroup"]["rxnormId"]
        first = ids[0] if ids else ""
        return str(first or "")
    except (KeyError, TypeError, IndexError, AttributeError):
        return ""


def fetch_rxnorm_id(name: str, timeout: float = 10.0) -> dict[str, Any]:
    """RxNorm concept ID for a drug spelling. Cached, never raises."""
    key = f"rxnorm|{name.lower()}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    blank: dict[str, Any] = {"name": name, "rxcui": ""}
    try:
        import httpx  # core dep, imported lazily

        r = httpx.get(RXNORM_RXCUI, params={"name": name}, timeout=timeout)
        r.raise_for_status()
        result = {"name": name, "rxcui": parse_rxnorm(r.json())}
        _rw_store(key, cache, result)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


def parse_dailymed(payload: Any) -> list[dict[str, str]]:
    """SPL setids + titles + published dates from a DailyMed spls payload."""
    try:
        data = payload.get("data", [])
    except AttributeError:
        return []
    out = []
    if isinstance(data, list):
        for d in data:
            if not isinstance(d, dict):
                continue
            setid = str(d.get("setid", "") or "")
            title = str(d.get("title", "") or "")
            if setid and title:
                out.append(
                    {
                        "setid": setid,
                        "title": title,
                        "published": str(d.get("published_date", "") or ""),
                    }
                )
    return out


def fetch_dailymed_label(drug: str, timeout: float = 10.0) -> dict[str, Any]:
    """NLM DailyMed SPL listings for a drug name. Cached, never raises."""
    key = f"dailymed|{drug.lower()}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    blank: dict[str, Any] = {"drug": drug, "spls": []}
    try:
        import httpx  # core dep, imported lazily

        r = httpx.get(DAILYMED_SPLS, params={"drug_name": drug}, timeout=timeout)
        r.raise_for_status()
        result = {"drug": drug, "spls": parse_dailymed(r.json())}
        _rw_store(key, cache, result)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}


def attach_rxnorm(triaged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill rxcui per distinct suspect_drug via cached RxNorm. Never raises.

    Route-layer helper: keeps the pure triage/signal agents offline while
    letting screens group spelling variants as one drug. Skips blanks and
    the unknown placeholder.
    """
    ids: dict[str, str] = {}
    for t in triaged:
        name = str(t.get("suspect_drug", "") or "").strip()
        key = name.lower()
        if name and key != "unknown" and key not in ids:
            try:
                ids[key] = fetch_rxnorm_id(name).get("rxcui", "") or ""
            except Exception:
                ids[key] = ""
    for t in triaged:
        key = str(t.get("suspect_drug", "") or "").strip().lower()
        t["rxcui"] = ids.get(key, "")
    return triaged


def parse_npi_results(payload: Any) -> list[dict[str, str]]:
    """Provider cards from an NPPES NPI registry payload. Pure."""
    try:
        results = payload.get("results", [])
    except AttributeError:
        return []
    out = []
    if not isinstance(results, list):
        return []
    for r in results:
        if not isinstance(r, dict):
            continue
        basic = r.get("basic", {}) if isinstance(r.get("basic"), dict) else {}
        name = " ".join(
            x
            for x in (
                str(basic.get("first_name", "") or ""),
                str(basic.get("last_name", "") or ""),
            )
            if x
        )
        taxes = r.get("taxonomies", []) if isinstance(r.get("taxonomies"), list) else []
        primary = next(
            (t for t in taxes if isinstance(t, dict) and t.get("primary")), {}
        )
        if not primary and taxes and isinstance(taxes[0], dict):
            primary = taxes[0]
        addrs = r.get("addresses", []) if isinstance(r.get("addresses"), list) else []
        loc = next(
            (
                a
                for a in addrs
                if isinstance(a, dict) and a.get("address_purpose") == "LOCATION"
            ),
            {},
        )
        if not loc and addrs and isinstance(addrs[0], dict):
            loc = addrs[0]
        if not str(r.get("number", "") or ""):
            continue
        out.append(
            {
                "npi": str(r.get("number", "")),
                "name": name or str(basic.get("organization_name", "") or ""),
                "credential": str(basic.get("credential", "") or ""),
                "specialty": str(primary.get("desc", "") or ""),
                "city": str(loc.get("city", "") or ""),
                "state": str(loc.get("state", "") or ""),
            }
        )
    return out


def fetch_npi(
    number: str = "",
    first_name: str = "",
    last_name: str = "",
    state: str = "",
    limit: int = 5,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """NPPES NPI registry lookup by number or name+state. Cached."""
    params = {"version": "2.1", "limit": str(max(1, min(limit, 20)))}
    if number.strip():
        params["number"] = number.strip()
    else:
        if first_name.strip():
            params["first_name"] = first_name.strip()
        if last_name.strip():
            params["last_name"] = last_name.strip()
        if state.strip():
            params["state"] = state.strip().upper()
    if len(params) <= 2:
        return {
            "providers": [],
            "source": "offline-fallback",
            "note": "provide an NPI number or a name",
        }
    key = f"npi|{json.dumps(params, sort_keys=True)}"
    cache, hit = _rw_cached(key)
    if hit is not None:
        return {**hit, "source": "cache"}
    blank: dict[str, Any] = {"providers": []}
    try:
        import httpx  # core dep, imported lazily

        r = httpx.get(NPI_REGISTRY, params=params, timeout=timeout)
        r.raise_for_status()
        result = {"providers": parse_npi_results(r.json())}
        _rw_store(key, cache, result)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}
