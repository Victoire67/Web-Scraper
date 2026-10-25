"""End-to-end test of the scraping pipeline, with all HTTP calls mocked."""

import json

from aioresponses import aioresponses

from scraper.main import main


async def test_main_fetches_extracts_and_saves_in_input_order(tmp_path):
    urls = ["https://example.com/a", "https://example.com/b", "https://example.com/c"]
    output = tmp_path / "results.json"

    with aioresponses() as mocked:
        mocked.get(urls[0], status=200, body="<title>A</title><a href='/b'>b</a>")
        mocked.get(urls[1], status=404)
        mocked.get(urls[2], status=200, body="<title>C</title><h1>Hello</h1>")
        await main(urls, timeout=5, concurrency=3, output=output)

    report = json.loads(output.read_text(encoding="utf-8"))
    assert [page["url"] for page in report["pages"]] == urls
    assert report["succeeded"] == 2
    assert report["failed"] == 1
    assert report["pages"][0]["links"] == ["https://example.com/b"]
    assert report["pages"][1]["error"] == "HTTP 404"
    assert report["pages"][2]["headings"] == ["Hello"]
