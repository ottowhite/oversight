"""Harvester for programming-languages conference proceedings.

Fetches a venue/year volume from DBLP, looks up abstracts and author
affiliations from OpenAlex (with a Semantic Scholar fallback), and emits
papers in the ``scraped`` JSON shape consumed by
:meth:`oversight.Paper.Paper.from_scraped_json`.

Currently hardcoded to ``("popl", 2024)`` — the (venue, year) constructor
parameters are present so Phase 2 can drive the full back-catalogue without
touching the implementation. See ``docs/pl-conferences-plan.md``.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Iterable

import requests

logger = logging.getLogger(__name__)


# DBLP returns ``Proc. ACM Program. Lang.`` (PACMPL) for POPL/PLDI/ICFP/OOPSLA
# from 2017 onwards. ``number`` discriminates the issue (e.g. "POPL").
_PACMPL_ISSUES = {
    "popl": "POPL",
    "pldi": "PLDI",
    "icfp": "ICFP",
    "oopsla": "OOPSLA",
}

# Friendly conference label written into the ``conference_name`` field of the
# emitted JSON (and ultimately the ``source`` column in the database).
_CONFERENCE_LABEL = {
    "popl": "POPL",
    "pldi": "PLDI",
    "icfp": "ICFP",
    "oopsla": "OOPSLA",
}

_USER_AGENT = "oversight/0.1 (https://github.com/charlielidbury/oversight)"
_OPENALEX_MAILTO = "charlie.lidbury@icloud.com"


class PLConferenceHarvester:
    """Harvest a single (venue, year) volume into a ``scraped``-format JSON file.

    Parameters
    ----------
    venue:
        Lowercase venue slug, e.g. ``"popl"``.
    year:
        Four-digit year of the volume.
    output_dir:
        Directory under which ``<venue>/<year>.json`` will be written.
    cache_dir:
        Optional directory for caching OpenAlex / Semantic Scholar responses
        across reruns. Created on demand. Use a path inside ``.cache/`` so it
        stays out of git.
    request_delay_s:
        Polite delay between external API requests.
    """

    def __init__(
        self,
        venue: str,
        year: int,
        output_dir: str | Path = "data/pl_conferences",
        cache_dir: str | Path | None = None,
        request_delay_s: float = 0.1,
    ) -> None:
        venue = venue.lower()
        if venue not in _PACMPL_ISSUES:
            raise ValueError(
                f"Unsupported venue {venue!r}. Phase 1 only supports POPL; "
                "Phase 2 will add the rest."
            )
        if venue != "popl" or year != 2024:
            # Soft guard rather than hard error so future phases just need to
            # remove this branch.
            logger.warning(
                "PLConferenceHarvester is currently exercised only for POPL 2024;"
                " (%s, %s) may surface unhandled edge cases.",
                venue,
                year,
            )

        self.venue = venue
        self.year = year
        self.output_dir = Path(output_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.request_delay_s = request_delay_s

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})

    # ------------------------------------------------------------------
    # Top-level entry point
    # ------------------------------------------------------------------

    def harvest(self) -> Path:
        """Run the full pipeline. Returns the path to the JSON file written."""
        dblp_entries = list(self._fetch_dblp_entries())
        logger.info(
            "DBLP listed %d entries for %s %s",
            len(dblp_entries),
            self.venue.upper(),
            self.year,
        )

        papers: list[dict[str, Any]] = []
        skipped_no_doi: list[str] = []
        skipped_no_abstract: list[str] = []

        for entry in dblp_entries:
            title = (entry.get("title") or "").rstrip(".")
            doi = entry.get("doi")
            if not doi:
                skipped_no_doi.append(title)
                logger.warning("Skipping %r: no DOI in DBLP entry", title)
                continue

            paper = self._build_paper(entry, doi)
            if paper is None:
                skipped_no_abstract.append(title)
                continue
            papers.append(paper)

        logger.info(
            "Built %d papers (skipped %d with no DOI, %d with no abstract)",
            len(papers),
            len(skipped_no_doi),
            len(skipped_no_abstract),
        )

        out_path = self.output_dir / self.venue / f"{self.year}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        logger.info("Wrote %s (%d papers)", out_path, len(papers))
        return out_path

    # ------------------------------------------------------------------
    # DBLP
    # ------------------------------------------------------------------

    def _fetch_dblp_entries(self) -> Iterable[dict[str, Any]]:
        """Yield raw DBLP ``info`` dicts for the configured venue+year.

        We use the search API (``/search/publ/api``) constrained to the
        relevant table-of-contents BHT. The per-volume ``.json`` endpoint
        documented in the dblp wiki returns 404 for the current PACMPL
        volumes, so the search API is the reliable path.
        """
        bht = self._dblp_toc_bht()
        # Query: facet on the TOC, plus the issue token (e.g. "POPL") to
        # restrict to the right PACMPL number when the TOC covers multiple.
        issue_token = _PACMPL_ISSUES[self.venue]
        query = f"toc:{bht}: {issue_token}"

        url = "https://dblp.org/search/publ/api"
        params = {
            "q": query,
            "format": "json",
            "h": 1000,  # well above the ~100 papers/year ceiling
            "f": 0,
        }
        resp = self._session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        hits = payload.get("result", {}).get("hits", {})
        total = int(hits.get("@total", 0))
        sent = int(hits.get("@sent", 0))
        if total > sent:
            raise RuntimeError(
                f"DBLP returned {sent}/{total} hits — bump 'h' parameter."
            )

        for hit in hits.get("hit", []):
            info = hit.get("info", {})
            # Defensive filtering: keep only PACMPL articles for the right
            # issue. The search query already constrains this, but if the
            # query is loosened later the data must stay clean.
            if info.get("number") != issue_token:
                continue
            if str(info.get("year")) != str(self.year):
                continue
            if info.get("type") and info["type"] != "Journal Articles":
                # Editor-only "Proceedings" records etc. None observed for
                # PACMPL, but keep the guard for non-PACMPL venues.
                continue
            yield info

    def _dblp_toc_bht(self) -> str:
        """Return the DBLP TOC BHT identifier for ``(venue, year)``."""
        # PACMPL volume number = year - 2016 (vol 1 = 2017).
        if self.venue in _PACMPL_ISSUES:
            volume = self.year - 2016
            if volume < 1:
                raise ValueError(
                    f"PACMPL coverage starts in 2017; cannot fetch {self.venue} {self.year}"
                )
            return f"db/journals/pacmpl/pacmpl{volume}.bht"
        raise ValueError(f"Unsupported venue {self.venue!r}")

    # ------------------------------------------------------------------
    # Paper assembly
    # ------------------------------------------------------------------

    def _build_paper(self, entry: dict[str, Any], doi: str) -> dict[str, Any] | None:
        """Combine a DBLP entry with OpenAlex (or Semantic Scholar fallback).

        Returns ``None`` if no abstract can be obtained, in which case the
        caller skips the paper.
        """
        title = (entry.get("title") or "").rstrip(".")

        oa = self._fetch_openalex(doi)
        abstract: str | None = None
        publication_date: str | None = None
        oa_authors: list[dict[str, str]] = []

        if oa is not None:
            ai = oa.get("abstract_inverted_index")
            if ai:
                abstract = _reconstruct_abstract(ai)
            publication_date = oa.get("publication_date")
            oa_authors = _openalex_authors(oa)

        if not abstract:
            ss = self._fetch_semantic_scholar(doi)
            if ss is not None:
                abstract = (ss.get("abstract") or "").strip() or None

        if not abstract:
            logger.warning(
                "Skipping DOI %s (%r): no abstract in OpenAlex or Semantic Scholar",
                doi,
                title,
            )
            return None

        # Authors: prefer OpenAlex (has institutions). Fall back to DBLP
        # author list (no affiliations) so we never lose author names.
        if oa_authors:
            authors = oa_authors
        else:
            authors = _dblp_authors(entry)

        date = publication_date or self._fallback_date()
        link = f"https://dl.acm.org/doi/{doi}"

        return {
            "paper_id": doi,
            "title": title,
            "abstract": abstract,
            "date": date,
            "link": link,
            "conference_name": _CONFERENCE_LABEL[self.venue],
            "authors": authors,
            # Provenance — keeps the JSON debuggable without bloating it.
            "dblp_key": entry.get("key"),
            "venue": self.venue,
            "year": self.year,
        }

    def _fallback_date(self) -> str:
        # Conference dates differ by venue, but the volume publication date
        # captured by OpenAlex is what we really want. This is only used
        # when both abstract sources also fail to provide a date — which
        # currently never happens for PACMPL. Use Jan-1 of the volume year
        # as a stable default.
        return f"{self.year}-01-01"

    # ------------------------------------------------------------------
    # OpenAlex
    # ------------------------------------------------------------------

    def _fetch_openalex(self, doi: str) -> dict[str, Any] | None:
        cache_key = f"openalex/{_safe_filename(doi)}.json"
        cached = self._cache_load(cache_key)
        if cached is not None:
            return cached or None  # falsy {} stored as "miss"

        url = f"https://api.openalex.org/works/https://doi.org/{doi}"
        params = {"mailto": _OPENALEX_MAILTO}
        try:
            resp = self._session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            logger.warning("OpenAlex request failed for %s: %s", doi, exc)
            return None
        time.sleep(self.request_delay_s)
        if resp.status_code == 404:
            self._cache_store(cache_key, {})
            return None
        if resp.status_code != 200:
            logger.warning(
                "OpenAlex returned %s for %s (%s)",
                resp.status_code,
                doi,
                resp.text[:200],
            )
            return None
        data = resp.json()
        self._cache_store(cache_key, data)
        return data

    # ------------------------------------------------------------------
    # Semantic Scholar
    # ------------------------------------------------------------------

    def _fetch_semantic_scholar(self, doi: str) -> dict[str, Any] | None:
        cache_key = f"semantic_scholar/{_safe_filename(doi)}.json"
        cached = self._cache_load(cache_key)
        if cached is not None:
            return cached or None

        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        params = {"fields": "abstract,authors,year"}
        try:
            resp = self._session.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            logger.warning("Semantic Scholar request failed for %s: %s", doi, exc)
            return None
        time.sleep(self.request_delay_s)
        if resp.status_code == 404:
            self._cache_store(cache_key, {})
            return None
        if resp.status_code == 429:
            # Rate limited — wait briefly and retry once.
            time.sleep(2.0)
            resp = self._session.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning(
                "Semantic Scholar returned %s for %s (%s)",
                resp.status_code,
                doi,
                resp.text[:200],
            )
            return None
        data = resp.json()
        self._cache_store(cache_key, data)
        return data

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _cache_load(self, key: str) -> dict[str, Any] | None:
        if self.cache_dir is None:
            return None
        path = self.cache_dir / key
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _cache_store(self, key: str, value: dict[str, Any]) -> None:
        if self.cache_dir is None:
            return
        path = self.cache_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)
        tmp.replace(path)


# ----------------------------------------------------------------------
# Pure helpers (testable without network)
# ----------------------------------------------------------------------


def _reconstruct_abstract(inverted_index: dict[str, list[int]]) -> str:
    """Reconstruct an OpenAlex abstract from its inverted-index form."""
    positions: list[tuple[int, str]] = []
    for word, locs in inverted_index.items():
        for loc in locs:
            positions.append((loc, word))
    positions.sort(key=lambda p: p[0])
    return " ".join(word for _, word in positions)


def _openalex_authors(work: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for authorship in work.get("authorships", []) or []:
        author = authorship.get("author") or {}
        display_name = (author.get("display_name") or "").strip()
        if not display_name:
            continue
        first, last = _split_name(display_name)
        institutions = authorship.get("institutions") or []
        institution_name = ""
        if institutions:
            institution_name = (institutions[0].get("display_name") or "").strip()
        out.append(
            {
                "first_name": first,
                "last_name": last,
                "institution": institution_name,
            }
        )
    return out


def _dblp_authors(entry: dict[str, Any]) -> list[dict[str, str]]:
    """Extract authors from a DBLP search-API ``info`` dict."""
    raw = (entry.get("authors") or {}).get("author")
    if raw is None:
        return []
    if isinstance(raw, dict):
        # Single-author papers come back as a dict, not a list.
        raw = [raw]
    out: list[dict[str, str]] = []
    for author in raw:
        text = (author.get("text") or "").strip()
        # DBLP disambiguates name collisions with " 0001" etc — strip those.
        text = _strip_dblp_disambiguator(text)
        if not text:
            continue
        first, last = _split_name(text)
        out.append({"first_name": first, "last_name": last, "institution": ""})
    return out


def _split_name(name: str) -> tuple[str, str]:
    parts = name.split()
    if len(parts) == 0:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


def _strip_dblp_disambiguator(name: str) -> str:
    parts = name.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 4:
        return parts[0]
    return name


def _safe_filename(s: str) -> str:
    return s.replace("/", "_").replace(":", "_")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    harvester = PLConferenceHarvester(
        venue="popl",
        year=2024,
        output_dir="data/pl_conferences",
        cache_dir=".cache/pl_conferences",
    )
    harvester.harvest()
