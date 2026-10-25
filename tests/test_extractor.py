"""Tests for scraper.extractor."""

from scraper.async_scraper import FetchResult
from scraper.extractor import (
    clean_text,
    extract_headings,
    extract_links,
    extract_records,
    extract_title,
    is_web_link,
    to_record,
)

PAGE = """
<html>
<head><title>  Books &amp; More </title></head>
<body>
  <h1>All <em>products</em></h1>
  <h2 class="sub">Fiction</h2>
  <h3></h3>
  <h4>Ignored heading</h4>
  <a href="page-2.html">next</a>
  <a class="x" href='/about/'>about</a>
  <a href="https://other.com/">other</a>
  <a href="page-2.html">next again</a>
  <a href="#top">top</a>
  <a href="mailto:me@example.com">mail</a>
</body>
</html>
"""
BASE_URL = "https://books.example.com/catalogue/page-1.html"


def test_clean_text_strips_tags_entities_and_whitespace():
    assert clean_text("  <b>Fish</b> &amp;\n  chips ") == "Fish & chips"


def test_extract_title():
    assert extract_title(PAGE) == "Books & More"


def test_extract_title_missing():
    assert extract_title("<p>no title here</p>") is None


def test_extract_headings_keeps_h1_to_h3_and_skips_empty():
    assert extract_headings(PAGE) == ["All products", "Fiction"]


def test_is_web_link():
    assert is_web_link("page-2.html")
    assert is_web_link("https://example.com")
    assert not is_web_link("#top")
    assert not is_web_link("mailto:me@example.com")
    assert not is_web_link("JavaScript:void(0)")


def test_extract_links_resolves_relative_and_removes_duplicates():
    assert extract_links(PAGE, BASE_URL) == [
        "https://books.example.com/catalogue/page-2.html",
        "https://books.example.com/about/",
        "https://other.com/",
    ]


def test_to_record_for_successful_page():
    record = to_record(FetchResult(url=BASE_URL, status=200, html=PAGE, elapsed=0.5))

    assert record["url"] == BASE_URL
    assert record["status"] == 200
    assert record["error"] is None
    assert record["title"] == "Books & More"
    assert record["headings"] == ["All products", "Fiction"]
    assert record["link_count"] == 3
    assert len(record["links"]) == 3


def test_to_record_for_failed_page_has_no_extracted_fields():
    record = to_record(FetchResult(url=BASE_URL, status=404, error="HTTP 404"))

    assert record == {"url": BASE_URL, "status": 404, "elapsed": 0.0, "error": "HTTP 404"}


async def test_extract_records_processes_an_async_stream():
    async def results():
        yield FetchResult(url="https://a.com", status=200, html="<title>A</title>")
        yield FetchResult(url="https://b.com", error="HTTP 500", status=500)

    records = [record async for record in extract_records(results())]

    assert [r["url"] for r in records] == ["https://a.com", "https://b.com"]
    assert records[0]["title"] == "A"
    assert "title" not in records[1]
