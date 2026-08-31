"""Shared test fixtures.

`run_db` exists because of a failure that only appeared in the full suite: two tests
each called `asyncio.run()` against the module-level `async_session_factory`, and the
second died with `RuntimeError: got Future attached to a different loop`.

`db/session.py` builds one engine at import time and its asyncpg pool binds to whichever
loop first used it, while `asyncio.run` creates and closes a fresh loop per call — so the
pooled connections outlive their loop. Each test passed alone and the pair failed
together, which reads as flakiness rather than a defect.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from rishivan.db.session import async_session_factory, engine


def run_db(work: Callable[[Any], Awaitable[Any]]) -> Any:
    """Run one database coroutine in its own loop, disposing the pool afterwards.

        `work` receives an `AsyncSession`. Disposal is the point: it returns the connections
        before the loop closes, so the next `asyncio.run` starts clean. Raises whatever the
        work raises — callers needing to tolerate an absent database should skip themselves.
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

        "No database in CI" is not a test failure, but an ambiguous column or a bad
        predicate is exactly what these tests exist to catch.
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


def pytest_addoption(parser):
    """`--golden-update` rewrites golden files instead of asserting against them.

    Registered here rather than beside the test that reads it: a
    `pytest_addoption` hook in a test module is silently ignored, and
    `config.getoption` then raises `ValueError: no option named` — which reads
    like the test is broken rather than the hook being in the wrong file.
    """
    parser.addoption(
        "--golden-update", action="store_true", default=False,
        help="rewrite golden files instead of asserting against them",
    )


@pytest.fixture(autouse=True)
def no_telemetry_writes(monkeypatch):
    """Keep the test suite out of the real MongoDB Atlas cluster.

    `persist_node`'s default sink picks MongoDB whenever credentials are
    present, and `.streamlit/secrets.toml` is present on a developer machine —
    so the first full run after wiring it up put **34 turns and 34 predictions
    into the production `client_testing` collection**, and took two minutes
    doing it over the network.

    A test that silently writes to a shared database is a test that corrupts
    the data somebody is about to demo from. Autouse, so it protects tests
    written later by someone who has never read this docstring.

    Tests that genuinely want the store patch it back themselves — see
    `tests/store/test_mongo.py`.
    """
    from rishivan.council.requirements import store
    from rishivan.store import mongo

    monkeypatch.setattr(mongo, "is_configured", lambda: False)
    monkeypatch.setattr(mongo, "client", lambda: None)

    # The requirements catalogue caches per PROCESS, not per test, so a cache
    # populated before this fixture applied would survive it and every later
    # test would silently assert against whatever is in Atlas today. Cleared on
    # the way in and the way out: the suite must describe the code, not the
    # cluster.
    store.reset()
    yield
    store.reset()
