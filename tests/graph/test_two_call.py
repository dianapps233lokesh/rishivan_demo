"""The two-call direct lane, end to end and at the seams.

Two things are worth asserting here and nowhere else: that the reasoning call
and the narration call are genuinely different models, and that what the second
one sees is only ever what the gate let through. Both are properties of the
whole lane rather than of any one function, so they are tested from the adapter.
"""

import json
import re
from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.council.client import model_name
from rishivan.graph.build import TWO_CALL_STATIC_EDGES, build_graph

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


# ── topology ──────────────────────────────────────────────────────────────────

@pytest.fixture
def two_call_graph():
    return build_graph(store=None, client=None, direct=True, two_call=True)


@pytest.fixture
def single_call_graph():
    return build_graph(store=None, client=None, direct=True)


def _nodes(graph):
    return set(graph.get_graph().nodes)


def _edges(graph):
    return {(e.source, e.target) for e in graph.get_graph().edges}


class TestTopology:
    def test_the_reasoning_node_exists_only_in_the_two_call_shape(
        self, two_call_graph, single_call_graph
    ):
        assert "analyse" in _nodes(two_call_graph)
        assert "analyse" not in _nodes(single_call_graph)

    def test_the_prompt_goes_to_the_reasoning_call_before_it_is_traced(
        self, two_call_graph
    ):
        edges = _edges(two_call_graph)
        assert ("direct_read", "analyse") in edges
        assert ("analyse", "persist") in edges
        assert ("direct_read", "persist") not in edges

    def test_the_single_call_shape_is_untouched(self, single_call_graph):
        """The lane this one sits beside. A green assertion here is what makes
        the A/B between them worth running."""
        assert ("direct_read", "persist") in _edges(single_call_graph)

    def test_the_council_is_absent_from_both(self, two_call_graph):
        for gone in ("retrieve", "ground", "koonji_read", "fan_out", "rishi",
                     "sakshi", "synthesis", "answer_plan"):
            assert gone not in _nodes(two_call_graph)

    def test_the_override_table_only_overrides(self, single_call_graph):
        """`TWO_CALL_STATIC_EDGES` re-points edges that already exist. A key
        that names no edge in the base table is a typo nobody would notice."""
        from rishivan.graph.build import DIRECT_STATIC_EDGES

        assert set(TWO_CALL_STATIC_EDGES) - {"analyse"} <= set(DIRECT_STATIC_EDGES)


# ── the lane, running ─────────────────────────────────────────────────────────

VERDICT = {
    "promise": "carried",
    "headline": "Marriage comes between late 2026 and 2027.",
    "not_happening": "Nothing in the next three months.",
    "factors": [
        {"fact": "Venus, house 7", "consequence": "a partner who arrives through "
         "work", "weight": "strong"},
    ],
    "windows": [],
    "exact_times": [],
    "disagreements": [],
    "unsupported": [],
    "falsifier": "No introduction through work by the end of 2027.",
}


class _Chunk:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text):
        self.text = text


class FakeModels:
    """Both calls, kept apart. The classifier is stubbed at its own seam."""

    def __init__(self, verdict=None):
        self.verdict = VERDICT if verdict is None else verdict
        self.analysis_calls = []
        self.narration_calls = []

    def generate_content(self, **kwargs):
        self.analysis_calls.append(kwargs)
        return _Response(json.dumps(self.verdict))

    def generate_content_stream(self, **kwargs):
        self.narration_calls.append(kwargs)
        yield _Chunk("Marriage is close.")


class FakeClient:
    def __init__(self, verdict=None):
        self.models = FakeModels(verdict)


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture(autouse=True)
def stub_classifier(monkeypatch):
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
        birth_data=BIRTH, query_time=WHEN, direct=True, two_call=True, **kw,
    )


