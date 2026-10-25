"""Asynchronous page fetching with aiohttp."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass

import aiohttp

from scraper.decorators import rate_limit, retry

DEFAULT_TIMEOUT = 10.0
DEFAULT_CONCURRENCY = 10
MAX_ATTEMPTS = 3
RETRY_DELAY = 0.5
RATE_LIMIT_PER_SECOND = 10

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


def is_transient_error(error: Exception) -> bool:
    """Return True for errors worth retrying.

    Timeouts, network problems, server errors (5xx) and "too many requests"
    (429) can succeed on a second try. Other 4xx errors, like 404, never will.
    """
    if isinstance(error, aiohttp.ClientResponseError):
        return error.status >= 500 or error.status == 429
    return isinstance(error, (aiohttp.ClientError, TimeoutError))


@retry(attempts=MAX_ATTEMPTS, delay=RETRY_DELAY, retry_if=is_transient_error)
@rate_limit(calls_per_second=RATE_LIMIT_PER_SECOND)
async def _download(
    session: aiohttp.ClientSession, url: str, timeout: float
) -> tuple[int, str]:
    """Send one GET request with a timeout and return the status code and body.

    Raises on failure so @retry can try again. Each attempt passes through
    @rate_limit, because retry is the outer decorator.
    """

    async def request() -> tuple[int, str]:
        async with session.get(url) as response:
            response.raise_for_status()  # turns 4xx/5xx into an exception
            return response.status, await response.text()

    return await asyncio.wait_for(request(), timeout=timeout)


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
        status, html = await _download(session, url, timeout)
        return FetchResult(url=url, status=status, html=html, elapsed=elapsed())
    except TimeoutError:
        return FetchResult(url=url, elapsed=elapsed(), error=f"Timed out after {timeout}s")
    except aiohttp.ClientResponseError as e:
        return FetchResult(url=url, status=e.status, elapsed=elapsed(), error=f"HTTP {e.status}")
    except aiohttp.ClientError as e:
        return FetchResult(url=url, elapsed=elapsed(), error=f"{type(e).__name__}: {e}")


async def _limited_fetch(
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    url: str,
    timeout: float,
) -> FetchResult:
    """Fetch one URL once the semaphore lets us in, logging start and end."""
    async with semaphore:
        logger.info("START %s", url)
        try:
            result = await fetch_page(session, url, timeout)
        except Exception as e:
            # fetch_page shouldn't raise, but if something unexpected slips
            # through, record it as a failed result instead of crashing the run.
            result = FetchResult(url=url, error=f"Unexpected error: {e!r}")
        status = "DONE " if result.ok else "FAIL "
        logger.info("%s %s (%.2fs)", status, url, result.elapsed)
        return result


async def fetch_all(
    urls: Iterable[str],
    timeout: float = DEFAULT_TIMEOUT,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[FetchResult]:
    """Fetch many URLs concurrently and return results in the same order.

    A semaphore caps how many requests run at once, so we don't flood
    the servers or get blocked.
    """
    semaphore = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(_limited_fetch(session, semaphore, url, timeout))
            for url in urls
        ]
        return await asyncio.gather(*tasks)


async def fetch_as_completed(
    urls: Iterable[str],
    timeout: float = DEFAULT_TIMEOUT,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> AsyncIterator[FetchResult]:
    """Fetch many URLs concurrently and yield each result as soon as it is ready.

    Unlike fetch_all, the caller doesn't wait for the slowest page: it can
    start processing fast pages with `async for` while slow ones are still
    downloading. Results arrive in completion order, not input order.
    """
    semaphore = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(_limited_fetch(session, semaphore, url, timeout))
            for url in urls
        ]
        try:
            for next_done in asyncio.as_completed(tasks):
                yield await next_done
        finally:
            # If the caller stops early, don't leave downloads running.
            for task in tasks:
                task.cancel()