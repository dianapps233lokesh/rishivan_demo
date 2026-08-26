"""The MongoDB layer, and the promise that it can never break a reading.

Telemetry is a byproduct of answering a question. A byproduct that can fail the
thing it observes is worse than no telemetry at all, so most of this file is
about what happens when the cluster is absent, slow, or broken.

Nothing here touches the real Atlas cluster. `tests/conftest.py` disables it
autouse — after a full suite run wrote 34 documents into the production
`client_testing` collection, which is exactly the failure these tests exist to
make impossible.
"""

import pytest

from rishivan.config import _encode_mongo_userinfo
from rishivan.store import mongo

_REAL_CLIENT = mongo.client
"""Captured at import, which happens before the autouse fixture in
`tests/conftest.py` stubs `mongo.client` out. A test that wants the real
connection logic restores this one."""


# ==========================================================================
# The URI
# ==========================================================================


def test_a_password_with_a_reserved_character_is_encoded():
    """The real credential holds a `%`, and pymongo refuses it outright:
    `InvalidURI: Username and password must be escaped according to RFC
    3986`. Encoding here beats asking whoever pastes the secret to remember."""
    out = _encode_mongo_userinfo("mongodb+srv://user:pa%ss@host/?a=1")
    assert "pa%25ss" in out


def test_encoding_is_idempotent():
    """Encoding an encoded password doubles the escapes and produces
    credentials that authenticate against nothing."""
    once = _encode_mongo_userinfo("mongodb+srv://user:pa%ss@host/")
    assert _encode_mongo_userinfo(once) == once


def test_a_uri_without_credentials_passes_through():
    assert _encode_mongo_userinfo("mongodb://localhost:27017") == \
        "mongodb://localhost:27017"


def test_an_unrecognised_shape_is_handed_to_the_driver_unchanged():
    """Better a driver error naming the real problem than a mangled URI."""
    assert _encode_mongo_userinfo("not a uri") == "not a uri"


def test_the_query_string_survives():
    out = _encode_mongo_userinfo("mongodb+srv://u:p@host/?appName=Cluster0")
    assert out.endswith("?appName=Cluster0")


# ==========================================================================
# Absence
# ==========================================================================


def test_an_unconfigured_store_returns_nothing_rather_than_raising():
    assert mongo.client() is None
    assert mongo.turns() is None
    assert mongo.predictions() is None


def test_ping_is_false_when_unconfigured():
    assert mongo.ping() is False


def test_stats_are_empty_when_unconfigured():
    assert mongo.stats() == {}


def test_ensure_indexes_reports_failure_rather_than_raising():
    assert mongo.ensure_indexes() is False


def test_a_failed_connection_is_not_retried_every_request(monkeypatch):
    """A dead cluster must cost one connection attempt, not one per request.
    Three seconds each, on the request path, adds up fast."""
    monkeypatch.setattr(mongo, "is_configured", lambda: True)
    monkeypatch.setattr(mongo, "client", _REAL_CLIENT)
    attempts = []

    def boom(*a, **kw):
        attempts.append(1)
        raise RuntimeError("no route to host")

    monkeypatch.setattr("pymongo.MongoClient", boom)
    mongo.reset()
    try:
        assert mongo.client() is None
        assert mongo.client() is None
        assert len(attempts) == 1
    finally:
        mongo.reset()


def test_the_timeouts_are_short_enough_for_a_request_path():
    """A reader waiting thirty seconds for a telemetry write they cannot see
    is the worst outcome available."""
    assert mongo.SERVER_SELECTION_TIMEOUT_MS <= 5000
    assert mongo.CONNECT_TIMEOUT_MS <= 5000


# ==========================================================================
# Telemetry degrades, never fails
# ==========================================================================


def test_recording_a_turn_without_a_cluster_returns_false_quietly():
    from rishivan.store.telemetry import record_turn

    assert record_turn({"run_id": "r1"}) is False


def test_recording_an_answer_without_a_cluster_returns_false_quietly():
    from rishivan.store.telemetry import record_answer

    assert record_answer("r1", "some prose") is False


def test_reading_recent_turns_without_a_cluster_is_empty():
    from rishivan.store.telemetry import open_predictions, recent

    assert recent() == []
    assert open_predictions() == []


def test_a_write_failure_is_swallowed(monkeypatch):
    """A full disk or an expired cluster costs the telemetry, not the answer."""
    from rishivan.store import telemetry

    class _Boom:
        def update_one(self, *a, **kw):
            raise RuntimeError("cluster is over quota")

    monkeypatch.setattr(mongo, "turns", lambda: _Boom())
    assert telemetry.record_turn({"run_id": "r1"}) is False


def test_resolving_an_unknown_outcome_is_refused():
    from rishivan.store.telemetry import resolve

    with pytest.raises(ValueError):
        resolve("p1", outcome="sort of")
