"""Extract structured data from downloaded HTML with regular expressions."""

import re
from collections.abc import AsyncIterable, AsyncIterator
from functools import partial
from html import unescape
from typing import Any
from urllib.parse import urljoin

from scraper.async_scraper import FetchResult

TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
# \1 makes the closing tag match the opening one: <h2>...</h2>, not <h2>...</h3>.
HEADING_RE = re.compile(r"<h([1-3])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
LINK_RE = re.compile(r"<a\s[^>]*?href=[\"']([^\"']+)[\"']", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")

NON_WEB_PREFIXES = ("#", "mailto:", "javascript:", "tel:")


def clean_text(fragment: str) -> str:
    """Strip inner tags, decode entities like &amp; and collapse whitespace."""
    text = unescape(TAG_RE.sub("", fragment))
    return WHITESPACE_RE.sub(" ", text).strip()


def extract_title(html: str) -> str | None:
    """Return the text of the <title> tag, or None if the page has none."""
    match = TITLE_RE.search(html)
    return clean_text(match.group(1)) if match else None


def extract_headings(html: str) -> list[str]:
    """Return the text of every <h1>, <h2> and <h3>, skipping empty ones."""
    texts = map(clean_text, (match.group(2) for match in HEADING_RE.finditer(html)))
    return list(filter(None, texts))


def is_web_link(href: str) -> bool:
    """False for in-page anchors and mailto:/javascript:/tel: links."""
    return not href.strip().lower().startswith(NON_WEB_PREFIXES)


def extract_links(html: str, base_url: str) -> list[str]:
    """Return unique absolute links in page order.

    Relative links like "page-2.html" are resolved against the page URL.
    """
    hrefs = filter(is_web_link, LINK_RE.findall(html))
    absolute = map(partial(urljoin, base_url), map(str.strip, hrefs))
    return list(dict.fromkeys(absolute))  # removes duplicates, keeps order


def to_record(result: FetchResult) -> dict[str, Any]:
    """Turn a fetch result into a JSON-ready dictionary of extracted data."""
    record: dict[str, Any] = {
        "url": result.url,
        "status": result.status,
        "elapsed": result.elapsed,
        "error": result.error,
    }
    if result.ok:
        links = extract_links(result.html, result.url)
        record.update(
            title=extract_title(result.html),
            headings=extract_headings(result.html),
            link_count=len(links),
            links=links,
        )
    return record


async def extract_records(
    results: AsyncIterable[FetchResult],
) -> AsyncIterator[dict[str, Any]]:
    """Turn each fetch result into a record as soon as it arrives.

    Chained after fetch_as_completed, pages are parsed while slower
    pages are still downloading.
    """
    async for result in results:
        yield to_record(result)
