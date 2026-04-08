from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Superscraper CLI")
    parser.add_argument("url", help="URL of the webpage to scrape")
    args = parser.parse_args()
    print(args.url)


if __name__ == "__main__":
    main()
