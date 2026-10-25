"""Benchmark the async scraper against sequential and threaded versions.

Run with: python -m scraper.benchmark [--file benchmark_urls.txt]
"""

import argparse
import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scraper.async_scraper import DEFAULT_CONCURRENCY, DEFAULT_TIMEOUT, FetchResult, fetch_all
from scraper.sync_scraper import fetch_all_sequential, fetch_all_threaded
from scraper.url_loader import load_urls


@dataclass
class BenchmarkResult:
    name: str
    seconds: float
    succeeded: int
    total: int


def time_run(name: str, run: Callable[[], list[FetchResult]]) -> BenchmarkResult:
    """Run one fetching strategy and measure how long it takes."""
    print(f"Running {name}...")
    start = time.perf_counter()
    results = run()
    seconds = time.perf_counter() - start
    succeeded = sum(1 for result in results if result.ok)
    return BenchmarkResult(name, seconds, succeeded, len(results))


def format_table(results: list[BenchmarkResult]) -> str:
    """Return the results as a Markdown table, with speedup relative to the first row."""
    baseline = results[0].seconds
    lines = [
        "| Approach | Time (s) | Pages OK | Speedup vs sequential |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.name} | {r.seconds:.2f} | {r.succeeded}/{r.total} | {baseline / r.seconds:.1f}x |"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare sequential, threaded and async fetching")
    parser.add_argument(
        "-f", "--file", type=Path, default=Path("benchmark_urls.txt"),
        help="Text file with one URL per line (default: benchmark_urls.txt)",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"Seconds before giving up on a URL (default: {DEFAULT_TIMEOUT})",
    )
    parser.add_argument(
        "--concurrency", type=int, default=DEFAULT_CONCURRENCY,
        help=f"Threads / concurrent requests (default: {DEFAULT_CONCURRENCY})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    urls = list(load_urls(args.file))
    print(f"Benchmarking {len(urls)} URLs (concurrency {args.concurrency})\n")

    results = [
        time_run("Sequential (requests)", lambda: fetch_all_sequential(urls, args.timeout)),
        time_run(
            f"Threaded ({args.concurrency} threads)",
            lambda: fetch_all_threaded(urls, args.timeout, args.concurrency),
        ),
        time_run(
            "Async (asyncio + aiohttp)",
            lambda: asyncio.run(fetch_all(urls, args.timeout, args.concurrency)),
        ),
    ]
    print()
    print(format_table(results))


if __name__ == "__main__":
    main()
