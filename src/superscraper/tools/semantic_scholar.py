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


async def lookup_paper_by_doi(doi: str, *, cached: bool = True) -> SemanticScholarPaper:
    """Look up a paper on Semantic Scholar by DOI and return its metadata."""
    if cached:
        hit = _read_cache(doi)
        if hit is not None:
            return SemanticScholarPaper(hit)

    semantic_scholar = AsyncSemanticScholar()
    paper = await semantic_scholar.get_paper(doi, fields=PAPER_FIELDS)

    if cached:
        _write_cache(doi, paper.raw_data)

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
