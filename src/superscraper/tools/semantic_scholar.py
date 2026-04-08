from __future__ import annotations

import json
from pathlib import Path

from semanticscholar.Paper import Paper as SemanticScholarPaper
from semanticscholar import AsyncSemanticScholar

CACHE_DIR = Path(__file__).parent / ".cache" / "semantic_scholar"

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


def _paper_from_cache(data: dict) -> SemanticScholarPaper:
    return SemanticScholarPaper(data)


async def lookup_paper_by_doi(doi: str) -> SemanticScholarPaper:
    """Look up a paper on Semantic Scholar by DOI and return its metadata."""
    semantic_scholar = AsyncSemanticScholar()
    return await semantic_scholar.get_paper(doi, fields=PAPER_FIELDS)


async def lookup_paper_by_doi_cached(doi: str) -> SemanticScholarPaper:
    """Cached version of lookup_paper_by_doi."""
    cached = _read_cache(doi)
    if cached is not None:
        return _paper_from_cache(cached)

    paper = await lookup_paper_by_doi(doi)
    _write_cache(doi, paper.raw_data)
    return paper


async def lookup_abstract_by_doi(doi: str) -> str:
    """Look up a paper on Semantic Scholar by DOI and return its abstract."""
    paper = await lookup_paper_by_doi(doi)
    return paper.abstract


async def lookup_abstract_by_doi_cached(doi: str) -> str:
    """Cached version of lookup_abstract_by_doi."""
    paper = await lookup_paper_by_doi_cached(doi)
    return paper.abstract


def _extract_doi_from_acm_link(acm_link: str) -> str:
    assert acm_link.startswith("https://dl.acm.org/doi/")
    doi = acm_link[len("https://dl.acm.org/doi/") :]
    if doi.endswith("/"):
        doi = doi[:-1]
    return doi


# https://dl.acm.org/doi/10.1145/3731569.3764800
async def lookup_abstract_from_acm_link(acm_link: str) -> str:
    """Look up a paper on Semantic Scholar by ACM DOI link and return its abstract."""
    return await lookup_abstract_by_doi(_extract_doi_from_acm_link(acm_link))


async def lookup_abstract_from_acm_link_cached(acm_link: str) -> str:
    """Cached version of lookup_abstract_from_acm_link."""
    return await lookup_abstract_by_doi_cached(_extract_doi_from_acm_link(acm_link))
