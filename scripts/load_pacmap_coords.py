"""Load PaCMAP (or other 2D-projection) coordinates from a CSV into the
``paper_projection_2d`` table.

Expected CSV columns: ``paper_id, title, source, update_date, x, y``.
Only ``paper_id``, ``x``, ``y`` are stored; the rest are joined from the
``paper`` table at query time.

Usage:
    uv run python scripts/load_pacmap_coords.py \\
        --csv /tmp/pacmap_pl.csv \\
        --projection pacmap_pl_v1

Re-running with the same ``--projection`` updates existing rows
(``ON CONFLICT (paper_id, projection) DO UPDATE``). Pass a new projection
name to load a different run alongside without overwriting.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Iterator

import psycopg
from dotenv import load_dotenv


def _iter_rows(csv_path: str) -> Iterator[tuple[str, float, float]]:
    """Yield ``(paper_id, x, y)`` tuples from the CSV, one row at a time."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"paper_id", "x", "y"}
        missing = required - set(reader.fieldnames or [])
        assert not missing, f"CSV missing required columns: {sorted(missing)}"
        for row in reader:
            pid = row["paper_id"].strip()
            if not pid:
                continue
            try:
                x = float(row["x"])
                y = float(row["y"])
            except (TypeError, ValueError):
                # Skip malformed rows but keep going — a single NaN shouldn't
                # abort a 940k-row load.
                print(f"skipping row with bad x/y: paper_id={pid!r}", file=sys.stderr)
                continue
            yield pid, x, y


def load_coords(
    csv_path: str,
    projection: str,
    *,
    batch_size: int = 5000,
) -> tuple[int, int]:
    """Stream ``csv_path`` into ``paper_projection_2d`` and return
    ``(rows_read, rows_upserted)``.

    Rows whose ``paper_id`` is absent from ``paper`` are silently dropped by
    the foreign-key constraint via a pre-filter SELECT; we do that filter
    in batches to keep memory bounded for the full 940k load.
    """
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    assert database_url is not None, "DATABASE_URL is not set"

    rows_read = 0
    rows_upserted = 0
    with psycopg.connect(database_url) as con:
        # autocommit=False so the whole load is one transaction — if the
        # script dies halfway through, we don't end up with a partial
        # projection.
        con.autocommit = False
        with con.cursor() as cur:
            batch: list[tuple[str, str, float, float]] = []
            for pid, x, y in _iter_rows(csv_path):
                rows_read += 1
                batch.append((pid, projection, x, y))
                if len(batch) >= batch_size:
                    rows_upserted += _flush(cur, batch)
                    batch.clear()
                    if rows_read % (batch_size * 4) == 0:
                        print(f"  ...read={rows_read} upserted={rows_upserted}")
            if batch:
                rows_upserted += _flush(cur, batch)
        con.commit()
    return rows_read, rows_upserted


def _flush(
    cur: psycopg.Cursor, batch: list[tuple[str, str, float, float]]
) -> int:
    """Upsert a batch and return the rowcount the server reported."""
    # ON CONFLICT (paper_id, projection) so a re-run with the same projection
    # name updates in-place rather than failing. Rows whose paper_id doesn't
    # exist in `paper` will raise a foreign-key violation, so we filter
    # those out client-side via a single round-trip per batch.
    ids = [row[0] for row in batch]
    existing = {
        pid
        for (pid,) in cur.execute(
            "SELECT paper_id FROM paper WHERE paper_id = ANY(%s)",
            [ids],
        ).fetchall()
    }
    filtered = [row for row in batch if row[0] in existing]
    if not filtered:
        return 0
    cur.executemany(
        """
        INSERT INTO paper_projection_2d (paper_id, projection, x, y)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (paper_id, projection)
        DO UPDATE SET x = EXCLUDED.x, y = EXCLUDED.y, created_at = CURRENT_TIMESTAMP
        """,
        filtered,
    )
    return len(filtered)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, help="Path to the coords CSV")
    parser.add_argument(
        "--projection",
        required=True,
        help="Projection name (e.g. 'pacmap_pl_v1', 'pacmap_v1')",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Rows per upsert batch (default: 5000)",
    )
    args = parser.parse_args()

    print(f"Loading {args.csv} into projection={args.projection!r}...")
    rows_read, rows_upserted = load_coords(
        args.csv, args.projection, batch_size=args.batch_size
    )
    skipped = rows_read - rows_upserted
    print(
        f"Done. rows_read={rows_read} rows_upserted={rows_upserted} "
        f"rows_skipped_no_paper_match={skipped}"
    )


if __name__ == "__main__":
    main()
