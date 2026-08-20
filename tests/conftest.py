"""Shared test fixtures.

The one thing here is `run_db`, and it exists because of a failure that only appeared in
the full suite. Two tests each called `asyncio.run()` against the module-level
`async_session_factory`, and the second died with

    RuntimeError: got Future attached to a different loop

`rishivan/db/session.py` builds one engine at import time, and its asyncpg connection pool
binds to whichever event loop first used it. `asyncio.run` creates a fresh loop per call
and closes it on exit, so the pooled connections outlive their loop and the next test
inherits corpses. Each test passed alone and the pair failed together, which is the worst
version of this bug -- it looks like flakiness rather than a defect.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from rishivan.db.session import async_session_factory, engine


def run_db(work: Callable[[Any], Awaitable[Any]]) -> Any:
    """Run one database coroutine in its own loop, disposing the pool afterwards.

    `work` receives an `AsyncSession`. Disposal is the whole point: it returns the
    connections before the loop closes, so the next `asyncio.run` starts clean.

    Raises whatever the work raises. Callers that must tolerate an absent database should
    catch and `pytest.skip` themselves, so a genuinely broken query is never mistaken for
    a missing server.
    """

    async def main() -> Any:
        try:
            async with async_session_factory() as session:
                return await work(session)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def skip_without_database(exc: BaseException) -> None:
    """Skip on a connection failure, re-raise anything else.

    The distinction matters: "no database in CI" is not a test failure, but an ambiguous
    column or a bad predicate is exactly what these tests exist to catch, and swallowing
    those would make the suite green while the query is broken in production.
    """
    name = type(exc).__name__
    message = str(exc)
    if (
        "Connect" in name
        or "OperationalError" in name
        or "does not exist" in message
        or "Name or service not known" in message
    ):
        pytest.skip(f"database unavailable: {name}")
    raise exc
