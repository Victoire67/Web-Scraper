"""Decorators that add retry and rate-limiting behaviour to async functions."""

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

AsyncFunc = Callable[..., Awaitable[Any]]


def retry(
    attempts: int = 3,
    delay: float = 0.5,
    backoff: float = 2.0,
    retry_if: Callable[[Exception], bool] = lambda error: True,
) -> Callable[[AsyncFunc], AsyncFunc]:
    """Retry an async function when it raises an exception.

    Args:
        attempts: Total number of tries, including the first one.
        delay: Seconds to wait before the first retry.
        backoff: Multiply the delay by this after each failure (exponential backoff).
        retry_if: Decides whether an error is worth retrying. Errors it rejects
            are raised immediately.
    """
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    def decorator(func: AsyncFunc) -> AsyncFunc:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            current_delay = delay
            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as error:
                    if attempt == attempts or not retry_if(error):
                        raise
                    logger.warning(
                        "RETRY %s failed (%s), attempt %d/%d, waiting %.2fs",
                        func.__name__, type(error).__name__, attempt, attempts, current_delay,
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

        return wrapper

    return decorator


def rate_limit(calls_per_second: float) -> Callable[[AsyncFunc], AsyncFunc]:
    """Make sure calls to an async function start at least 1/calls_per_second apart.

    Every call to the decorated function shares one limit, even when many
    run concurrently with asyncio.gather.
    """
    if calls_per_second <= 0:
        raise ValueError("calls_per_second must be positive")
    min_interval = 1.0 / calls_per_second

    def decorator(func: AsyncFunc) -> AsyncFunc:
        # Shared by every call. A new event loop (each asyncio.run, or each
        # test) gets a fresh lock, because an asyncio.Lock belongs to one loop.
        state: dict[str, Any] = {"loop": None, "lock": None, "last_call": 0.0}

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            loop = asyncio.get_running_loop()
            if state["loop"] is not loop:
                state.update(loop=loop, lock=asyncio.Lock(), last_call=0.0)

            async with state["lock"]:
                while (wait := state["last_call"] + min_interval - time.perf_counter()) > 0:
                    await asyncio.sleep(wait)
                state["last_call"] = time.perf_counter()

            return await func(*args, **kwargs)

        return wrapper

    return decorator