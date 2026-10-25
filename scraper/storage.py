"""Save scraped records to JSON with async file I/O."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles

DEFAULT_OUTPUT = Path("output") / "results.json"


def build_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap the records with a timestamp and success/failure counts."""
    failed = sum(1 for record in records if record["error"])
    return {
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_pages": len(records),
        "succeeded": len(records) - failed,
        "failed": failed,
        "pages": records,
    }


async def save_json(data: Any, path: Path = DEFAULT_OUTPUT) -> Path:
    """Write data as pretty-printed JSON, creating parent folders if needed.

    aiofiles runs the blocking disk write in a worker thread, so the event
    loop stays free while the file is written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, "w", encoding="utf-8") as file:
        await file.write(json.dumps(data, indent=2, ensure_ascii=False))
    return path
