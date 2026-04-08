from __future__ import annotations
from superscraper.tools.semantic_scholar import lookup_abstract_from_acm_link
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


async def main() -> None:
    parser = argparse.ArgumentParser(description="Superscraper CLI")
    parser.add_argument("--url", required=True, help="URL of the webpage to scrape")
    parser.add_argument(
        "--output-path", required=True, help="Output file path for scraped data"
    )
    args = parser.parse_args()

    async def callback(chunk):
        print(chunk.content, end="", flush=True)

    agent = await spawn(
        premise="You are a web-scraping agent. You extract information from webpages with beautifulsoup, and return well-typed outputs. You scrape the information that is available on the webpage, and retrieve missing information from other tools you have access to. Populate the uid field with the DOI if it's available on the page.",
        model="openai:gpt-5.4",
        listener=lambda: AgentListener(StreamLogger(on_chunk=callback)),
    )

    initial_papers: list[SimplePaper] = await agent.call(
        list[SimplePaper],
        "Scrape the webpage at the provided URL.",
        url=args.url,
        SimplePaper=SimplePaper,
        Author=SimplePaper.Author,
        lookup_abstract_from_acm_link=lookup_abstract_from_acm_link,
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
        f.write(json.dumps([asdict(paper) for paper in validated_papers], indent=2))


def entrypoint() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    entrypoint()
