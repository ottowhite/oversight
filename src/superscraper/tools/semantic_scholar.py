from __future__ import annotations
from semanticscholar.Paper import Paper as SemanticScholarPaper
from semanticscholar import AsyncSemanticScholar


async def lookup_paper_by_doi(doi: str) -> SemanticScholarPaper:
    """Look up a paper on Semantic Scholar by DOI and return its metadata."""
    semantic_scholar = AsyncSemanticScholar()
    return await semantic_scholar.get_paper(
        doi,
        fields=[
            "title",
            "abstract",
            "authors",
            "year",
            "venue",
            "citationCount",
            "url",
            "openAccessPdf",
            "externalIds",
        ],
    )


async def lookup_abstract_by_doi(doi: str) -> str:
    """Look up a paper on Semantic Scholar by DOI and return its abstract."""
    paper = await lookup_paper_by_doi(doi)
    return paper.abstract


# https://dl.acm.org/doi/10.1145/3731569.3764800
async def lookup_abstract_from_acm_link(acm_link: str) -> str:
    """Look up a paper on Semantic Scholar by ACM DOI link and return its abstract."""
    # Ensure this is the correct type of link
    assert acm_link.startswith("https://dl.acm.org/doi/")

    # Strip the "https://dl.acm.org/doi/" prefix to get the DOI
    doi = acm_link[len("https://dl.acm.org/doi/") :]

    # Strip trailing slash if it exists
    if doi.endswith("/"):
        doi = doi[:-1]

    return await lookup_abstract_by_doi(doi)
