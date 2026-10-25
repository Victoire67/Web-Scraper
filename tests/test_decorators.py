"""Tests for scraper.decorators."""

import asyncio
import time

import pytest

from scraper.decorators import rate_limit, retry


# ---------------------------------------------------------------------------
# retry
# ---------------------------------------------------------------------------


async def test_retry_succeeds_after_failures():
    calls = 0

    @retry(attempts=3, delay=0)
    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ValueError("temporary failure")
        return "ok"

    assert await flaky() == "ok"
    assert calls == 3


async def test_retry_reraises_after_last_attempt():
    calls = 0

    @retry(attempts=2, delay=0)
    async def always_fails():
        nonlocal calls
        calls += 1
        raise ValueError("permanent failure")

    with pytest.raises(ValueError, match="permanent failure"):
        await always_fails()
    assert calls == 2


async def test_retry_does_not_retry_rejected_errors():
    calls = 0

    @retry(attempts=3, delay=0, retry_if=lambda error: not isinstance(error, KeyError))
    async def fails_with_key_error():
        nonlocal calls
        calls += 1
        raise KeyError("not retryable")

    with pytest.raises(KeyError):
        await fails_with_key_error()
    assert calls == 1


async def test_retry_keeps_function_name_and_docstring():
    @retry(attempts=2, delay=0)
    async def my_function():
        """My docstring."""

    assert my_function.__name__ == "my_function"
    assert my_function.__doc__ == "My docstring."


def test_retry_rejects_invalid_attempts():
    with pytest.raises(ValueError):
        retry(attempts=0)


# ---------------------------------------------------------------------------
# rate_limit
# ---------------------------------------------------------------------------


async def test_rate_limit_spaces_concurrent_calls():
    call_times = []

    @rate_limit(calls_per_second=10)  # at least 0.1s apart
    async def record_time():
        call_times.append(time.perf_counter())

    await asyncio.gather(*(record_time() for _ in range(5)))

    gaps = [later - earlier for earlier, later in zip(call_times, call_times[1:])]
    assert len(gaps) == 4
    assert all(gap >= 0.095 for gap in gaps)


async def test_rate_limit_keeps_function_name():
    @rate_limit(calls_per_second=5)
    async def my_function():
        pass

    assert my_function.__name__ == "my_function"


def test_rate_limit_rejects_invalid_rate():
    with pytest.raises(ValueError):
        rate_limit(calls_per_second=0)