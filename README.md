# Async Web Scraper

Fetches many web pages concurrently with `asyncio` and `aiohttp`, extracts structured data (title, headings, links) with regular expressions, and saves the results as JSON. Sequential and threaded versions are included to compare performance against the async version.

## Features

- Concurrent HTTP requests with `aiohttp`, `asyncio.create_task()` and `asyncio.gather()`
- Per-request timeouts with `asyncio.wait_for()`
- A semaphore that caps how many requests run at once
- Async generators (`fetch_as_completed`, `extract_records`) consumed with `async for`, so pages are processed as soon as they arrive
- `@retry` (exponential backoff, transient errors only) and `@rate_limit` decorators for async functions
- Regex extraction, with `map` and `filter` for the transformations
- JSON output written with `aiofiles`, with paths handled by `pathlib`
- Sequential (`requests`) and threaded (`ThreadPoolExecutor`) versions, plus a benchmark script

## Project structure

```
Web-Scraper/
├── main.py                  # Entry point: python main.py
├── urls.txt                 # 24 URLs, including deliberate failures
├── benchmark_urls.txt       # 20 reliable URLs used by the benchmark
├── scraper/
│   ├── async_scraper.py     # fetch_page, fetch_all (gather), fetch_as_completed (async generator)
│   ├── decorators.py        # @retry and @rate_limit for async functions
│   ├── extractor.py         # Regex extraction with map/filter, extract_records (async generator)
│   ├── storage.py           # Async JSON writing with aiofiles + pathlib
│   ├── url_loader.py        # Generator that reads URLs from a file lazily
│   ├── sync_scraper.py      # Sequential and threaded versions (requests)
│   ├── benchmark.py         # Times sequential vs threaded vs async
│   └── main.py              # Command-line interface and pipeline
├── tests/                   # pytest suite, all HTTP calls mocked
└── output/
    └── sample_output.json   # Example output from a real run
```

## Setup

Requires **Python 3.11+**.

```bash
git clone https://github.com/Victoire67/Web-Scraper.git
cd Web-Scraper

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

If you use Poetry, run `poetry install` instead.

## Usage

Scrape every URL in `urls.txt` and save the results to `output/results.json`:

```bash
python main.py
```

Other options:

```bash
python main.py https://quotes.toscrape.com/ https://books.toscrape.com/   # specific URLs
python main.py --file my_urls.txt --output output/my_results.json
python main.py --timeout 5 --concurrency 20
```

| Option | Default | Description |
|---|---|---|
| `urls` | — | URLs to fetch. If none are given, they are read from `--file` |
| `-f`, `--file` | `urls.txt` | Text file with one URL per line (`#` starts a comment) |
| `-o`, `--output` | `output/results.json` | Where to write the JSON results |
| `--timeout` | `10` | Seconds before giving up on one URL |
| `--concurrency` | `10` | Maximum number of requests running at the same time |

The log shows requests overlapping. Ten requests start within milliseconds of each other (the concurrency limit), before the first one finishes, and results arrive in completion order:

```
22:59:41.319  START https://quotes.toscrape.com/page/1/
22:59:41.324  START https://quotes.toscrape.com/page/2/
22:59:41.324  START https://quotes.toscrape.com/page/3/
22:59:41.324  START https://quotes.toscrape.com/page/4/
...
22:59:42.561  DONE  https://quotes.toscrape.com/page/1/ (1.24s)
...
23:00:05.002  RETRY _download failed (TimeoutError), attempt 2/3, waiting 1.00s
23:00:16.016  FAIL  https://httpbin.org/delay/15 (31.54s)

FAILED  https://httpbin.org/status/404  ->  HTTP 404
FAILED  https://this-site-does-not-exist-12345.com  ->  ClientConnectorDNSError: ...
FAILED  https://httpbin.org/status/500  ->  HTTP 500
FAILED  https://httpbin.org/delay/15  ->  Timed out after 10.0s

20/24 pages fetched in 34.70s (slowest single page: 31.54s)
Results saved to output\results.json
```

The four failures are deliberate. They test error handling: a 404 (not retried), a 500 and a timeout (retried 3 times with backoff), and a domain that doesn't exist. Here the total time is set by the timeout URL's retries (3 × 10s), not by the 20 successful pages.

## How asyncio works in this project

**Coroutines and the event loop.** A function defined with `async def` is a *coroutine function*. Calling it doesn't run it; it returns a coroutine object. The **event loop**, started by `asyncio.run()` in `scraper/main.py`, runs coroutines. When a coroutine reaches `await` on something slow, such as a network response, it pauses and hands control back to the loop. The loop then runs another coroutine that is ready. A regular function, by contrast, blocks the whole thread until it returns.

**Why this suits scraping.** Fetching a page is I/O-bound: almost all the time is spent waiting for the server. While one request waits, the event loop sends and receives others. One thread can keep many requests in flight without the overhead of creating threads.

**Tasks and gather.** `fetch_all` wraps each URL's coroutine in `asyncio.create_task()`, which schedules it on the loop right away. It then waits for all of them with `asyncio.gather()`, which returns results in the same order as the input. An `asyncio.Semaphore` limits how many tasks are downloading at once, so the target servers aren't flooded.

**Timeouts.** Each request is wrapped in `asyncio.wait_for(..., timeout)`, so a server that never answers raises `TimeoutError` instead of hanging the run.

**Async generators.** `fetch_as_completed` is an `async def` function that uses `yield`, which makes it an *async generator*. It uses `asyncio.as_completed()` to yield each result as soon as it's ready, fastest first. `extract_records` is a second async generator that consumes the first with `async for` and turns each result into a record. Chained together, they form a pipeline: pages are parsed while slower pages are still downloading. The URL file is read the same way, through a regular generator (`load_urls`).

