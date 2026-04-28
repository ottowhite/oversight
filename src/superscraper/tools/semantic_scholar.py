from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from semanticscholar.Paper import Paper as SemanticScholarPaper
from semanticscholar import AsyncSemanticScholar

load_dotenv()

CACHE_DIR = Path(__file__).parent / ".cache" / "semantic_scholar"
NAME_CACHE_DIR = Path(__file__).parent / ".cache" / "semantic_scholar_by_name"

MIN_REQUEST_INTERVAL_SECONDS = 1.0

_request_semaphore: asyncio.Semaphore | None = None
_last_request_monotonic: float = 0.0


def _get_semaphore() -> asyncio.Semaphore:
    global _request_semaphore
    if _request_semaphore is None:
        _request_semaphore = asyncio.Semaphore(1)
    return _request_semaphore


async def _throttle() -> None:
    """Sleep so that consecutive requests are at least MIN_REQUEST_INTERVAL_SECONDS apart."""
    global _last_request_monotonic
    elapsed = time.monotonic() - _last_request_monotonic
    if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
        await asyncio.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
    _last_request_monotonic = time.monotonic()


PAPER_FIELDS = [
    "title",
    "abstract",
    "authors",
    "year",
    "venue",
    "citationCount",
    "url",
    "openAccessPdf",
    "externalIds",
]


def _cache_key(doi: str) -> str:
    """Convert a DOI to a safe filename."""
    return doi.replace("/", "__")


def _read_cache(doi: str) -> dict | None:
    path = CACHE_DIR / f"{_cache_key(doi)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write_cache(doi: str, data: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{_cache_key(doi)}.json"
    path.write_text(json.dumps(data, indent=2))


async def lookup_paper_by_doi(doi: str, *, cached: bool = True) -> SemanticScholarPaper:
    """Look up a paper on Semantic Scholar by DOI and return its metadata."""
    if cached:
        hit = _read_cache(doi)
        if hit is not None:
            return SemanticScholarPaper(hit)

    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    assert api_key, "SEMANTIC_SCHOLAR_API_KEY is not set"
    semantic_scholar = AsyncSemanticScholar(api_key=api_key)
    async with _get_semaphore():
        await _throttle()
        paper = await semantic_scholar.get_paper(doi, fields=PAPER_FIELDS)

    if cached:
        _write_cache(doi, paper.raw_data)

    return paper


def _name_cache_key(name: str) -> str:
    """Hash a paper name into a safe, fixed-length filename."""
    return hashlib.sha256(name.strip().lower().encode()).hexdigest()


def _read_name_cache(name: str) -> dict | None:
    path = NAME_CACHE_DIR / f"{_name_cache_key(name)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write_name_cache(name: str, data: dict) -> None:
    NAME_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = NAME_CACHE_DIR / f"{_name_cache_key(name)}.json"
    path.write_text(json.dumps(data, indent=2))


async def lookup_paper_by_name(
    name: str, *, cached: bool = True
) -> SemanticScholarPaper | None:
    """Look up a paper on Semantic Scholar by name and return its metadata."""
    if cached:
        hit = _read_name_cache(name)
        if hit is not None:
            return SemanticScholarPaper(hit)

    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    assert api_key, "SEMANTIC_SCHOLAR_API_KEY is not set"
    semantic_scholar = AsyncSemanticScholar(api_key=api_key)
    async with _get_semaphore():
        await _throttle()
        results = await semantic_scholar.search_paper(name, fields=PAPER_FIELDS)
    if not results:
        return None
    paper = results[0]

    if cached:
        _write_name_cache(name, paper.raw_data)

    return paper


async def lookup_abstract_by_doi(doi: str, *, cached: bool = True) -> str:
    """Look up a paper on Semantic Scholar by DOI and return its abstract."""
    paper = await lookup_paper_by_doi(doi, cached=cached)
    return paper.abstract


def _extract_doi_from_acm_link(acm_link: str) -> str:
    assert acm_link.startswith("https://dl.acm.org/doi/")
    doi = acm_link[len("https://dl.acm.org/doi/") :]
    if doi.endswith("/"):
        doi = doi[:-1]
    return doi


# https://dl.acm.org/doi/10.1145/3731569.3764800
async def lookup_abstract_from_acm_link(acm_link: str, *, cached: bool = True) -> str:
    """Look up a paper on Semantic Scholar by ACM DOI link and return its abstract."""
    return await lookup_abstract_by_doi(
        _extract_doi_from_acm_link(acm_link), cached=cached
    )
