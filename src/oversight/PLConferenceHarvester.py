"""Harvester for programming-languages conference proceedings.

For a ``(venue, year)`` pair this fetches the DBLP table-of-contents,
looks up abstracts and author affiliations from OpenAlex (with a Semantic
Scholar fallback), and emits papers in the ``scraped`` JSON shape consumed
by :meth:`oversight.Paper.Paper.from_scraped_json`.

Two TOC schemes coexist on DBLP:

1. **PACMPL journal articles** — POPL/PLDI/ICFP/OOPSLA from the year SIGPLAN
   moved them onto PACMPL onwards. The TOC lives at
   ``db/journals/pacmpl/pacmpl<vol>.bht`` where ``vol = year - 2016``;
   each volume bundles multiple venues, discriminated by the ``number``
   field (``"POPL"``, ``"PLDI"``, ``"ICFP"``, ``"OOPSLA"``,
   ``"OOPSLA1"``/``"OOPSLA2"`` once OOPSLA split into Spring + Fall in 2022).

2. **Conference proceedings** — everything else (pre-PACMPL POPL/PLDI/ICFP/
   OOPSLA, plus all years of ESOP/ECOOP/CC/Haskell). The TOC lives at
   ``db/conf/<venue>/<venue><year>.bht`` (or ``<venue><year>-1.bht``,
   ``-2.bht`` when proceedings are split across volumes, e.g. ESOP).

DBLP's ``db/conf/<venue>/index.xml`` enumerates every issue/proceedings
that exists for a venue, including which scheme each year uses. The
:class:`PLVenueIndex` class parses that file; the harvester then iterates
the ``(year, [TOC entries])`` it returns.

See ``docs/pl-conferences-plan.md``.
"""

from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import requests

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Venue registry
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class VenueSpec:
    """Static facts about a venue: how to find it on DBLP, how to label it."""

    slug: str  # lowercase, matches DBLP path component
    label: str  # human label written into ``conference_name`` / DB ``source``
    pacmpl_numbers: frozenset[str] = field(default_factory=frozenset)
    """PACMPL ``number`` values that map to this venue. Empty for non-PACMPL
    venues. POPL/PLDI/ICFP use ``{label}``; OOPSLA additionally accepts
    ``OOPSLA1`` / ``OOPSLA2`` for the post-2022 split."""


VENUES: dict[str, VenueSpec] = {
    spec.slug: spec
    for spec in [
        # Tier 1 — SIGPLAN flagship (PACMPL since 2017/2018/2023 depending on venue)
        VenueSpec("popl", "POPL", frozenset({"POPL"})),
        VenueSpec("pldi", "PLDI", frozenset({"PLDI"})),
        VenueSpec("icfp", "ICFP", frozenset({"ICFP"})),
        VenueSpec("oopsla", "OOPSLA", frozenset({"OOPSLA", "OOPSLA1", "OOPSLA2"})),
        # Tier 2 — also clearly PL, conf-only
        VenueSpec("esop", "ESOP"),
        VenueSpec("ecoop", "ECOOP"),
        VenueSpec("cc", "CC"),
        VenueSpec("haskell", "Haskell"),
    ]
}


# ----------------------------------------------------------------------
# DBLP TOC discovery
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class TOCEntry:
    """One DBLP table-of-contents pointing at a list of papers.

    A single ``(venue, year)`` may resolve to multiple TOC entries:
    PACMPL OOPSLA 2022+ has Spring + Fall (``OOPSLA1``/``OOPSLA2``) in one
    journal volume; conf-style ESOP 2024 has two parts under separate BHT
    files.
    """

    bht: str
    """DBLP TOC identifier, e.g. ``db/conf/popl/popl2010.bht`` or
    ``db/journals/pacmpl/pacmpl1.bht``."""

    pacmpl_number: str | None
    """When the TOC bundles multiple venues (PACMPL), the ``number``
    discriminator (e.g. ``"POPL"``); ``None`` for single-venue conf TOCs."""


