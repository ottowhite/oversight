from __future__ import annotations
from superscraper.tools.semantic_scholar import (
    lookup_abstract_from_acm_link,
    lookup_paper_by_name,
)
import json
from pathlib import Path
from attr import asdict, dataclass
import asyncio
from agentica.logging.loggers.stream_logger import StreamLogger
from agentica.logging import AgentListener
import argparse
from agentica import spawn
from semanticscholar.Paper import Paper as SemanticScholarPaper


@dataclass
class SimplePaper:
    @dataclass
    class Author:
        first_name: str
        last_name: str
        institution: str

    title: str
    authors: list[SimplePaper.Author]
    abstract: str
    link: str
    uid: str
    date: str
    conference_name: str


async def main() -> None:
    parser = argparse.ArgumentParser(description="Superscraper CLI")
    parser.add_argument("--url", required=True, help="URL of the webpage to scrape")
    parser.add_argument(
        "--output-path", required=True, help="Output file path for scraped data"
    )
    parser.add_argument("--date", required=True, help="Date of the conference")
    parser.add_argument(
        "--conference-name", required=True, help="Name of the conference"
    )
    args = parser.parse_args()

    async def callback(chunk):
        print(chunk.content, end="", flush=True)

    agent = await spawn(
        premise="You are a web-scraping agent. You extract information from webpages with beautifulsoup, and return well-typed outputs. You scrape the information that is available on the webpage, and retrieve missing information from other tools you have access to.",
        model="anthropic/claude-opus-4.6",
        listener=lambda: AgentListener(StreamLogger(on_chunk=callback)),
    )

    initial_papers: list[SimplePaper] = await agent.call(
        list[SimplePaper],
        "Scrape the webpage at the provided URL. Set the date field to the provided date (in YYYY-MM-DD format) and the conference_name field to the provided conference_name directly on all papers. Links and abstracts are not available on this page, so you can retrieve these by looking up on semantic scholar by paper name, and cross referencing the authors. Also note that there are two table formats as the morning schedules are single track, and the afternoon sessions are multi-track.",
        url=args.url,
        date=args.date,
        conference_name=args.conference_name,
        SimplePaper=SimplePaper,
        SemanticScholarPaper=SemanticScholarPaper,
        Author=SimplePaper.Author,
        lookup_abstract_from_acm_link=lookup_abstract_from_acm_link,
        lookup_paper_by_name=lookup_paper_by_name,
    )

    validated_papers: list[SimplePaper] = await agent.call(
        list[SimplePaper],
        "Validate all extracted information is correct, finding any issues with your previous approach. If you did do issues, adapt scrapers and re-generate the papers, validating that the issues are fixed across all papers.",
        SimplePaper=SimplePaper,
        Author=SimplePaper.Author,
        initial_papers=initial_papers,
    )

    for paper in validated_papers:
        print(f"{paper.title} ({paper.uid})")
        for author in paper.authors:
            print(f"  - {author.first_name} {author.last_name} ({author.institution})")
        print(
            f"  Abstract: {paper.abstract[:200]}..."
        )  # Print the first 200 characters of the abstract

        print()

    print(f"Found {len(validated_papers)} papers.")

    # Save the papers
    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        if output_path.suffix == ".json":
            f.write(json.dumps([asdict(paper) for paper in validated_papers], indent=2))
        elif output_path.suffix == ".txt":
            f.write(f"Found {len(validated_papers)} papers.\n\n")
            for paper in validated_papers:
                f.write(f"{paper.title} ({paper.uid})\n")
                for author in paper.authors:
                    f.write(
                        f"  - {author.first_name} {author.last_name} ({author.institution})\n"
                    )
                f.write(f"  Link: {paper.link}\n")
                f.write(f"  Abstract: {paper.abstract}\n\n")
        elif output_path.suffix == ".md":
            f.write(f"# {len(validated_papers)} Papers\n\n")
            for paper in validated_papers:
                f.write(f"## [{paper.title}]({paper.link})\n\n")
                f.write(f"**DOI:** `{paper.uid}`\n\n")
                f.write(f"**Authors:**\n\n")
                for author in paper.authors:
                    f.write(
                        f"- {author.first_name} {author.last_name} (*{author.institution}*)\n"
                    )
                f.write(f"\n**Abstract:**\n\n> {paper.abstract}\n\n---\n\n")
        else:
            raise ValueError(f"Unsupported output format: {output_path.suffix}")


def entrypoint() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    entrypoint()
