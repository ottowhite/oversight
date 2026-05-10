"""Wrap :class:`PLConferenceHarvester` as a :class:`SourcePoller`.

The PL source covers eight venues whose DB ``source`` values are the
labels in :data:`PLConferenceHarvester.VENUES`: POPL, PLDI, ICFP, OOPSLA,
ESOP, ECOOP, CC, Haskell.

For incremental sync we don't talk to OpenAlex/Semantic Scholar at all
unless DBLP advertises a new volume year for the venue. The DBLP venue
index is one HTTP call per venue (~80 KB XML), cached on disk, and
served from a CDN — well within the free-tier budget for a daily run.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from .PLConferenceHarvester import VENUES, PLConferenceHarvester, PLVenueIndex
from .SourcePoller import SyncResult
from .utils import get_logger

if TYPE_CHECKING:
    from .PaperDatabase import PaperDatabase

logger = get_logger()


class PLConfPoller:
    """Poller for the eight PL conferences listed in
    :data:`oversight.PLConferenceHarvester.VENUES`.
    """

    name = "pl"

    # Lower-case slug → DB ``source`` value (the human-facing label).
    # Mirrors VenueSpec.label so both stay in lock-step.
    SOURCE_LABELS: tuple[str, ...] = tuple(spec.label for spec in VENUES.values())

    def __init__(
        self,
        output_dir: str | Path = "data/pl_conferences",
        cache_dir: str | Path | None = ".cache/pl_conferences",
        max_workers: int = 16,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._max_workers = max_workers

    # ------------------------------------------------------------------
    # Watermark
    # ------------------------------------------------------------------

    def latest_in_db(self, db: PaperDatabase) -> date | None:
        """Newest ``update_date`` across any of the eight PL ``source`` values.

        We collapse the per-venue watermarks into a single value because
        the CLI currently treats each poller as one watermark; per-venue
        scoping happens inside ``fetch_and_insert``.
        """
        labels = self.SOURCE_LABELS
        if not labels:
            return None

        placeholders = ",".join(["%s"] * len(labels))
        query = (
            f"SELECT MAX(update_date)::DATE FROM paper WHERE source IN ({placeholders})"
        )
        with db._get_con().cursor() as cur:
            row = cur.execute(query, list(labels)).fetchone()
        if row is None or row[0] is None:
            return None
        value = row[0]
        if hasattr(value, "date"):
            return value.date()  # type: ignore[no-any-return]
        return value

    def _per_venue_watermarks(self, db: PaperDatabase) -> dict[str, date | None]:
        """Latest ``update_date`` per PL venue label (or None if absent)."""
        labels = self.SOURCE_LABELS
        placeholders = ",".join(["%s"] * len(labels))
        query = (
            f"SELECT source, MAX(update_date)::DATE FROM paper "
            f"WHERE source IN ({placeholders}) GROUP BY source"
        )
        out: dict[str, date | None] = {label: None for label in labels}
        with db._get_con().cursor() as cur:
            rows = cur.execute(query, list(labels)).fetchall()
        for src, d in rows:
            out[src] = d
        return out

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def fetch_and_insert(
        self,
        db: PaperDatabase,
        *,
        backfill: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        watermarks = self._per_venue_watermarks(db)

        # Decide which (venue, year) pairs to harvest.
        plan: list[tuple[str, int]] = []
        skipped_venues: list[str] = []
        for slug, spec in VENUES.items():
            try:
                index = PLVenueIndex(spec, cache_dir=self._cache_dir)
                year_to_entries = dict(index.discover())
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to discover DBLP index for %s; skipping venue", spec.label
                )
                skipped_venues.append(spec.label)
                continue

            if backfill:
                years = sorted(year_to_entries.keys())
            else:
                wm = watermarks.get(spec.label)
                # If we've never seen this venue, treat it as "everything
                # newer than today minus a year" — but only when not in
                # backfill. Realistically a missing venue means the user
                # should --backfill it once. Fall through to all years
                # ≥ wm.year so we don't pull the entire 1973– archive on
                # a routine sync.
                if wm is None:
                    skipped_venues.append(
                        f"{spec.label} (no rows; use --backfill --sources pl)"
                    )
                    continue
                years = [y for y in sorted(year_to_entries.keys()) if y >= wm.year]
            for year in years:
                plan.append((slug, year))

        if dry_run:
            note_parts = [f"{len(plan)} (venue, year) pairs to harvest"]
            if backfill:
                note_parts.append("backfill")
            else:
                wm_summary = ", ".join(
                    f"{lab}={wm}" for lab, wm in watermarks.items() if wm is not None
                )
                note_parts.append(f"watermarks: {wm_summary or '(none)'}")
            if skipped_venues:
                note_parts.append("skipped: " + "; ".join(skipped_venues))
            return SyncResult(self.name, 0, 0, 0, note="; ".join(note_parts))

        if not plan:
            return SyncResult(
                self.name,
                0,
                0,
                0,
                note="no (venue, year) pairs to harvest"
                + (f" — skipped {skipped_venues}" if skipped_venues else ""),
            )

        # Build a set of DOIs already in the DB once, so each harvester
        # doesn't re-query. Re-uses the same shape as
        # ``_make_db_doi_skipper`` in PLConferenceHarvester._main but
        # against our connection.
        with db._get_con().cursor() as cur:
            rows = cur.execute(
                "SELECT paper_id FROM paper "
                "WHERE source != 'arxiv' AND paper_id LIKE '10.%'"
            ).fetchall()
        existing_dois = {r[0] for r in rows}
        logger.info(
            "PLConfPoller: %d existing non-arxiv DOIs loaded (skip set)",
            len(existing_dois),
        )

        # Run harvesters sequentially. Each harvester writes
        # data/pl_conferences/<venue>/<year>.json then we feed those
        # JSONs into the DB. The harvester's internal concurrency
        # already saturates DBLP's polite throttle.
        from .PaperRepository import PaperRepository

        harvested_paths: list[Path] = []
        for slug, year in plan:
            try:
                # Reload the index entries for this year — discover() is
                # cached on disk so this is essentially free.
                spec = VENUES[slug]
                index = PLVenueIndex(spec, cache_dir=self._cache_dir)
                toc_entries = dict(index.discover()).get(year)
                if toc_entries is None:
                    logger.warning(
                        "DBLP index has no entries for %s %s; skipping",
                        spec.label,
                        year,
                    )
                    continue
                harvester = PLConferenceHarvester(
                    venue=slug,
                    year=year,
                    output_dir=self._output_dir,
                    cache_dir=self._cache_dir,
                    skip_existing_doi=lambda doi: doi in existing_dois,
                    toc_entries=toc_entries,
                    max_workers=self._max_workers,
                )
                path = harvester.harvest()
                if path is not None:
                    harvested_paths.append(path)
            except Exception:  # noqa: BLE001
                logger.exception("Failed to harvest %s %s; continuing", slug, year)

        if not harvested_paths:
            return SyncResult(
                self.name,
                0,
                0,
                0,
                note=f"harvested 0 JSON files across {len(plan)} (venue, year) pairs",
            )

        # Insert harvested JSONs into the DB. Don't run the embedding
        # pass here — the CLI runs it once after all pollers finish.
        with PaperRepository(
            embedding_model_name="models/gemini-embedding-001"
        ) as repo:
            for path in harvested_paths:
                repo.add_scraped_papers(str(path))

        return SyncResult(
            self.name,
            inserted=0,
            updated=0,
            skipped=0,
            note=(
                f"harvested {len(harvested_paths)} JSON file(s) "
                f"across {len(plan)} (venue, year) pairs"
            ),
        )


__all__ = ["PLConfPoller"]


# Suppress "imported but unused" warning for ``logging`` — kept available
# in case downstream tweaks need to construct a custom logger config.
_ = logging
