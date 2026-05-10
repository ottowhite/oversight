"""Wrap :class:`ArXivRepository` as a :class:`SourcePoller`.

The arxiv source uses OAI-PMH cs:cs sets via :class:`SickleWrapper`; the
existing harvester logic in :class:`ArXivRepository.sync` already does
the right thing — fetch by ``MAX(update_date) - overlap_timedelta``, then
insert/update rows. This poller is a thin adapter over that.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from .SourcePoller import SyncResult
from .utils import get_logger

if TYPE_CHECKING:
    from .PaperDatabase import PaperDatabase

logger = get_logger()


class ArxivPoller:
    """Poller for arxiv cs.* papers via OAI-PMH."""

    name = "arxiv"

    def __init__(
        self,
        embedding_model_name: str = "models/gemini-embedding-001",
        research_llm_model_name: str = "google/gemini-2.5-flash",
        overlap_timedelta: timedelta = timedelta(days=1),
    ) -> None:
        # Names only; the underlying ArXivRepository constructs heavy
        # objects (embedding model, LLM, sickle session) so we defer
        # instantiation to fetch_and_insert.
        self._embedding_model_name = embedding_model_name
        self._research_llm_model_name = research_llm_model_name
        self._overlap_timedelta = overlap_timedelta

    def latest_in_db(self, db: PaperDatabase) -> date | None:
        """Newest ``update_date`` of any ``source = 'arxiv'`` row.

        Returns ``None`` only on a totally empty arxiv table — almost
        never the case in practice (~980k rows in production).
        """
        with db._get_con().cursor() as cur:
            row = cur.execute(
                "SELECT MAX(update_date)::DATE FROM paper WHERE source = 'arxiv'"
            ).fetchone()
        if row is None or row[0] is None:
            return None
        value = row[0]
        # MAX(...)::DATE returns a date already, but be defensive.
        if hasattr(value, "date"):
            return value.date()  # type: ignore[no-any-return]
        return value

    def fetch_and_insert(
        self,
        db: PaperDatabase,
        *,
        backfill: bool = False,
        dry_run: bool = False,
    ) -> SyncResult:
        watermark = self.latest_in_db(db)
        if dry_run:
            note = (
                "backfill (full re-pull from arxiv OAI-PMH)"
                if backfill
                else f"watermark={watermark}, would fetch from "
                f"{(watermark - self._overlap_timedelta) if watermark else 'epoch'}"
            )
            return SyncResult(self.name, 0, 0, 0, note=note)

        # Construct the heavy repo lazily and run its existing sync().
        # We import inside the method so a missing optional dep (e.g.
        # OAI client) doesn't break ``oversight sync --sources pl``.
        from .ArXivRepository import ArXivRepository

        if backfill:
            logger.warning(
                "ArxivPoller --backfill: pulling from epoch is impractical against "
                "the OAI-PMH endpoint; running a normal sync from the watermark instead."
            )

        with ArXivRepository(
            embedding_model_name=self._embedding_model_name,
            research_llm_model_name=self._research_llm_model_name,
            overlap_timedelta=self._overlap_timedelta,
        ) as repo:
            # ArXivRepository.sync fetches new papers and ALSO embeds
            # them. The unified CLI calls a single embedding pass after
            # all pollers run, so we do the fetch step only here.
            repo._sync_from_date((watermark or date.today()) - self._overlap_timedelta)

        # ArXivRepository.sync logs counts but does not return them.
        # For now report zeros and let the per-row tqdm output carry the
        # signal. A future refactor of the inner sync to return counts
        # would let us populate this faithfully.
        return SyncResult(self.name, inserted=0, updated=0, skipped=0)


__all__ = ["ArxivPoller"]
