"""Asynchronous page fetching with aiohttp."""

import asyncio
import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass

import aiohttp

DEFAULT_TIMEOUT = 10.0
DEFAULT_CONCURRENCY = 10

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """The outcome of fetching one URL, whether it succeeded or failed."""

    url: str
    status: int | None = None
    html: str = ""
    elapsed: float = 0.0
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True if the page was fetched without any error."""
        return self.error is None

# The underscore before the download function means that this is an internal helper and that it can not be used outside of the module .


async def _download(session: aiohttp.ClientSession, url: str) -> tuple[int, str]:
    """Send a GET request and return the status code and body."""
    async with session.get(url) as response:
        response.raise_for_status()  # turns 4xx/5xx into an exception
        return response.status, await response.text()


async def fetch_page(
    session: aiohttp.ClientSession, url: str, timeout: float = DEFAULT_TIMEOUT
) -> FetchResult:
    """Fetch one URL and never raise: errors are recorded in the result.

    Returning errors instead of raising them means one bad URL can't crash
    a run that fetches many pages concurrently.
    """
    start = time.perf_counter()

    def elapsed() -> float:
        return round(time.perf_counter() - start, 3)

    try:
        status, html = await asyncio.wait_for(_download(session, url), timeout=timeout)
        return FetchResult(url=url, status=status, html=html, elapsed=elapsed())
    except TimeoutError:
        return FetchResult(url=url, elapsed=elapsed(), error=f"Timed out after {timeout}s")
    except aiohttp.ClientResponseError as e:
        return FetchResult(url=url, status=e.status, elapsed=elapsed(), error=f"HTTP {e.status}")
    except aiohttp.ClientError as e:
        return FetchResult(url=url, elapsed=elapsed(), error=f"{type(e).__name__}: {e}")


async def fetch_all(
    urls: Iterable[str],
    timeout: float = DEFAULT_TIMEOUT,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[FetchResult]:
    """Fetch many URLs concurrently and return results in the same order.

    A semaphore caps how many requests run at once, so we don't flood
    the servers or get blocked.
    """
    url_list = list(urls)
    semaphore = asyncio.Semaphore(concurrency)

    async def limited_fetch(session: aiohttp.ClientSession, url: str) -> FetchResult:
        async with semaphore:
            logger.info("START %s", url)
            result = await fetch_page(session, url, timeout)
            status = "DONE " if result.ok else "FAIL "
            logger.info("%s %s (%.2fs)", status, url, result.elapsed)
            return result

    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.create_task(limited_fetch(session, url))
                 for url in url_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # fetch_page shouldn't raise, but if something unexpected slips through,
    # record it as a failed result instead of crashing the whole run.
    return [
        result if isinstance(result, FetchResult)
        else FetchResult(url=url, error=f"Unexpected error: {result!r}")
        for url, result in zip(url_list, results)
    ]