class TestTheLaneRuns:
    def test_both_calls_happen(self, client):
        result = _consult(client)
        list(result["answer_stream"])
        assert len(client.models.analysis_calls) == 1
        assert len(client.models.narration_calls) == 1

    def test_the_reasoning_runs_on_pro_and_the_narration_on_flash(self, client):
        """The lane's entire premise. If these ever name the same model, the
        second call is a round trip that bought nothing."""
        result = _consult(client)
        list(result["answer_stream"])
        assert client.models.analysis_calls[0]["model"] == model_name("pro")
        assert client.models.narration_calls[0]["model"] == model_name("flash")
        assert model_name("pro") != model_name("flash")

    def test_the_reasoning_call_gets_the_chart_and_the_method(self, client):
        result = _consult(client)
        prompt = client.models.analysis_calls[0]["contents"]
        assert "READING METHOD" in prompt
        assert "Ascendant (Lagna)" in prompt
        assert prompt == result["direct_prompt"]

    def test_the_reasoning_call_gets_what_THIS_question_requires(self, client):
        """The complaint that produced the requirement registry.

        The first two-call marriage reading leant on Moon-in-7th and general
        dasha strength, because `question_profile` keyed its fact selection on
        the question KIND and ignored the domain entirely - so a marriage timing
        question and a career timing question received byte-identical facts.
        """
        result = _consult(client, question="when will I marry?")
        prompt = result["direct_prompt"]
        assert "THE 7TH HOUSE — computed diagnosis" in prompt
        assert "MANGAL (KUJA) DOSHA" in prompt
        assert "DARAKARAKA" in prompt
        assert "UPAPADA LAGNA" in prompt
        assert "TO THE THIRD LEVEL" in prompt

    def test_the_bands_tell_the_model_what_to_rule_on(self, client):
        """Twelve undifferentiated blocks read as twelve equal facts. The whole
        complaint about the first output was that it weighted general strength
        the same as the seventh house."""
        prompt = _consult(client)["direct_prompt"]
        assert "RULE ON THIS" in prompt
        assert prompt.index("RULE ON THIS") < prompt.index("CORROBORATE")

    def test_an_unmet_requirement_is_declared_against_its_protocol_step(self, client):
        """A reading that skips step 5 says so. `prema.blocked_concepts` has
        listed Darakaraka since the constitutions were written and every
        marriage reading silently skipped it."""
        result = _consult(client)
        report = result["requirement_report"]
        assert report["constitution"] == "prema"
        assert report["required"] > 20

    def test_the_narration_call_never_sees_the_chart(self, client):
        """The actual quality lever. Flash cannot assert a placement it was
        never shown, which is a stronger guarantee than any instruction."""
        result = _consult(client)
        list(result["answer_stream"])
        narration = client.models.narration_calls[0]["contents"]
        assert "READING METHOD" not in narration
        assert "Ascendant (Lagna)" not in narration
        assert "COMPUTED PERIODS" not in narration

    def test_no_iso_date_survives_into_the_narration(self, client):
        result = _consult(client)
        list(result["answer_stream"])
        narration = client.models.narration_calls[0]["contents"]
        assert re.search(r"\d{4}-\d{2}-\d{2}", narration) is None

    def test_the_verdict_comes_back_on_the_result(self, client):
        assert _consult(client)["verdict"].headline == VERDICT["headline"]

    def test_the_answer_streams(self, client):
        assert "".join(_consult(client)["answer_stream"]) == "Marriage is close."

    def test_the_declared_result_contract_is_unchanged(self, client):
        from rishivan.graph.state import RESULT_KEYS

        assert RESULT_KEYS <= set(_consult(client))

    def test_a_chart_is_still_computed(self, client):
        result = _consult(client)
        assert result["chart_facts"] and result["chart_summary"]


class TestTheGateRunsInsideTheLane:
    def test_an_invented_window_never_reaches_the_narrator(self):
        """The failure this lane exists to make impossible. Pro returns a
        boundary Swiss Ephemeris never computed; the reader must not see it."""
        client = FakeClient({**VERDICT, "windows": [
            {"start": "2031-04-04", "end": "2032-01-01",
             "label": "invented", "status": "future"},
        ]})
        result = _consult(client)
        list(result["answer_stream"])
        assert result["verdict"].windows == ()
        assert "2031" not in client.models.narration_calls[0]["contents"]
        assert result["verdict"].dropped

    def test_a_factor_naming_an_unprinted_graha_is_dropped(self):
        client = FakeClient({**VERDICT, "factors": [
            {"fact": "Nibiru, house 7", "consequence": "chaos", "weight": "strong"},
            VERDICT["factors"][0],
        ]})
        result = _consult(client)
        # `Nibiru` is not a graha the gate knows, so it survives on that rule —
        # the gate checks the nine, and inventing a tenth body is a different
        # failure from misattributing a real one. Pinned so the boundary of what
        # this gate does is written down rather than assumed.
        assert len(result["verdict"].factors) == 2


class TestFailure:
    def test_a_failed_analysis_says_so_and_does_not_answer_from_the_other_lane(self):
        """Falling back to the single-call prompt would hand the reader a
        different lane's reading under this lane's name, and make the A/B
        between them unreadable."""
        from rishivan.council.narrate_verdict import FAILED

        client = FakeClient("not a verdict at all")
        client.models.generate_content = lambda **kw: _Response("not json")

        result = _consult(client)
        assert "".join(result["answer_stream"]) == FAILED
        assert client.models.narration_calls == []
        assert result.get("verdict") is None
