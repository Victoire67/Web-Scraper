"""Sequential and threaded page fetching with requests, for comparison with asyncio."""

import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import requests

from scraper.async_scraper import DEFAULT_CONCURRENCY, DEFAULT_TIMEOUT, FetchResult


def fetch_page_sync(url: str, timeout: float = DEFAULT_TIMEOUT) -> FetchResult:
    """Fetch one URL with a blocking request and never raise.

    Mirrors async_scraper.fetch_page so the three versions return the
    same results and can be compared fairly.
    """
    start = time.perf_counter()

    def elapsed() -> float:
        return round(time.perf_counter() - start, 3)

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return FetchResult(url=url, status=response.status_code, html=response.text, elapsed=elapsed())
    except requests.Timeout:
        return FetchResult(url=url, elapsed=elapsed(), error=f"Timed out after {timeout}s")
    except requests.HTTPError as e:
        status = e.response.status_code
        return FetchResult(url=url, status=status, elapsed=elapsed(), error=f"HTTP {status}")
    except requests.RequestException as e:
        return FetchResult(url=url, elapsed=elapsed(), error=f"{type(e).__name__}: {e}")


def fetch_all_sequential(
    urls: Iterable[str], timeout: float = DEFAULT_TIMEOUT
) -> list[FetchResult]:
    """Fetch URLs one after another: each request waits for the previous one."""
    return [fetch_page_sync(url, timeout) for url in urls]


def fetch_all_threaded(
    urls: Iterable[str],
    timeout: float = DEFAULT_TIMEOUT,
    workers: int = DEFAULT_CONCURRENCY,
) -> list[FetchResult]:
    """Fetch URLs in a pool of threads and return results in the same order.

    While one thread waits on the network, the others keep working. The
    GIL is released during socket I/O, so threads overlap their waiting.
    """
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(partial(fetch_page_sync, timeout=timeout), urls))
