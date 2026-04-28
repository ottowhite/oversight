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

    # oversight inventory
    sp_inventory = subparsers.add_parser(
        "inventory", help="Show paper counts and conferences"
    )
    sp_inventory.set_defaults(func=cmd_inventory)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
