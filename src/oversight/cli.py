from __future__ import annotations

import argparse
import os
from datetime import timedelta

from dotenv import load_dotenv
from psycopg import sql


def cmd_search(args: argparse.Namespace) -> None:
    from .PaperRepository import PaperRepository

    sources = [s.strip() for s in args.sources.split(",")] if args.sources else []

    with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
        filters: list[sql.Composable] = (
            [repo.build_filter_sql(sources)] if sources else []
        )
        papers = repo.get_newest_related_papers(
            args.query,
            timedelta(days=args.days),
            filters,
            limit=args.limit,
        )

    for paper in papers:
        print(paper)


def cmd_sync(args: argparse.Namespace) -> None:
    from .ArXivRepository import ArXivRepository

    with ArXivRepository(
        embedding_model_name="models/gemini-embedding-001",
        research_llm_model_name="google/gemini-2.5-flash",
    ) as repo:
        repo.sync()


def cmd_digest(args: argparse.Namespace) -> None:
    from .ArXivRepository import ArXivRepository
    from .ResearchListener import research_listener_group

    with ArXivRepository(
        embedding_model_name="models/gemini-embedding-001",
        research_llm_model_name="google/gemini-2.5-flash",
    ) as repo:
        if not args.no_sync:
            repo.sync()
        repo.email_weekly_digest(research_listener_group)


