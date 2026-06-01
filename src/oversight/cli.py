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


def cmd_project(args: argparse.Namespace) -> None:
    """Fetch embeddings, run PaCMAP, upsert 2D coords for /atlas.

    Replaces the old scripts/load_pacmap_coords.py loader — there's no CSV
    intermediate any more, the embeddings are pulled directly from the DB
    and the resulting coords are written back in the same process.
    Designed to be run on a weekly cron (see scripts/install_sync_cron.sh)
    so the projection stays roughly fresh without manual intervention.
    """
    import numpy as np
    import psycopg
    from pacmap import PaCMAP
    from pgvector.psycopg import register_vector

    database_url = os.getenv("DATABASE_URL")
    assert database_url is not None, "DATABASE_URL is not set"

    # Two literal queries rather than an f-string built from clauses, so
    # the SQL is a LiteralString (psycopg's `execute` rejects arbitrary
    # `str` for safety — there's no user-injected interpolation here, but
    # ty enforces the contract uniformly).
    print(f"[project] fetching embeddings (projection={args.name!r})...")
    ids: list[str] = []
    vectors: list = []
    with psycopg.connect(database_url) as con:
        register_vector(con)
        with con.cursor() as cur:
            if args.sources:
                sources = [s.strip() for s in args.sources.split(",") if s.strip()]
                cur.execute(
                    """
                    SELECT p.paper_id, e.embedding_gemini_embedding_001
                    FROM paper AS p
                    JOIN embedding AS e ON e.paper_id = p.paper_id
                    WHERE e.embedding_gemini_embedding_001 IS NOT NULL
                      AND p.source = ANY(%s)
                    """,
                    [sources],
                )
            else:
                cur.execute(
                    """
                    SELECT p.paper_id, e.embedding_gemini_embedding_001
                    FROM paper AS p
                    JOIN embedding AS e ON e.paper_id = p.paper_id
                    WHERE e.embedding_gemini_embedding_001 IS NOT NULL
                    """
                )
            for paper_id, emb in cur:
                ids.append(paper_id)
                vectors.append(emb)

    if not ids:
        print("[project] no embeddings matched; nothing to project.")
        return

    print(f"[project] running PaCMAP on {len(ids):,} × 3072-d embeddings...")
    # PaCMAP needs contiguous float32; cast once and free the row list.
    embeddings = np.asarray(vectors, dtype=np.float32)
    del vectors
    reducer = PaCMAP(
        n_components=2,
        n_neighbors=args.n_neighbors,
        MN_ratio=0.5,
        FP_ratio=2.0,
        random_state=args.seed,
    )
    coords = reducer.fit_transform(embeddings)
    del embeddings

    print(f"[project] upserting {len(ids):,} coords into paper_projection_2d...")
    with psycopg.connect(database_url) as con:
        # autocommit=False so a crash mid-load doesn't leave the
        # projection half-overwritten — the table flips atomically.
        con.autocommit = False
        with con.cursor() as cur:
            batch_size = 5000
            written = 0
            for i in range(0, len(ids), batch_size):
                end = min(i + batch_size, len(ids))
                rows = [
                    (ids[j], args.name, float(coords[j, 0]), float(coords[j, 1]))
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
                written = end
                if (i // batch_size) % 4 == 0:
                    print(f"  ...upserted {written:,}/{len(ids):,}")
        con.commit()

    print(f"[project] done — projection={args.name!r} rows={len(ids):,}.")


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

    # oversight project
    sp_project = subparsers.add_parser(
        "project",
        help="Compute a 2D PaCMAP projection of embeddings for /atlas",
    )
    sp_project.add_argument(
        "--name",
        default="pacmap_v1",
        help="Projection name written to paper_projection_2d (default: pacmap_v1)",
    )
    sp_project.add_argument(
        "--sources",
        help="Optional comma-separated source filter (e.g. ICFP,POPL,PLDI for a "
        "PL-only projection). Defaults to all sources.",
    )
    sp_project.add_argument(
        "--n-neighbors",
        type=int,
        default=10,
        dest="n_neighbors",
        help="PaCMAP n_neighbors hyperparameter (default: 10)",
    )
    sp_project.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for PaCMAP — keep fixed for reproducible projections",
    )
    sp_project.set_defaults(func=cmd_project)

    # oversight inventory
    sp_inventory = subparsers.add_parser(
        "inventory", help="Show paper counts and conferences"
    )
    sp_inventory.set_defaults(func=cmd_inventory)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