class PLVenueIndex:
    """Loads DBLP's ``db/conf/<venue>/index.xml`` and yields ``(year, [TOCEntry])``.

    The XML is unfortunately not strict (it embeds raw HTML headings like
    ``<h2>``), so we parse it as text rather than as an XML tree. Two
    relevant productions per year:

    - ``<issue href="db/journals/pacmpl/pacmplN.html" ... nr="POPL"/>``
      — denotes PACMPL coverage (post-2017).
    - ``<proceedings key="conf/popl/2010" ...> ... <url>db/conf/popl/popl2010.html</url> ... </proceedings>``
      — denotes a conf-style proceedings.

    We filter out workshops co-located with the main conference (PLMW@POPL,
    PEPM@POPL, TyDe@ICFP, etc.) by requiring the proceedings ``key`` to
    match ``conf/<slug>/YYYY(-N)?$`` — workshops use suffixes like
    ``2015plmw``.
    """

    _USER_AGENT = "oversight/0.1 (https://github.com/charlielidbury/oversight)"

    def __init__(
        self,
        venue: VenueSpec,
        cache_dir: Path | None = None,
        request_delay_s: float = 0.5,
    ) -> None:
        self.venue = venue
        self.cache_dir = cache_dir
        self.request_delay_s = request_delay_s
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self._USER_AGENT})
        self._raw_xml: str | None = None

    # ------------------------------------------------------------------

    def discover(self) -> list[tuple[int, list[TOCEntry]]]:
        """Return ``[(year, [TOCEntry, ...]), ...]`` newest-first."""
        xml_text = self._load_xml()
        return list(_parse_index_xml(xml_text, self.venue))

    # ------------------------------------------------------------------

    def _load_xml(self) -> str:
        if self._raw_xml is not None:
            return self._raw_xml
        cached = self._cache_path()
        if cached is not None and cached.exists():
            self._raw_xml = cached.read_text(encoding="utf-8")
            return self._raw_xml

        url = f"https://dblp.org/db/conf/{self.venue.slug}/index.xml"
        logger.info("Fetching DBLP venue index %s", url)
        resp = _request_with_retries(self._session, url, timeout=30)
        resp.raise_for_status()
        time.sleep(self.request_delay_s)

        text = resp.text
        if cached is not None:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(text, encoding="utf-8")
        self._raw_xml = text
        return text

    def _cache_path(self) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / "dblp_index" / f"{self.venue.slug}.xml"


