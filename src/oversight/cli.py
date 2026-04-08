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

    # oversight inventory
    sp_inventory = subparsers.add_parser(
        "inventory", help="Show paper counts and conferences"
    )
    sp_inventory.set_defaults(func=cmd_inventory)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