def cmd_serve(args: argparse.Namespace) -> None:
    from .flask_app import app

    port = args.port or int(os.getenv("FLASK_PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=args.debug)


def cmd_consume(args: argparse.Namespace) -> None:
    if args.dry_run:
        _consume_dry_run(args)
        return

    from .PaperRepository import PaperRepository

    is_dir = os.path.isdir(args.path)

    with PaperRepository(embedding_model_name="models/gemini-embedding-001") as repo:
        if args.format == "scraped":
            if is_dir:
                repo.add_scraped_papers_from_dir(args.path)
            else:
                repo.add_scraped_papers(args.path)
        else:
            api_version = 1 if args.format == "openreview-api-v1" else 2
            if is_dir:
                for filename in os.listdir(args.path):
                    repo.add_openreview_papers(
                        os.path.join(args.path, filename), api_version
                    )
            else:
                repo.add_openreview_papers(args.path, api_version)

        repo.embed_missing_conference_papers()


def _consume_dry_run(args: argparse.Namespace) -> None:
    import json

    from .Paper import Paper

    if os.path.isdir(args.path):
        paths = [os.path.join(args.path, f) for f in sorted(os.listdir(args.path))]
    else:
        paths = [args.path]

    total = 0
    for path in paths:
        with open(path, "r") as f:
            items = json.load(f)
        print(f"\n=== {path} ({len(items)} papers) ===")
        for item in items:
            if args.format == "scraped":
                paper = Paper.from_scraped_json(item)
            else:
                api_version = 1 if args.format == "openreview-api-v1" else 2
                paper = Paper.from_openreview_json(item, api_version)
            title = paper.title if len(paper.title) <= 80 else paper.title[:77] + "..."
            print(
                f"  [{paper.source}] {paper.paper_date.date()} {paper.paper_id}  "
                f"{title}  ({len(paper.authors)} authors, {len(paper.institutions)} institutions)"
            )
            total += 1

    print(f"\nDry run: {total} papers would be upserted (no DB writes performed).")


def cmd_projections(args: argparse.Namespace) -> None:
    """Compute a 2D PaCMAP projection of every embedded paper and upsert
    the coords into paper_projection_2d for the /atlas page.

    Pipeline (lifted verbatim from the original one-shot
    scripts/build_pacmap_coords.py — the same script that produced the
    in-prod /tmp/pacmap_all.csv that the old loader script ingested):

      1. Server-side-cursor stream of (paper_id, embedding) from
         Postgres into a pre-allocated float32 ndarray. The
         halfvec→vector cast in SQL is the load-bearing trick that
         lets pgvector-python decode straight into np.float32 instead
         of HalfVector wrappers.
      2. L2-normalize in place (avoids a 6 GB copy at full-corpus scale).
      3. PCA → 50 dimensions (PaCMAP is much faster from 50-d input than
         from raw 3072-d; the variance loss is negligible after L2
         normalize).
      4. PaCMAP → 2 dimensions with init="pca".
      5. Upsert (paper_id, projection, x, y) into paper_projection_2d
         under a single transaction so a crash mid-load doesn't leave
         the projection half-overwritten.

    The previous CSV intermediate (and the plotting + nearest-neighbour
    sanity-check from the original script) are dropped — the CLI is the
    cron-driven happy path and doesn't need diagnostic artefacts.
    """
    import time

    import numpy as np
    import pacmap
    import psycopg
    from pgvector.psycopg import register_vector
    from sklearn.decomposition import PCA

    database_url = os.getenv("DATABASE_URL")
    assert database_url is not None, "DATABASE_URL is not set"

    DIM = 3072
    ITERSIZE = 5000

    # Cast halfvec -> vector so pgvector-python decodes into np.float32
    # ndarray. The optional source filter mirrors the script's behaviour
    # (none by default = full corpus); two literal SQL strings rather
    # than an f-string so the query stays LiteralString-typed.
    count_sql_all = """
        SELECT count(*)
        FROM paper p
        JOIN embedding e ON e.paper_id = p.paper_id
        WHERE e.embedding_gemini_embedding_001 IS NOT NULL
    """
    count_sql_sources = """
        SELECT count(*)
        FROM paper p
        JOIN embedding e ON e.paper_id = p.paper_id
        WHERE e.embedding_gemini_embedding_001 IS NOT NULL
          AND p.source = ANY(%s)
    """
    stream_sql_all = """
        SELECT p.paper_id,
               e.embedding_gemini_embedding_001::vector AS emb
        FROM paper p
        JOIN embedding e ON e.paper_id = p.paper_id
        WHERE e.embedding_gemini_embedding_001 IS NOT NULL
    """
    stream_sql_sources = """
        SELECT p.paper_id,
               e.embedding_gemini_embedding_001::vector AS emb
        FROM paper p
        JOIN embedding e ON e.paper_id = p.paper_id
        WHERE e.embedding_gemini_embedding_001 IS NOT NULL
          AND p.source = ANY(%s)
    """
    if args.sources:
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        source_params: list = [sources]
    else:
        source_params = []

    t_total = time.time()
    print(f"[projections] connecting to DB (projection={args.name!r})...", flush=True)
    con = psycopg.connect(database_url)
    register_vector(con)

    with con.cursor() as cur:
        if args.sources:
            cur.execute(count_sql_sources, source_params)
        else:
            cur.execute(count_sql_all)
        row = cur.fetchone()
        n_rows = int(row[0]) if row is not None else 0
    print(f"[projections] rows to fetch: {n_rows}", flush=True)

    if n_rows == 0:
        print("[projections] no embeddings; nothing to project.")
        con.close()
        return

    # Pre-allocate float32 (N, 3072). For 524k rows this is ~6.4 GB.
    X = np.empty((n_rows, DIM), dtype=np.float32)
    paper_ids: list[str] = [""] * n_rows

    print("[projections] streaming embeddings...", flush=True)
    t_db = time.time()
    with con.cursor(name="proj_stream") as cur:
        cur.itersize = ITERSIZE
        if args.sources:
            cur.execute(stream_sql_sources, source_params)
        else:
            cur.execute(stream_sql_all)
        i = 0
        for pid, emb in cur:
            paper_ids[i] = pid
            X[i] = emb
            i += 1
            if i % 50000 == 0:
                elapsed = time.time() - t_db
                rate = i / max(elapsed, 1e-6)
                eta = (n_rows - i) / max(rate, 1e-6)
                print(
                    f"  streamed {i}/{n_rows} rate={rate:.0f}/s "
                    f"elapsed={elapsed:.1f}s eta={eta:.0f}s",
                    flush=True,
                )
    db_time = time.time() - t_db
    assert i == n_rows, f"streamed {i} but expected {n_rows}"
    print(f"[projections] DB stream done in {db_time:.1f}s", flush=True)
    con.close()

    # L2 normalize in place to avoid a 6 GB copy at full-corpus scale.
    print("[projections] L2-normalising in place...", flush=True)
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    zero_mask = (norms == 0).flatten()
    if zero_mask.any():
        print(
            f"  WARNING: {zero_mask.sum()} zero-norm rows; setting to 1.",
            flush=True,
        )
        norms[zero_mask] = 1.0
    np.divide(X, norms, out=X)
    del norms

    # PCA → 50 then PaCMAP → 2. PaCMAP from 50-d is much faster than from
    # raw 3072-d and PCA explains nearly all the variance after L2 norm.
    print("[projections] PCA→50...", flush=True)
    t_pca = time.time()
    pca = PCA(n_components=50, random_state=42)
    X50 = pca.fit_transform(X)
    print(
        f"[projections] PCA done in {time.time() - t_pca:.1f}s "
        f"(explained_variance_ratio_sum={pca.explained_variance_ratio_.sum():.4f})",
        flush=True,
    )
    del X

    print("[projections] PaCMAP→2...", flush=True)
    t_pm = time.time()
    reducer = pacmap.PaCMAP(
        n_components=2,
        n_neighbors=None,
        MN_ratio=0.5,
        FP_ratio=2.0,
        random_state=42,
        verbose=True,
    )
    X2 = reducer.fit_transform(X50, init="pca")
    print(f"[projections] PaCMAP done in {time.time() - t_pm:.1f}s", flush=True)
    del X50

    print(
        f"[projections] upserting {n_rows} coords into projection={args.name!r}...",
        flush=True,
    )
    with psycopg.connect(database_url) as con:
        # autocommit=False so a crash mid-load doesn't leave the
        # projection half-overwritten — the table flips atomically.
        con.autocommit = False
        with con.cursor() as cur:
            batch_size = 5000
            for i in range(0, n_rows, batch_size):
                end = min(i + batch_size, n_rows)
                rows = [
                    (paper_ids[j], args.name, float(X2[j, 0]), float(X2[j, 1]))
                    for j in range(i, end)
                ]
                cur.executemany(
                    """
                    INSERT INTO paper_projection_2d (paper_id, projection, x, y)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (paper_id, projection)
                    DO UPDATE SET
                        x = EXCLUDED.x,
                        y = EXCLUDED.y,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    rows,
                )
                if (i // batch_size) % 4 == 0:
                    print(f"  ...upserted {end:,}/{n_rows:,}")
        con.commit()

    print(
        f"[projections] done in {time.time() - t_total:.1f}s total "
        f"(projection={args.name!r} rows={n_rows:,}).",
        flush=True,
    )


def cmd_inventory(args: argparse.Namespace) -> None:
    from .PaperDatabase import PaperDatabase

    with PaperDatabase() as db:
        counts = db.count_papers_by_source()
        conferences = db.summarise_current_conferences()

    print(f"Total papers: {counts.pop('total', 0)}\n")
    for source, cnt in sorted(counts.items()):
        years = conferences.get(source, {})
        years_str = ", ".join(str(y) for y in sorted(years))
        print(f"  {source:<10} {cnt:>6} papers  [{years_str}]")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Oversight — academic paper search engine"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # oversight search
    sp_search = subparsers.add_parser("search", help="Search papers by similarity")
    sp_search.add_argument("query", help="Search query text")
    sp_search.add_argument(
        "--sources",
        help="Comma-separated sources to filter (e.g. arxiv,ICML,NeurIPS)",
    )
    sp_search.add_argument(
        "--days", type=int, default=365 * 5, help="Time window in days (default: 1825)"
    )
    sp_search.add_argument(
        "--limit", type=int, default=10, help="Max results (default: 10)"
    )
    sp_search.set_defaults(func=cmd_search)

    # oversight sync
    sp_sync = subparsers.add_parser("sync", help="Sync papers from ArXiv")
    sp_sync.set_defaults(func=cmd_sync)

    # oversight digest
    sp_digest = subparsers.add_parser("digest", help="Send weekly email digest")
    sp_digest.add_argument(
        "--no-sync", action="store_true", help="Skip syncing before sending digest"
    )
    sp_digest.set_defaults(func=cmd_digest)

    # oversight serve
    sp_serve = subparsers.add_parser("serve", help="Run the API server")
    sp_serve.add_argument("--port", type=int, help="Port to listen on (default: 5001)")
    sp_serve.add_argument(
        "--debug", action="store_true", help="Enable Flask debug mode"
    )
    sp_serve.set_defaults(func=cmd_serve)

    # oversight consume
    sp_consume = subparsers.add_parser(
        "consume", help="Load papers from a JSON file (or directory) into the database"
    )
    sp_consume.add_argument(
        "path", help="Path to a JSON file or directory of JSON files"
    )
    sp_consume.add_argument(
        "--format",
        choices=["scraped", "openreview-api-v1", "openreview-api-v2"],
        default="scraped",
        help="Input format (default: scraped)",
    )
    sp_consume.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print what would be inserted without writing to the database",
    )
    sp_consume.set_defaults(func=cmd_consume)

    # oversight projections
    sp_projections = subparsers.add_parser(
        "projections",
        help="Compute a 2D PaCMAP projection of embeddings for /atlas",
    )
    sp_projections.add_argument(
        "--name",
        default="pacmap_v1",
        help="Projection name written to paper_projection_2d (default: pacmap_v1)",
    )
    sp_projections.add_argument(
        "--sources",
        help="Optional comma-separated source filter (e.g. ICFP,POPL,PLDI for a "
        "PL-only projection). Defaults to all sources.",
    )
    sp_projections.set_defaults(func=cmd_projections)

    # oversight inventory
    sp_inventory = subparsers.add_parser(
        "inventory", help="Show paper counts and conferences"
    )
    sp_inventory.set_defaults(func=cmd_inventory)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
