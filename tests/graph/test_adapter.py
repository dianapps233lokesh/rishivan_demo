"""The contract `streamlit_app.py` and `tests/eval/run_eval.py` depend on.

Phase 1 is behaviour-preserving, so this is the test that says so. The classifier
is a model call, so it is stubbed here - what is under test is the adapter's
contract, not the model's judgement.
"""

import inspect

import pytest

from rishivan.council.domains import QueryDomain
from rishivan.graph.state import RESULT_KEYS


@pytest.fixture
def stub_models(monkeypatch):
    """Stub the two model calls the graph makes on a small-talk turn."""
    from rishivan.council import classifier, warmth

    monkeypatch.setattr(
        classifier, "classify_query",
        lambda client, question, **kw: {
            "is_smalltalk_or_gibberish": True,
            "primary_rishi": "vyom",
            "query_domain": QueryDomain.GENERAL,
        },
    )
    monkeypatch.setattr(
        warmth, "respond_warmly",
        lambda client, question, **kw: iter(["Hello — good to see you."]),
    )


def consult(**kw):
    from rishivan.council.orchestrator import council_consult

    return council_consult(None, None, kw.pop("question", "hello"), **kw)


class TestContract:
    def test_the_signature_is_unchanged(self):
        from rishivan.council.orchestrator import council_consult

        params = list(inspect.signature(council_consult).parameters)
        assert params[:3] == ["client", "store", "question"]
        for kw in ("rishi_override", "birth_data", "query_time", "target_time",
                   "lat", "lon", "tz_offset", "place", "conversation"):
            assert kw in params, kw

    def test_every_promised_key_is_returned(self, stub_models):
        result = consult()
        missing = RESULT_KEYS - set(result)
        assert not missing, f"dropped from the contract: {sorted(missing)}"

    def test_it_returns_a_plain_dict(self, stub_models):
        assert isinstance(consult(), dict)


class TestSmallTalk:
    def test_it_streams_without_a_store(self, stub_models):
        """The cheapest end-to-end path, and the one that proves the graph
        runs: no chart, no embeddings, no retrieval."""
        result = consult(question="hello")
        assert result["is_warmth"] is True
        assert "".join(result["answer_stream"]).strip()

    def test_it_carries_a_rishi_and_a_title(self, stub_models):
        result = consult(question="hello")
        assert result["primary_rishi"]
        assert result["rishi_title"]


class TestNoBranchingLeftBehind:
    def test_the_orchestrator_no_longer_branches_on_business_logic(self):
        """The point of the phase. `council_consult` becomes an adapter; if it
        grows conditionals again, the graph is being bypassed."""
        from rishivan.council.orchestrator import council_consult

        source = inspect.getsource(council_consult)
        body = source.split('"""', 2)[-1]
        assert body.count("if ") <= 2, "business branching belongs on edges now"

    def test_the_adapter_is_short(self):
        """A 564-line function became a graph. If this creeps back up, the
        nodes are being worked around rather than extended."""
        from rishivan.council.orchestrator import council_consult

        lines = inspect.getsource(council_consult).splitlines()
        assert len(lines) < 80, f"adapter is {len(lines)} lines"
