"""The adapter's contract, on the direct path.

The default path's contract is covered by `test_adapter.py` and must not move;
one test here asserts that from the other side.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


class _Chunk:
    def __init__(self, text):
        self.text = text


class FakeModels:
    """Only the reading call. The classifier is stubbed at its own seam — see
    `stub_classifier` below."""

    def __init__(self):
        self.stream_prompts = []

    def generate_content_stream(self, **kwargs):
        self.stream_prompts.append(kwargs.get("contents"))
        yield _Chunk("Marriage is close.")


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture(autouse=True)
def stub_classifier(monkeypatch):
    """Stub the classifier at its own seam, not through a fake response body.

    `intake_node` does `from rishivan.council.classifier import classify_query`
    at call time, so patching the module attribute takes effect. Faking
    `client.models.generate_content` instead would mean encoding the
    classifier's JSON contract into this test — a second copy of a schema that
    lives somewhere else, and one that fails confusingly when that schema moves.
    """
    def fake_classify(client, question, model="", conversation=None):
        return {
            "query_domain": "natal",
            "intent": "reading",
            "is_smalltalk_or_gibberish": False,
            "primary_rishi": "medhan",
            "search_query": question,
            "stated_facts": [],
        }

    monkeypatch.setattr(
        "rishivan.council.classifier.classify_query", fake_classify
    )


def _consult(client, **kw):
    from rishivan.council.orchestrator import council_consult

    return council_consult(
        client, None, kw.pop("question", "when will I marry?"),
        birth_data=BIRTH, query_time=WHEN, **kw,
    )


class TestDirectPath:
    def test_it_returns_the_prompt_it_sent(self, client):
        result = _consult(client, direct=True)
        assert "READING METHOD" in result["direct_prompt"]

    def test_the_prompt_returned_is_the_prompt_sent(self, client):
        """Two assemblies of "the same" prompt is how a UI panel starts lying
        about what the model saw."""
        result = _consult(client, direct=True)
        list(result["answer_stream"])
        assert client.models.stream_prompts == [result["direct_prompt"]]

    def test_the_answer_streams(self, client):
        result = _consult(client, direct=True)
        assert "".join(result["answer_stream"]) == "Marriage is close."

    def test_the_result_keys_are_still_the_declared_contract(self, client):
        from rishivan.graph.state import RESULT_KEYS

        result = _consult(client, direct=True)
        assert RESULT_KEYS <= set(result)

    def test_the_retrieval_panels_get_nothing_to_render(self, client):
        """No panel work is needed in the UI: both expanders are guarded on
        these being non-empty, so they disappear on their own."""
        result = _consult(client, direct=True)
        assert result["sources"] == []
        assert result["matched_rules"] == []

    def test_a_chart_is_still_computed(self, client):
        result = _consult(client, direct=True)
        assert result["chart_facts"]
        assert result["chart_summary"]

    def test_the_computed_chart_reaches_the_prompt(self, client):
        """The whole point: Swiss Ephemeris still owns the placements, and the
        model interprets them rather than guessing them."""
        result = _consult(client, direct=True)
        assert "Ascendant (Lagna)" in result["direct_prompt"]
        assert "COMPUTED PERIODS" in result["direct_prompt"]
