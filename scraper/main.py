"""Command-line entry point for the async web scraper."""

import argparse
import asyncio
import logging
import time
from pathlib import Path

from scraper.async_scraper import (
    DEFAULT_CONCURRENCY,
    DEFAULT_TIMEOUT,
    FetchResult,
    fetch_as_completed,
)
from scraper.url_loader import load_urls


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Async web scraper")
    parser.add_argument(
        "urls", nargs="*",
        help="URLs to fetch. If none are given, they are read from --file.",
    )
    parser.add_argument(
        "-f", "--file", type=Path, default=Path("urls.txt"),
        help="Text file with one URL per line (default: urls.txt)",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"Seconds before giving up on a URL (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Maximum requests at the same time (default: {DEFAULT_CONCURRENCY})",
    )
    return parser.parse_args()


def print_summary(results: list[FetchResult], total_time: float) -> None:
    failed = [r for r in results if not r.ok]
    succeeded = len(results) - len(failed)

    print()
    for result in failed:
        print(f"FAILED  {result.url}  ->  {result.error}")

    slowest = max((r.elapsed for r in results), default=0)
    print(f"\n{succeeded}/{len(results)} pages fetched in {total_time:.2f}s "
          f"(slowest single page: {slowest:.2f}s)")


async def main(urls: list[str], timeout: float, concurrency: int) -> None:
    start = time.perf_counter()
    results = [
        result
        async for result in fetch_as_completed(urls, timeout=timeout, concurrency=concurrency)
    ]
    print_summary(results, time.perf_counter() - start)


def run() -> None:
    """Parse the command line and start the event loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d  %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args()
    urls = args.urls or list(load_urls(args.file))
    asyncio.run(main(urls, args.timeout, args.concurrency))


if __name__ == "__main__":
    run()