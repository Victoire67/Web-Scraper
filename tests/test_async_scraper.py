"""Tests for scraper.async_scraper, with all HTTP calls mocked."""

import aiohttp
import pytest
from aioresponses import aioresponses

from scraper.async_scraper import FetchResult, fetch_page

URL = "https://example.com"


@pytest.fixture
async def session():
    """Give each test a fresh aiohttp session, closed automatically afterwards."""
    async with aiohttp.ClientSession() as s:
        yield s


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