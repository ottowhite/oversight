from __future__ import annotations
from attr import dataclass
import asyncio
from agentica.logging.loggers.stream_logger import StreamLogger
from agentica.logging import AgentListener
import argparse
from agentica import spawn


@dataclass
class SimplePaper:
    @dataclass
    class Author:
        name: str
        institution: str

    title: str
    authors: list[SimplePaper.Author]
    link: str


async def main() -> None:
    parser = argparse.ArgumentParser(description="Superscraper CLI")
    parser.add_argument("url", help="URL of the webpage to scrape")
    args = parser.parse_args()

    async def callback(chunk):
        print(chunk.content, end="", flush=True)

    agent = await spawn(
        premise="You are a web-scraping agent. You extract information from webpages with beautifulsoup, and return well-typed outputs.",
        model="openai:gpt-5.4",
        listener=lambda: AgentListener(StreamLogger(on_chunk=callback)),
    )

    papers: list[SimplePaper] = await agent.call(
        list[SimplePaper],
        "Scrape the webpage at the provided URL.",
        url=args.url,
        SimplePaper=SimplePaper,
        Author=SimplePaper.Author,
    )

    for paper in papers:
        print(paper.title)
        for author in paper.authors:
            print(f"  - {author.name} ({author.institution})")

        print()


def entrypoint() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    entrypoint()
