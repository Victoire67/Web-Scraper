"""Command-line entry point for the async web scraper."""

import argparse
import asyncio

import aiohttp

from scraper.async_scraper import DEFAULT_TIMEOUT, fetch_page


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Async web scraper")
    parser.add_argument("url", help="The URL to fetch")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"Seconds before giving up (default: {DEFAULT_TIMEOUT})",
    )
    return parser.parse_args()


async def main(url: str, timeout: float) -> None:
    async with aiohttp.ClientSession() as session:
        result = await fetch_page(session, url, timeout=timeout)

    if result.ok:
        print(f"OK     {result.url}  status={result.status}  "
              f"{len(result.html)} chars  {result.elapsed}s")
    else:
        print(f"FAILED {result.url}  {result.error}  {result.elapsed}s")


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.url, args.timeout))