# Header like "<h2>37th POPL 2010: Madrid, Spain</h2>", or with nested tags
# such as "<h2>10th CC@<ref href=...>ETAPS</ref> 2001: Genova, Italy</h2>".
# Non-greedy ``.*?`` plus DOTALL lets nested tags through; the year is
# extracted from the inner text downstream.
_H2_YEAR_RE = re.compile(r"<h2>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_YEAR_FROM_HEADING_RE = re.compile(r"\b(19|20)\d{2}\b")
# Issue: <issue href="..." nr="POPL" .../>  (self-closing with optional space)
_ISSUE_RE = re.compile(
    r"<issue\s+([^>]+?)/?>",
    re.IGNORECASE | re.DOTALL,
)
# Proceedings opening tag
_PROCEEDINGS_KEY_RE = re.compile(
    r'<proceedings\s+key="([^"]+)"',
    re.IGNORECASE,
)
# URL element inside a proceedings block
_URL_RE = re.compile(r"<url>([^<]+)</url>", re.IGNORECASE)


def _parse_index_xml(
    xml_text: str, venue: VenueSpec
) -> Iterator[tuple[int, list[TOCEntry]]]:
    """Yield ``(year, [TOCEntry])`` for every year listed in the venue index.

    Pure function — no IO — so it stays trivially testable.
    """
    # Split the document into ``<h2>`` blocks. Each block runs from one
    # ``<h2>`` to the next.
    headings = list(_H2_YEAR_RE.finditer(xml_text))
    # Sentinel end position
    headings_with_ends: list[tuple[re.Match[str], int]] = []
    for i, m in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(xml_text)
        headings_with_ends.append((m, end))

    seen_years: set[int] = set()
    for match, end in headings_with_ends:
        heading_text = match.group(1)
        year_match = _YEAR_FROM_HEADING_RE.search(heading_text)
        if year_match is None:
            continue
        year = int(year_match.group(0))
        if year in seen_years:
            continue
        seen_years.add(year)

        block = xml_text[match.end() : end]
        entries = list(_extract_toc_entries(block, venue, year))
        if entries:
            yield (year, entries)


def _extract_toc_entries(block: str, venue: VenueSpec, year: int) -> Iterator[TOCEntry]:
    """Pull out ``<issue>`` and ``<proceedings>`` from one year's block."""
    # PACMPL issues
    if venue.pacmpl_numbers:
        for m in _ISSUE_RE.finditer(block):
            attrs = _parse_xml_attrs(m.group(1))
            href = attrs.get("href", "")
            if not href.startswith("db/journals/pacmpl/"):
                continue
            number = attrs.get("nr", "")
            if number not in venue.pacmpl_numbers:
                continue
            bht = href.replace(".html", ".bht").rstrip("/")
            yield TOCEntry(bht=bht, pacmpl_number=number)

    # Conf-style proceedings. Walk every <proceedings> in the block; pick
    # only those whose key matches ``conf/<slug>/YYYY(-N)?$``. DBLP also
    # uses 2-digit-year keys for some early proceedings (e.g.
    # ``conf/popl/77`` for POPL 1977), so accept those too.
    yy = f"{year % 100:02d}"
    expected_pattern = re.compile(
        rf"^conf/{re.escape(venue.slug)}/(?:{year}|{yy})(?:-\d+)?$"
    )
    for m in _PROCEEDINGS_KEY_RE.finditer(block):
        key = m.group(1)
        if not expected_pattern.match(key):
            continue
        # Find the matching <url>...</url> within this proceedings element.
        # Search for the closing </proceedings> after this opening tag and
        # restrict the URL search to the slice between them.
        proc_start = m.start()
        proc_end_match = re.search(r"</proceedings>", block[proc_start:], re.IGNORECASE)
        if proc_end_match is None:
            continue
        proc_block = block[proc_start : proc_start + proc_end_match.end()]
        url_match = _URL_RE.search(proc_block)
        if url_match is None:
            continue
        url = url_match.group(1).strip()
        bht = url.replace(".html", ".bht")
        yield TOCEntry(bht=bht, pacmpl_number=None)


def _parse_xml_attrs(attr_str: str) -> dict[str, str]:
    """Parse `key="value"` pairs out of an XML attribute substring."""
    return {
        m.group(1): m.group(2) for m in re.finditer(r'(\w[\w-]*)="([^"]*)"', attr_str)
    }


# ----------------------------------------------------------------------
# Harvester
# ----------------------------------------------------------------------


_USER_AGENT = "oversight/0.1 (https://github.com/charlielidbury/oversight)"
_OPENALEX_MAILTO = "charlie.lidbury@icloud.com"


def _request_with_retries(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 30,
    max_attempts: int = 4,
) -> requests.Response:
    """GET with exponential backoff on transient errors (429/503/connection)."""
    attempt = 0
    backoff = 2.0
    while True:
        attempt += 1
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            if attempt >= max_attempts:
                raise
            logger.warning(
                "Request to %s failed (%s); retry %d/%d in %.1fs",
                url,
                exc,
                attempt,
                max_attempts,
                backoff,
            )
            time.sleep(backoff)
            backoff *= 2
            continue
        if resp.status_code in (429, 502, 503, 504) and attempt < max_attempts:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else backoff
            logger.warning(
                "Request to %s returned %s; retry %d/%d in %.1fs",
                url,
                resp.status_code,
                attempt,
                max_attempts,
                wait,
            )
            time.sleep(wait)
            backoff *= 2
            continue
        return resp


class PLConferenceHarvester:
    """Harvest a single ``(venue, year)`` into a ``scraped``-format JSON file.

    Parameters
    ----------
    venue:
        Lowercase venue slug from :data:`VENUES`.
    year:
        Four-digit year of the volume.
    output_dir:
        Directory under which ``<venue>/<year>.json`` will be written.
    cache_dir:
        Optional directory for caching DBLP / OpenAlex / Semantic Scholar
        responses across reruns. Created on demand. Use a path inside
        ``.cache/`` so it stays out of git.
    request_delay_s:
        Polite delay between external API requests.
    skip_existing_doi:
        If provided, a callable returning ``True`` for DOIs already present
        in the database. Skipping these short-circuits OpenAlex lookups.
    toc_entries:
        Pre-resolved DBLP TOC entries for this ``(venue, year)``. When
        provided, the harvester skips the per-venue index discovery step
        (useful when driving many years from a single :class:`PLVenueIndex`
        load).
    """

    def __init__(
        self,
        venue: str,
        year: int,
        output_dir: str | Path = "data/pl_conferences",
        cache_dir: str | Path | None = None,
        request_delay_s: float = 0.1,
        skip_existing_doi: Callable[[str], bool] | None = None,
        toc_entries: Sequence[TOCEntry] | None = None,
    ) -> None:
        venue = venue.lower()
        if venue not in VENUES:
            raise ValueError(
                f"Unsupported venue {venue!r}. Known venues: {sorted(VENUES.keys())}"
            )

        self.venue_spec = VENUES[venue]
        self.venue = venue
        self.year = year
        self.output_dir = Path(output_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.request_delay_s = request_delay_s
        self.skip_existing_doi = skip_existing_doi
        self._toc_entries = list(toc_entries) if toc_entries is not None else None

        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})

    # ------------------------------------------------------------------
    # Top-level entry point
    # ------------------------------------------------------------------

    def harvest(self) -> Path | None:
        """Run the full pipeline. Returns the path to the JSON written, or
        ``None`` if no papers were emitted (e.g. DBLP listed nothing)."""
        toc_entries = self._resolve_toc_entries()
        if not toc_entries:
            logger.warning(
                "No DBLP TOC entries found for %s %s; skipping.",
                self.venue_spec.label,
                self.year,
            )
            return None

        dblp_entries = list(self._fetch_dblp_entries(toc_entries))
        logger.info(
            "DBLP listed %d entries for %s %s (across %d TOC%s)",
            len(dblp_entries),
            self.venue_spec.label,
            self.year,
            len(toc_entries),
            "s" if len(toc_entries) != 1 else "",
        )

        papers: list[dict[str, Any]] = []
        skipped_no_doi: list[str] = []
        skipped_no_abstract: list[str] = []
        skipped_already_in_db = 0

        for entry in dblp_entries:
            title = (entry.get("title") or "").rstrip(".")
            doi = entry.get("doi")
            if not doi:
                skipped_no_doi.append(title)
                logger.debug("Skipping %r: no DOI in DBLP entry", title)
                continue

            if self.skip_existing_doi is not None and self.skip_existing_doi(doi):
                skipped_already_in_db += 1
                continue

            paper = self._build_paper(entry, doi)
            if paper is None:
                skipped_no_abstract.append(title)
                continue
            papers.append(paper)

        logger.info(
            "Built %d papers (%d in DB; %d no-DOI; %d no-abstract)",
            len(papers),
            skipped_already_in_db,
            len(skipped_no_doi),
            len(skipped_no_abstract),
        )

        out_path = self.output_dir / self.venue / f"{self.year}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not papers:
            # Don't write an empty file — if every DOI is already in DB we
            # have nothing to consume; an existing JSON from a previous run
            # should remain for reproducibility.
            if not out_path.exists():
                logger.info(
                    "No new papers for %s %s; nothing to write.",
                    self.venue_spec.label,
                    self.year,
                )
                return None
            return out_path
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        logger.info("Wrote %s (%d papers)", out_path, len(papers))
        return out_path

    # ------------------------------------------------------------------
    # TOC resolution
    # ------------------------------------------------------------------

    def _resolve_toc_entries(self) -> list[TOCEntry]:
        if self._toc_entries is not None:
            return self._toc_entries
        index = PLVenueIndex(
            self.venue_spec,
            cache_dir=self.cache_dir,
            request_delay_s=self.request_delay_s,
        )
        for year, entries in index.discover():
            if year == self.year:
                self._toc_entries = entries
                return entries
        self._toc_entries = []
        return []

    # ------------------------------------------------------------------
    # DBLP search-API: list papers in a TOC
    # ------------------------------------------------------------------

    def _fetch_dblp_entries(
        self, toc_entries: Sequence[TOCEntry]
    ) -> Iterable[dict[str, Any]]:
        seen_keys: set[str] = set()
        for toc in toc_entries:
            for info in self._fetch_dblp_toc_papers(toc):
                key = info.get("key") or info.get("doi")
                if key in seen_keys:
                    continue
                if key:
                    seen_keys.add(key)
                yield info

    def _fetch_dblp_toc_papers(self, toc: TOCEntry) -> Iterator[dict[str, Any]]:
        """Yield raw DBLP ``info`` dicts for a single TOC entry."""
        cache_key = self._dblp_toc_cache_key(toc)
        cached = self._cache_load(cache_key)
        if cached is not None:
            payload = cached
        else:
            # Query the search API faceted on the TOC. Add the PACMPL
            # ``number`` token (e.g. "POPL") to disambiguate when the same
            # TOC bundles several venues.
            query_terms = [f"toc:{toc.bht}:"]
            if toc.pacmpl_number is not None:
                query_terms.append(toc.pacmpl_number)
            url = "https://dblp.org/search/publ/api"
            params = {
                "q": " ".join(query_terms),
                "format": "json",
                "h": 1000,
                "f": 0,
            }
            resp = _request_with_retries(self._session, url, params=params, timeout=30)
            resp.raise_for_status()
            time.sleep(self.request_delay_s)
            payload = resp.json()
            self._cache_store(cache_key, payload)

        hits = payload.get("result", {}).get("hits", {})
        total = int(hits.get("@total", 0))
        sent = int(hits.get("@sent", 0))
        if total > sent:
            raise RuntimeError(
                f"DBLP returned {sent}/{total} hits for {toc.bht} — bump 'h' parameter."
            )

        for hit in hits.get("hit", []):
            info = hit.get("info", {})
            # Defensive filter: PACMPL TOCs cover multiple venues, so the
            # query already restricts by ``number``; verify anyway.
            if toc.pacmpl_number is not None:
                if info.get("number") != toc.pacmpl_number:
                    continue
            else:
                # Conf-style TOCs sometimes include the editor record as a
                # ``Editorship`` hit; drop those.
                if info.get("type") == "Editorship":
                    continue
            yield info

    def _dblp_toc_cache_key(self, toc: TOCEntry) -> str:
        bht_safe = _safe_filename(toc.bht)
        suffix = toc.pacmpl_number or "main"
        return f"dblp_toc/{bht_safe}.{suffix}.json"

    # ------------------------------------------------------------------
    # Paper assembly
    # ------------------------------------------------------------------

    def _build_paper(self, entry: dict[str, Any], doi: str) -> dict[str, Any] | None:
        """Combine a DBLP entry with OpenAlex (or Semantic Scholar fallback).

        Returns ``None`` if no abstract can be obtained.
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

        if oa_authors:
            authors = oa_authors
        else:
            authors = _dblp_authors(entry)

        date = publication_date or self._fallback_date()
        link = _doi_link(doi)

        return {
            "paper_id": doi,
            "title": title,
            "abstract": abstract,
            "date": date,
            "link": link,
            "conference_name": self.venue_spec.label,
            "authors": authors,
            "dblp_key": entry.get("key"),
            "venue": self.venue,
            "year": self.year,
        }

    def _fallback_date(self) -> str:
        # When OpenAlex doesn't tell us the publication date, default to
        # Jan-1 of the volume year — stable, sortable, and within the right
        # year for downstream date filters.
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
            resp = _request_with_retries(self._session, url, params=params, timeout=30)
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
            resp = _request_with_retries(self._session, url, params=params, timeout=30)
        except requests.RequestException as exc:
            logger.warning("Semantic Scholar request failed for %s: %s", doi, exc)
            return None
        time.sleep(self.request_delay_s)
        if resp.status_code == 404:
            self._cache_store(cache_key, {})
            return None
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
        raw = [raw]
    out: list[dict[str, str]] = []
    for author in raw:
        text = (author.get("text") or "").strip()
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


def _doi_link(doi: str) -> str:
    """Return a public landing-page URL for the DOI.

    ACM, Springer, LIPIcs, and others all resolve through ``doi.org``;
    keeping the redirect there is more durable than guessing publishers.
    """
    return f"https://doi.org/{doi}"


# Re-export so external callers don't need to know the parsing details.
__all__ = [
    "VENUES",
    "VenueSpec",
    "TOCEntry",
    "PLVenueIndex",
    "PLConferenceHarvester",
]


# Suppress "imported but unused" for stdlib ET — kept available for tests
# that may want to validate the index XML if DBLP changes its schema.
_ = ET


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Harvest a PL conference proceedings into the scraped JSON shape."
    )
    parser.add_argument(
        "venues",
        nargs="*",
        help=(
            "Venue slugs to harvest. Default: all known venues "
            f"({', '.join(sorted(VENUES))})."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Single year to harvest. Default: every year DBLP indexes.",
    )
    parser.add_argument(
        "--year-min",
        type=int,
        default=None,
        help="Minimum year (inclusive). Ignored when --year is set.",
    )
    parser.add_argument(
        "--year-max",
        type=int,
        default=None,
        help="Maximum year (inclusive). Ignored when --year is set.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/pl_conferences",
    )
    parser.add_argument(
        "--cache-dir",
        default=".cache/pl_conferences",
    )
    parser.add_argument(
        "--skip-existing-doi",
        action="store_true",
        help="Skip DOIs already present in the oversight database.",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.1,
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    venues = [v.lower() for v in args.venues] if args.venues else list(VENUES)
    for v in venues:
        if v not in VENUES:
            parser.error(f"Unknown venue {v!r}; known: {sorted(VENUES)}")

    skip_doi: Callable[[str], bool] | None = None
    if args.skip_existing_doi:
        skip_doi = _make_db_doi_skipper()

    for venue in venues:
        spec = VENUES[venue]
        index = PLVenueIndex(
            spec,
            cache_dir=Path(args.cache_dir),
            request_delay_s=args.request_delay,
        )
        year_to_entries = dict(index.discover())
        years = sorted(year_to_entries.keys())
        if args.year is not None:
            years = [args.year] if args.year in year_to_entries else []
        else:
            if args.year_min is not None:
                years = [y for y in years if y >= args.year_min]
            if args.year_max is not None:
                years = [y for y in years if y <= args.year_max]
        logger.info(
            "Venue %s: %d years to harvest (%s)",
            spec.label,
            len(years),
            ", ".join(str(y) for y in years)
            if len(years) <= 10
            else f"{years[0]}–{years[-1]}",
        )
        for year in years:
            harvester = PLConferenceHarvester(
                venue=venue,
                year=year,
                output_dir=args.output_dir,
                cache_dir=args.cache_dir,
                request_delay_s=args.request_delay,
                skip_existing_doi=skip_doi,
                toc_entries=year_to_entries[year],
            )
            try:
                harvester.harvest()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to harvest %s %s; continuing", spec.label, year
                )


def _make_db_doi_skipper() -> Callable[[str], bool]:
    """Return a function that returns True for DOIs already in the DB."""
    from .PaperDatabase import PaperDatabase

    db = PaperDatabase()
    db.__enter__()
    cursor = db._get_con().cursor()
    cursor.execute(
        "SELECT paper_id FROM paper WHERE source != 'arxiv' AND paper_id LIKE '10.%'"
    )
    existing: set[str] = {row[0] for row in cursor.fetchall()}
    cursor.close()
    db.__exit__(None, None, None)
    logger.info("Loaded %d existing non-arxiv DOIs from DB", len(existing))
    return lambda doi: doi in existing


if __name__ == "__main__":
    _main()
