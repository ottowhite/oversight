from __future__ import annotations
import asyncio

import argparse
from agentica import spawn


async def main() -> None:
    parser = argparse.ArgumentParser(description="Superscraper CLI")
    parser.add_argument("url", help="URL of the webpage to scrape")
    args = parser.parse_args()
    print(args.url)

    agent = await spawn(
        premise="You are a helpful assistant.",
        model="openai:gpt-4.1",
    )

    response: int = await agent.call(int, "What is 5 + 5?")
    print(f"Agent's response: {response}")


def entrypoint() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    entrypoint()