**Decorators on async functions.** `@retry` and `@rate_limit` in `scraper/decorators.py` return an `async def` wrapper that `await`s the original function. Both are applied to the low-level `_download` function:

```python
@retry(attempts=3, delay=0.5, retry_if=is_transient_error)   # outer: each retry...
@rate_limit(calls_per_second=10)                               # ...also waits for the rate limit
async def _download(session, url, timeout): ...
```

`@retry` only retries errors that might succeed on a second try (timeouts, connection errors, 5xx, 429), waiting longer after each failure. `@rate_limit` uses an `asyncio.Lock` so that all concurrent calls share one limit.

**Async file I/O.** `aiofiles` runs the disk write in a worker thread, so writing the JSON doesn't block the event loop.

## Performance comparison

`scraper/benchmark.py` fetches the same 20 pages (`benchmark_urls.txt`) in three ways:

| Approach | How it works |
|---|---|
| **Sequential** | `requests.get` in a loop. Each request waits for the previous one to finish |
| **Threaded** | `requests.get` in a `ThreadPoolExecutor` with 10 threads. The GIL is released while a thread waits on a socket, so threads overlap their waiting |
| **Async** | `fetch_all`: one thread, one event loop, up to 10 concurrent `aiohttp` requests |

Run it with:

```bash
python -m scraper.benchmark
```

### Benchmark results

Three runs on 2026-10-25, Windows 11, Python 3.14, home internet connection:

| Approach | Run 1 (s) | Run 2 (s) | Run 3 (s) | Average (s) | Speedup vs sequential |
|---|---|---|---|---|---|
| Sequential (requests) | 30.11 | 30.54 | 29.81 | 30.15 | 1.0x |
| Threaded (10 threads) | 3.40 | 3.52 | 3.04 | 3.32 | 9.1x |
| Async (asyncio + aiohttp) | 3.71 | 3.80 | 3.68 | 3.73 | 8.1x |

All 20 pages succeeded in every run.

### What the results show

- **Concurrency is what matters for I/O-bound work.** Each page takes about 1.5 seconds to load, mostly waiting on the network. Sequential spends ~30s waiting on one page at a time. Both concurrent versions overlap that waiting and finish about 8–9x faster. That is close to the theoretical limit with 10 requests at a time.
- **Threaded and async are close at this scale.** With only 20 URLs and 10 workers, both versions spend nearly all their time waiting on the same network. The async version is slightly slower here because it does extra work the others don't: `@rate_limit` spaces request starts 0.1s apart (so the 20th request can't start before ~1.9s), and every request goes through the `@retry` wrapper. Those are deliberate safety features for scraping real sites.
- **Async scales better.** Every thread has its own stack and is scheduled by the operating system, so thousands of threads become expensive. Async tasks are lightweight objects in a single thread, so the async version can handle far more simultaneous connections with the same resources. It also avoids shared-state problems between threads, because code only switches tasks at an `await`.

## Sample JSON output

Generated with:

```bash
python main.py https://quotes.toscrape.com/page/1/ https://books.toscrape.com/catalogue/page-1.html https://httpbin.org/status/404 -o output/sample_output.json
```

Shortened below; the full file is [`output/sample_output.json`](output/sample_output.json).

```json
{
  "scraped_at": "2026-10-25T20:58:37+00:00",
  "total_pages": 3,
  "succeeded": 2,
  "failed": 1,
  "pages": [
    {
      "url": "https://quotes.toscrape.com/page/1/",
      "status": 200,
      "elapsed": 1.499,
      "error": null,
      "title": "Quotes to Scrape",
      "headings": ["Quotes to Scrape", "Top Ten tags"],
      "link_count": 49,
      "links": [
        "https://quotes.toscrape.com/",
        "https://quotes.toscrape.com/login",
        "https://quotes.toscrape.com/author/Albert-Einstein",
        "..."
      ]
    },
    {
      "url": "https://books.toscrape.com/catalogue/page-1.html",
      "status": 200,
      "elapsed": 1.865,
      "error": null,
      "title": "All products | Books to Scrape - Sandbox",
      "headings": ["All products", "A Light in the ...", "Tipping the Velvet", "..."],
      "link_count": 73,
      "links": ["https://books.toscrape.com/index.html", "..."]
    },
    {
      "url": "https://httpbin.org/status/404",
      "status": 404,
      "elapsed": 1.385,
      "error": "HTTP 404"
    }
  ]
}
```

Failed pages keep their URL, status and error message, so they stay visible in the output instead of disappearing.

## Testing

```bash
python -m pytest
```

The suite has 43 tests. All network calls are mocked (`aioresponses` for aiohttp, `monkeypatch` for requests), so the tests are fast and work offline. They cover:

- `fetch_page`: success, HTTP errors, timeouts, connection errors, retrying 5xx but not 404
- `fetch_all`: input order, concurrent execution, the concurrency limit, unexpected errors
- `fetch_as_completed`: completion order, error handling, cancelling pending downloads when the caller stops early
- `@retry` and `@rate_limit`: retrying until success, re-raising after the last attempt, not retrying rejected errors, spacing concurrent calls, validating arguments, keeping function metadata
- Regex extraction, `map`/`filter` link cleaning, and record building
- Async JSON writing, including creating folders and keeping non-ASCII text
- Sequential and threaded versions, plus the benchmark table
- An end-to-end run of the whole pipeline (fetch → extract → save)
