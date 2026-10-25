"""Tests for scraper.sync_scraper and scraper.benchmark, with requests mocked."""

import time

import pytest
import requests

from scraper import sync_scraper
from scraper.benchmark import BenchmarkResult, format_table
from scraper.sync_scraper import fetch_all_sequential, fetch_all_threaded, fetch_page_sync

URL = "https://example.com"


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


def fake_get(responses):
    """Build a requests.get replacement that returns or raises per URL."""
    def get(url, timeout):
        outcome = responses[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
    return get


# ---------------------------------------------------------------------------
# fetch_page_sync
# ---------------------------------------------------------------------------


def test_fetch_page_sync_success(monkeypatch):
    monkeypatch.setattr(sync_scraper.requests, "get", fake_get({URL: FakeResponse(200, "hello")}))
    result = fetch_page_sync(URL)

    assert result.ok
    assert result.status == 200
    assert result.html == "hello"


def test_fetch_page_sync_http_error(monkeypatch):
    monkeypatch.setattr(sync_scraper.requests, "get", fake_get({URL: FakeResponse(404)}))
    result = fetch_page_sync(URL)

    assert not result.ok
    assert result.status == 404
    assert result.error == "HTTP 404"


def test_fetch_page_sync_timeout(monkeypatch):
    monkeypatch.setattr(sync_scraper.requests, "get", fake_get({URL: requests.Timeout()}))
    result = fetch_page_sync(URL, timeout=2)

    assert not result.ok
    assert result.error == "Timed out after 2s"


def test_fetch_page_sync_connection_error(monkeypatch):
    monkeypatch.setattr(
        sync_scraper.requests, "get", fake_get({URL: requests.ConnectionError("refused")})
    )
    result = fetch_page_sync(URL)

    assert not result.ok
    assert "ConnectionError" in result.error


# ---------------------------------------------------------------------------
# sequential vs threaded
# ---------------------------------------------------------------------------


@pytest.fixture
def slow_get(monkeypatch):
    """Every request takes 0.1 seconds, like a slow network."""
    def get(url, timeout):
        time.sleep(0.1)
        return FakeResponse(200, url)

    monkeypatch.setattr(sync_scraper.requests, "get", get)


URLS = [f"https://example.com/{i}" for i in range(5)]


def test_fetch_all_sequential_keeps_order(slow_get):
    results = fetch_all_sequential(URLS)

    assert [r.url for r in results] == URLS
    assert all(r.ok for r in results)


def test_fetch_all_threaded_keeps_order_and_runs_in_parallel(slow_get):
    start = time.perf_counter()
    results = fetch_all_threaded(URLS, workers=5)
    elapsed = time.perf_counter() - start

    assert [r.url for r in results] == URLS
    assert elapsed < 0.4  # sequential would take 5 x 0.1 = 0.5 seconds


# ---------------------------------------------------------------------------
# benchmark table
# ---------------------------------------------------------------------------


def test_format_table_shows_speedup_relative_to_first_row():
    table = format_table([
        BenchmarkResult("Sequential", 10.0, 20, 20),
        BenchmarkResult("Async", 2.0, 19, 20),
    ])

    assert "| Sequential | 10.00 | 20/20 | 1.0x |" in table
    assert "| Async | 2.00 | 19/20 | 5.0x |" in table
