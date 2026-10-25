"""Load the list of URLs to scrape from a text file."""

from collections.abc import Iterator
from pathlib import Path


def load_urls(path: Path) -> Iterator[str]:
    """Yield one URL per line, skipping blank lines and # comments.

    A generator reads the file lazily, one line at a time, instead of
    loading everything into memory first.
    """
    with path.open(encoding="utf-8") as file:
        for line in file:
            url = line.strip()
            if url and not url.startswith("#"):
                yield url