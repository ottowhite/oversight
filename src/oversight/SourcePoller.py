"""Unified source-poller protocol for ``oversight sync``.

Each ingestion source (arxiv, PL conferences, ML conferences, systems
conferences) implements :class:`SourcePoller`. The :class:`oversight sync
<oversight.cli.cmd_sync>` command iterates over a registry of pollers and
asks each one to fetch new rows since its watermark, or — for
``--backfill`` — its full back-catalogue.

A poller is intentionally thin: it owns

1. the ``name`` it advertises on the CLI (``--sources arxiv,pl``),
2. how to read the per-source watermark from the database, and
3. how to drive its underlying harvester to insert new rows.

Embedding is *not* a poller concern; the CLI runs a single embedding
pass after every poller has finished writing rows.

See ``docs/pl-conferences-plan.md`` § "Source registry + unified sync".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .PaperDatabase import PaperDatabase


@dataclass(frozen=True)
class SyncResult:
    """Outcome of running one poller. Reported by the CLI summary."""

    source: str
    """Poller name, e.g. ``"arxiv"`` or ``"pl"``."""

    inserted: int
    """Rows newly inserted into the ``paper`` table."""

    updated: int
    """Existing rows updated with newer content."""

    skipped: int
    """Rows skipped (already up-to-date)."""

    note: str | None = None
    """Optional human-readable note (e.g. ``"dry-run"``)."""


@runtime_checkable
class SourcePoller(Protocol):
    """A single ingestion source that can be polled incrementally.

    Implementations are constructed cheaply (no DB / network IO in
    ``__init__``) so the CLI can build the registry up-front and then
    call methods only on the subset the user actually requested.
    """

    name: str
    """Stable, lowercase identifier used on the CLI (``--sources``).

    Must be unique across the registry.
    """

    def latest_in_db(self, db: PaperDatabase) -> date | None:
        """Return the watermark — newest paper from this source already
        in the DB — or ``None`` if no rows for this source exist yet.

        This is used to decide what ``fetch_since`` should pull. A poller
        whose source spans multiple DB ``source`` values (e.g. PL with
        eight venues) returns the maximum across all of them.
        """
        ...

    def fetch_and_insert(
        self,
        db: PaperDatabase,
        *,
        backfill: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        """Drive the underlying harvester end-to-end.

        - If ``backfill`` is ``True``, ignore the watermark and re-pull
          the full back-catalogue. Used by ``oversight sync --backfill``.
        - If ``dry_run`` is ``True``, perform whatever read-only probing
          is cheap (e.g. compute the watermark, count expected new rows)
          without inserting anything; return a :class:`SyncResult` with
          ``inserted == updated == 0`` and a populated ``note``.

        Implementations should be defensive: a single poller failure must
        not crash the whole sync. The CLI catches and logs exceptions
        from this method.
        """
        ...


class _NotImplementedPoller:
    """Stub used by the registry for sources whose poller has not yet
    been migrated to the unified pipeline (ML, systems).

    Calling :meth:`fetch_and_insert` raises so accidental ``oversight
    sync --sources ml`` fails loudly rather than silently no-oping.
    """

    def __init__(self, name: str, reason: str) -> None:
        self.name = name
        self._reason = reason

    def latest_in_db(self, db: PaperDatabase) -> date | None:  # noqa: ARG002
        return None

    def fetch_and_insert(
        self,
        db: PaperDatabase,  # noqa: ARG002
        *,
        backfill: bool = False,  # noqa: ARG002
        dry_run: bool = False,  # noqa: ARG002
    ) -> SyncResult:
        raise NotImplementedError(
            f"Poller {self.name!r} is not yet migrated to the unified sync. "
            f"{self._reason} (See docs/pl-conferences-plan.md Phase 3.)"
        )


__all__ = [
    "SourcePoller",
    "SyncResult",
    "_NotImplementedPoller",
]
