"""MongoDB Atlas, for telemetry.

**Nothing in here may take down a reading.** Telemetry is a byproduct of
answering a question, and a byproduct that can fail the thing it observes is
worse than no telemetry. So every entry point returns `None` or `False` rather
than raising, connection is lazy, and the timeouts are short enough that an
unreachable cluster costs a request a second rather than thirty.

**Three things about Atlas specifically, all learned the hard way here:**

  * **The URI's password must be percent-encoded.** The real one holds a `%`
    and pymongo refused it outright - `InvalidURI: Username and password must
    be escaped according to RFC 3986`. `config.MONGODB_URI` encodes it.
  * **TLS needs an explicit CA bundle.** A stock macOS Python has no root
    certificates and every connection dies with `CERTIFICATE_VERIFY_FAILED`.
    `certifi` is passed as `tlsCAFile` always, which is also correct in a
    container that happens to have its own.
  * **The free tier is 512 MB and gives no warning before it fills.** Writes
    just start failing. Hence the TTL index, and hence `slim.py` - a raw trace
    measured 222 KB, which is roughly 2,300 turns before the cluster is full.

The client is a module-level singleton. `MongoClient` owns a connection pool
and is designed to be shared; building one per request exhausts the free
tier's connection limit long before its disk.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

SERVER_SELECTION_TIMEOUT_MS = 3000
"""Short on purpose. This runs on the request path, and a reader waiting
thirty seconds for a telemetry write they cannot see is the worst outcome
available. Three seconds is enough for a warm Atlas cluster and short enough
that a dead one is barely noticeable."""

CONNECT_TIMEOUT_MS = 3000
SOCKET_TIMEOUT_MS = 5000

_client: Any = None
_lock = threading.Lock()
_failed = False
"""Set after a failed connection attempt so a dead cluster is not retried on
every single request. Cleared only by `reset()`."""


def is_configured() -> bool:
    from rishivan.config import settings

    return settings.has_mongo


def reset() -> None:
    """Drop the cached client. For tests, and for a credential change."""
    global _client, _failed
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:  # noqa: BLE001
                pass
        _client = None
        _failed = False


def client() -> Optional[Any]:
    """The shared client, or None if Mongo is not configured or not reachable."""
    global _client, _failed
    if _failed or not is_configured():
        return None
    if _client is not None:
        return _client

    with _lock:
        if _client is not None:
            return _client
        try:
            import certifi
            from pymongo import MongoClient

            from rishivan.config import settings

            _client = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
                connectTimeoutMS=CONNECT_TIMEOUT_MS,
                socketTimeoutMS=SOCKET_TIMEOUT_MS,
                tls=True,
                tlsCAFile=certifi.where(),
                appname="rishivan-demo",
                retryWrites=True,
            )
        except Exception:  # noqa: BLE001
            logger.warning("could not build a MongoDB client", exc_info=True)
            _failed = True
            return None
    return _client


def database() -> Optional[Any]:
    conn = client()
    if conn is None:
        return None
    from rishivan.config import settings

    return conn[settings.MONGODB_DB_NAME]


def collection(name: str) -> Optional[Any]:
    db = database()
    return None if db is None else db[name]


def turns() -> Optional[Any]:
    """One document per answered turn."""
    from rishivan.config import settings

    return collection(settings.MONGODB_COLLECTION_NAME)


def predictions() -> Optional[Any]:
    """The prediction ledger."""
    from rishivan.config import settings

    return collection(settings.MONGODB_PREDICTIONS_COLLECTION)


def ping() -> bool:
    """Is the cluster actually reachable? Never raises."""
    conn = client()
    if conn is None:
        return False
    try:
        conn.admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        logger.warning("MongoDB ping failed", exc_info=True)
        return False


def ensure_indexes() -> bool:
    """Create the indexes and the TTL. Idempotent, and safe to call at startup.

    The TTL is the free tier's only real safeguard: 512 MB with no alarm before
    it fills, and writes that simply start failing. Expiring by age means the
    ceiling is reached on a schedule rather than as a surprise during a client
    demo.
    """
    from pymongo import ASCENDING, DESCENDING

    from rishivan.config import settings

    turn_docs, prediction_docs = turns(), predictions()
    if turn_docs is None or prediction_docs is None:
        return False

    try:
        turn_docs.create_index([("run_id", ASCENDING)], unique=True,
                               name="run_id_unique")
        turn_docs.create_index([("created_at", DESCENDING)], name="recent")
        turn_docs.create_index([("thread_id", ASCENDING),
                                ("created_at", ASCENDING)], name="conversation")
        turn_docs.create_index([("domain", ASCENDING)], name="by_domain")

        prediction_docs.create_index([("prediction_id", ASCENDING)],
                                     unique=True, name="prediction_id_unique")
        prediction_docs.create_index([("outcome", ASCENDING)], name="by_outcome")

        days = settings.MONGODB_RETENTION_DAYS
        if days > 0:
            turn_docs.create_index(
                [("created_at", ASCENDING)],
                expireAfterSeconds=days * 86400,
                name="ttl_created_at",
            )
            # Predictions deliberately have NO TTL. A prediction expiring
            # before its own window closes is a prediction that can never be
            # scored, which defeats the point of writing it down.
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not create MongoDB indexes", exc_info=True)
        return False


def stats() -> dict:
    """Size and counts, for the "how full is the free tier" question."""
    db = database()
    if db is None:
        return {}
    try:
        raw = db.command("dbstats")
        from rishivan.config import settings

        return {
            "data_mb": round(raw.get("dataSize", 0) / 1024 / 1024, 3),
            "storage_mb": round(raw.get("storageSize", 0) / 1024 / 1024, 3),
            "turns": db[settings.MONGODB_COLLECTION_NAME].estimated_document_count(),
            "predictions": db[
                settings.MONGODB_PREDICTIONS_COLLECTION
            ].estimated_document_count(),
        }
    except Exception:  # noqa: BLE001
        logger.warning("could not read MongoDB stats", exc_info=True)
        return {}
