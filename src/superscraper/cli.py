from __future__ import annotations
from superscraper.tools.semantic_scholar import lookup_abstract_from_acm_link
import json
from attr import dataclass
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
    abstract: str | None
    link: str


async def main() -> None:
    parser = argparse.ArgumentParser(description="Superscraper CLI")
    parser.add_argument("url", help="URL of the webpage to scrape")
    args = parser.parse_args()

    async def callback(chunk):
        print(chunk.content, end="", flush=True)

    agent = await spawn(
        premise="You are a web-scraping agent. You extract information from webpages with beautifulsoup, and return well-typed outputs. You scrape the information that is available on the webpage, and retrieve missing information from other tools you have access to.",
        model="openai:gpt-5.4",
        listener=lambda: AgentListener(StreamLogger(on_chunk=callback)),
    )

    papers: list[SimplePaper] = await agent.call(
        list[SimplePaper],
        "Scrape the webpage at the provided URL.",
        url=args.url,
        SimplePaper=SimplePaper,
        Author=SimplePaper.Author,
        lookup_abstract_from_acm_link=lookup_abstract_from_acm_link,
    )

    for paper in papers:
        print(paper.title)
        for author in paper.authors:
            print(f"  - {author.first_name} {author.last_name} ({author.institution})")

        print()

    print(f"Found {len(papers)} papers.")

    # Save the ppaers
    with open("papers.json", "w") as f:
        json.dump([paper.__dict__ for paper in papers], f, indent=2)


def entrypoint() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    entrypoint()
