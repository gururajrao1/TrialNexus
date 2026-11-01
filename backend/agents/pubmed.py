"""Agent support - PubMed literature lookup via NCBI Entrez.

Cookbook integration: esearch + esummary for standard-of-care adverse
event profiles and validation literature. Disk-cached with offline
fallback, mirroring the CT.gov lookup. No API key (2 calls/lookup,
well under the unauthenticated rate limit).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from backend.config import PUBMED_CACHE, PUBMED_CACHE_MAX_ENTRIES

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
TOOL = "TrialNexusOS"


def _read_cache() -> dict[str, Any]:
    try:
        if PUBMED_CACHE.exists():
            data = json.loads(PUBMED_CACHE.read_text())
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def _write_cache(cache: dict[str, Any]) -> None:
    while len(cache) > PUBMED_CACHE_MAX_ENTRIES:
        cache.pop(next(iter(cache)))
    try:
        PUBMED_CACHE.parent.mkdir(parents=True, exist_ok=True)
        PUBMED_CACHE.write_text(json.dumps(cache))
    except OSError:
        pass


def parse_esearch_xml(payload: str) -> tuple[int, list[str]]:
    """(total count, pmid list) from an esearch response. Pure, offline."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return 0, []
    count = 0
    count_el = root.find("Count")
    if count_el is not None and (count_el.text or "").strip().isdigit():
        count = int(count_el.text.strip())
    pmids = [
        (e.text or "").strip()
        for e in root.findall("./IdList/Id")
        if (e.text or "").strip()
    ]
    return count, pmids


def parse_esummary_xml(payload: str) -> list[dict[str, str]]:
    """Article cards from an esummary response. Pure, offline."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    out = []
    for doc in root.findall("DocSum"):
        pmid = (doc.findtext("Id") or "").strip()
        title = (doc.findtext("./Item[@Name='Title']") or "").strip()
        journal = (doc.findtext("./Item[@Name='FullJournalName']") or "").strip()
        pubdate = (doc.findtext("./Item[@Name='PubDate']") or "").strip()
        if pmid:
            out.append(
                {"pmid": pmid, "title": title, "journal": journal, "year": pubdate[:4]}
            )
    return out


def fetch_pubmed(term: str, retmax: int = 5, timeout: float = 10.0) -> dict[str, Any]:
    """Search PubMed; cached, with offline fallback. Never raises."""
    key = f"{term.lower()}|{max(1, min(retmax, 20))}"
    cache = _read_cache()
    if key in cache and isinstance(cache[key], dict):
        return {**cache[key], "source": "cache"}
    blank = {"term": term, "count": 0, "articles": []}
    try:
        import httpx  # core dep, imported lazily

        search = httpx.get(
            ESEARCH,
            params={
                "db": "pubmed",
                "term": term,
                "retmax": max(1, min(retmax, 20)),
                "retmode": "xml",
                "tool": TOOL,
            },
            timeout=timeout,
        )
        search.raise_for_status()
        count, pmids = parse_esearch_xml(search.text)
        articles: list[dict[str, str]] = []
        if pmids:
            summary = httpx.get(
                ESUMMARY,
                params={
                    "db": "pubmed",
                    "id": ",".join(pmids),
                    "retmode": "xml",
                    "tool": TOOL,
                },
                timeout=timeout,
            )
            summary.raise_for_status()
            articles = parse_esummary_xml(summary.text)
        result = {"term": term, "count": count, "articles": articles}
        cache[key] = result
        _write_cache(cache)
        return {**result, "source": "live"}
    except Exception:
        hit = cache.get(key)
        if isinstance(hit, dict):
            return {**hit, "source": "cache"}
        return {**blank, "source": "offline-fallback"}
