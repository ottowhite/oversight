"""Registry of :class:`SourcePoller` instances driven by ``oversight sync``.

Adding a new source means adding one entry here and ensuring the new
poller class lives in its own module (``<Name>Poller.py`` per the
one-class-per-file convention).
"""

from __future__ import annotations

from .ArxivPoller import ArxivPoller
from .PLConfPoller import PLConfPoller
from .SourcePoller import SourcePoller, _NotImplementedPoller


def build_registry() -> dict[str, SourcePoller]:
    """Return a fresh ``{name: poller}`` mapping.

    Pollers are cheap to construct (no DB / network IO until methods
    are called), so we rebuild the registry per CLI invocation rather
    than carrying it as module state. Tests rely on this isolation.
    """
    pollers: list[SourcePoller] = [
        ArxivPoller(),
        PLConfPoller(),
        # ML and Systems pollers will replace these stubs in a follow-up
        # commit. They each have ~1k+ lines of harvester logic
        # (OpenReviewHarvester for ML; superscraper for Systems) that
        # don't yet expose a clean watermark API. Phase 3 brief asks us
        # to stage the migration to keep this PR reviewable.
        _NotImplementedPoller(
            "ml",
            "OpenReviewHarvester (NeurIPS/ICLR/ICML/MLSys) needs a watermark API.",
        ),
        _NotImplementedPoller(
            "systems",
            "superscraper (OSDI/SOSP/ASPLOS/ATC/NSDI/EuroSys/VLDB) is agentic and needs"
            " a non-interactive driver.",
        ),
    ]
    return {p.name: p for p in pollers}


__all__ = ["build_registry"]
