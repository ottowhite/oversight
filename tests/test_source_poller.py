"""Tests for the SourcePoller registry, watermarks, and sync CLI flags.

These tests deliberately avoid touching the real database or network.
We mock :class:`PaperDatabase` at the cursor level — the watermark
queries are simple enough that a fake cursor returning canned rows
covers the watermark logic without bringing up Postgres.

End-to-end "rows actually land" coverage is left to manual verification
per the Phase 3 plan ("the integration test is a user runs it").
"""

from __future__ import annotations

import io
import sys
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path

import pytest

# tests/ doesn't import from the installed package; mirror the existing
# test_author_extractor.py shim so we resolve src/oversight/*.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from oversight.ArxivPoller import ArxivPoller  # noqa: E402
from oversight.PLConfPoller import PLConfPoller  # noqa: E402
from oversight.source_registry import build_registry  # noqa: E402
from oversight.SourcePoller import (  # noqa: E402
    SourcePoller,
    SyncResult,
    _NotImplementedPoller,
)


# ----------------------------------------------------------------------
# Fakes
# ----------------------------------------------------------------------


class _FakeCursor:
    """Minimal cursor that returns a canned result for ``execute().fetchone()``
    and ``execute().fetchall()``. The execute call itself returns the
    cursor so chained calls work like psycopg.
    """

    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows = rows or []

    def execute(self, query: str, params: list | None = None) -> _FakeCursor:  # noqa: ARG002
        return self

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return list(self._rows)

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeDB:
    """Stand-in for PaperDatabase that hands out a fake cursor."""

    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows = rows or []

    def _get_con(self) -> _FakeDB:
        return self

    @contextmanager
    def cursor(self):
        yield _FakeCursor(self._rows)


# ----------------------------------------------------------------------
# Registry / protocol
# ----------------------------------------------------------------------


class TestRegistry:
    def test_build_registry_keys(self) -> None:
        reg = build_registry()
        assert set(reg.keys()) == {"arxiv", "pl", "ml", "systems"}

    def test_pollers_satisfy_protocol(self) -> None:
        reg = build_registry()
        for name, poller in reg.items():
            # runtime_checkable Protocol; can isinstance().
            assert isinstance(poller, SourcePoller), name
            assert poller.name == name

    def test_stub_pollers_raise(self) -> None:
        reg = build_registry()
        for name in ("ml", "systems"):
            poller = reg[name]
            assert isinstance(poller, _NotImplementedPoller)
            with pytest.raises(NotImplementedError):
                poller.fetch_and_insert(_FakeDB())  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Watermarks
# ----------------------------------------------------------------------


class TestArxivWatermark:
    def test_returns_max_update_date(self) -> None:
        poller = ArxivPoller()
        db = _FakeDB(rows=[(date(2026, 5, 8),)])
        assert poller.latest_in_db(db) == date(2026, 5, 8)  # type: ignore[arg-type]

    def test_empty_db_returns_none(self) -> None:
        poller = ArxivPoller()
        db = _FakeDB(rows=[(None,)])
        assert poller.latest_in_db(db) is None  # type: ignore[arg-type]

    def test_no_rows_at_all_returns_none(self) -> None:
        poller = ArxivPoller()
        db = _FakeDB(rows=[])
        assert poller.latest_in_db(db) is None  # type: ignore[arg-type]


class TestPLConfWatermark:
    def test_returns_max_across_venues(self) -> None:
        poller = PLConfPoller()
        # Single MAX(...) across all PL labels.
        db = _FakeDB(rows=[(date(2026, 1, 28),)])
        assert poller.latest_in_db(db) == date(2026, 1, 28)  # type: ignore[arg-type]

    def test_no_pl_papers_returns_none(self) -> None:
        poller = PLConfPoller()
        db = _FakeDB(rows=[(None,)])
        assert poller.latest_in_db(db) is None  # type: ignore[arg-type]

    def test_per_venue_breakdown(self) -> None:
        poller = PLConfPoller()
        rows = [
            ("POPL", date(2026, 1, 8)),
            ("PLDI", date(2025, 6, 10)),
            ("Haskell", date(2009, 1, 1)),
        ]
        db = _FakeDB(rows=rows)
        result = poller._per_venue_watermarks(db)  # type: ignore[arg-type]
        assert result["POPL"] == date(2026, 1, 8)
        assert result["PLDI"] == date(2025, 6, 10)
        assert result["Haskell"] == date(2009, 1, 1)
        # Venues with no rows default to None
        assert result["ICFP"] is None
        assert result["OOPSLA"] is None


