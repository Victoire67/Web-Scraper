"""Tests for scraper.async_scraper, with all HTTP calls mocked."""

import asyncio
import time

import aiohttp
import pytest
from aioresponses import aioresponses

from scraper import async_scraper
from scraper.async_scraper import FetchResult, fetch_all, fetch_page

URL = "https://example.com"


@pytest.fixture
async def session():
    """Give each test a fresh aiohttp session, closed automatically afterwards."""
    async with aiohttp.ClientSession() as s:
        yield s


# ---------------------------------------------------------------------------
# fetch_page: fetching a single URL
# ---------------------------------------------------------------------------


async def test_fetch_page_success(session):
    with aioresponses() as mocked:
        mocked.get(URL, status=200, body="<title>Hello</title>")
        result = await fetch_page(session, URL)

    assert isinstance(result, FetchResult)
    assert result.ok
    assert result.status == 200
    assert "Hello" in result.html
    assert result.error is None


async def test_fetch_page_http_error(session):
    with aioresponses() as mocked:
        mocked.get(URL, status=404)
        result = await fetch_page(session, URL)

    assert not result.ok
    assert result.status == 404
    assert result.error == "HTTP 404"
    assert result.html == ""


async def test_fetch_page_timeout(session):
    with aioresponses() as mocked:
        mocked.get(URL, exception=TimeoutError())
        result = await fetch_page(session, URL, timeout=1)

    assert not result.ok
    assert result.status is None
    assert result.error == "Timed out after 1s"


async def test_fetch_page_connection_error(session):
    with aioresponses() as mocked:
        mocked.get(URL, exception=aiohttp.ClientConnectionError("refused"))
        result = await fetch_page(session, URL)

    assert not result.ok
    assert result.status is None
    assert "ClientConnectionError" in result.error


async def test_fetch_page_records_elapsed_time(session):
    with aioresponses() as mocked:
        mocked.get(URL, status=200, body="ok")
        result = await fetch_page(session, URL)

    assert result.elapsed >= 0


# ---------------------------------------------------------------------------
# fetch_all: fetching many URLs concurrently
# ---------------------------------------------------------------------------


async def test_fetch_all_keeps_order_and_mixes_results():
    urls = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    with aioresponses() as mocked:
        mocked.get(urls[0], status=200, body="a")
        mocked.get(urls[1], status=500)
        mocked.get(urls[2], status=200, body="c")
        results = await fetch_all(urls)

    assert [r.url for r in results] == urls
    assert [r.ok for r in results] == [True, False, True]


async def test_fetch_all_runs_concurrently(monkeypatch):
    async def fake_fetch_page(session, url, timeout):
        await asyncio.sleep(0.2)
        return FetchResult(url=url, status=200)

    monkeypatch.setattr(async_scraper, "fetch_page", fake_fetch_page)
    urls = [f"https://example.com/{i}" for i in range(10)]

    start = time.perf_counter()
    results = await fetch_all(urls, concurrency=10)
    elapsed = time.perf_counter() - start

    assert len(results) == 10
    assert elapsed < 1.0  # sequential would take 10 x 0.2 = 2 seconds


async def test_fetch_all_respects_concurrency_limit(monkeypatch):
    active = 0
    peak = 0

    async def fake_fetch_page(session, url, timeout):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return FetchResult(url=url, status=200)

    monkeypatch.setattr(async_scraper, "fetch_page", fake_fetch_page)
    urls = [f"https://example.com/{i}" for i in range(10)]

    await fetch_all(urls, concurrency=3)

    assert peak == 3


async def test_fetch_all_records_unexpected_errors(monkeypatch):
    async def broken_fetch_page(session, url, timeout):
        raise RuntimeError("boom")

    monkeypatch.setattr(async_scraper, "fetch_page", broken_fetch_page)
    results = await fetch_all(["https://example.com"])

    assert not results[0].ok
    assert "Unexpected error" in results[0].error