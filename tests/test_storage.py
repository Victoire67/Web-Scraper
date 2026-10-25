"""Tests for scraper.storage."""

import json

from scraper.storage import build_report, save_json

RECORDS = [
    {"url": "https://a.com", "status": 200, "elapsed": 0.1, "error": None, "title": "A"},
    {"url": "https://b.com", "status": 404, "elapsed": 0.2, "error": "HTTP 404"},
]


def test_build_report_counts_successes_and_failures():
    report = build_report(RECORDS)

    assert report["total_pages"] == 2
    assert report["succeeded"] == 1
    assert report["failed"] == 1
    assert report["pages"] == RECORDS
    assert "scraped_at" in report


async def test_save_json_creates_missing_folders_and_writes_valid_json(tmp_path):
    path = tmp_path / "nested" / "folder" / "results.json"

    returned = await save_json(build_report(RECORDS), path)

    assert returned == path
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["pages"] == RECORDS


async def test_save_json_keeps_non_ascii_characters(tmp_path):
    path = tmp_path / "results.json"

    await save_json({"title": "Café “quotes”"}, path)

    assert "Café “quotes”" in path.read_text(encoding="utf-8")