# ----------------------------------------------------------------------
# CLI flag parsing
# ----------------------------------------------------------------------


class TestSyncCLI:
    """Smoke-test the argparse plumbing for ``oversight sync``.

    We don't instantiate a real DB — every poller is stubbed with a
    MagicMock so the CLI's branching is tested in isolation.
    """

    def _run_cli(self, argv: list[str]) -> tuple[int | None, str, str, str]:
        """Return ``(rc, stdout, stderr, exit_message)``.

        ``exit_message`` is the string passed to ``SystemExit(...)`` when
        applicable — Python only writes that to stderr when the
        SystemExit propagates uncaught, so we surface it explicitly.
        """
        from oversight import cli

        out = io.StringIO()
        err = io.StringIO()
        old_argv = sys.argv
        rc: int | None = 0
        exit_message = ""
        try:
            sys.argv = ["oversight", *argv]
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    cli.main()
                except SystemExit as exc:
                    code = exc.code
                    if isinstance(code, int):
                        rc = code
                    elif code is None:
                        rc = 0
                    else:
                        rc = 1
                        exit_message = str(code)
        finally:
            sys.argv = old_argv
        return rc, out.getvalue(), err.getvalue(), exit_message

    def test_unknown_source_errors(self) -> None:
        rc, _, _, msg = self._run_cli(
            ["sync", "--sources", "definitely-not-a-source", "--dry-run"]
        )
        assert rc != 0
        assert "Unknown source" in msg

    def test_backfill_without_sources_errors(self) -> None:
        rc, _, _, msg = self._run_cli(["sync", "--backfill", "--dry-run"])
        assert rc != 0
        assert "--backfill requires --sources" in msg

    def test_dry_run_invokes_each_poller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Replace the registry with two trivial pollers and confirm the
        # CLI calls fetch_and_insert on each.
        from oversight import cli, source_registry

        called: list[tuple[str, bool, bool]] = []

        class _Stub:
            def __init__(self, name: str) -> None:
                self.name = name

            def latest_in_db(self, db: object) -> None:  # noqa: ARG002
                return None

            def fetch_and_insert(
                self,
                db: object,  # noqa: ARG002
                *,
                backfill: bool = False,
                dry_run: bool = False,
            ) -> SyncResult:
                called.append((self.name, backfill, dry_run))
                return SyncResult(self.name, 0, 0, 0, note="stub")

        def _fake_registry() -> dict[str, object]:
            return {"arxiv": _Stub("arxiv"), "pl": _Stub("pl")}

        monkeypatch.setattr(source_registry, "build_registry", _fake_registry)
        monkeypatch.setattr(cli, "PaperDatabase", None, raising=False)

        # Inject a fake PaperDatabase via module so cmd_sync's local
        # import resolves to our stub. Easiest is to monkeypatch the
        # module attribute on PaperDatabase.PaperDatabase itself.
        import oversight.PaperDatabase as pd_mod

        class _NoOpDB:
            def __enter__(self) -> _NoOpDB:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        monkeypatch.setattr(pd_mod, "PaperDatabase", _NoOpDB)

        rc, out, _, _ = self._run_cli(["sync", "--dry-run"])
        assert rc == 0, out
        names = [c[0] for c in called]
        assert names == ["arxiv", "pl"]
        # Both calls receive dry_run=True, backfill=False.
        assert all(dr is True and bf is False for _, bf, dr in called)
