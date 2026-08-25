"""Intake: classify, route, and rewrite the domain when there is no chart.

The classifier and the warmth responder are both model calls, so both are
injected. A node that constructs its own client cannot be tested without a
network, and an untestable node is where the next 564-line function starts.
"""

from rishivan.council.domains import QueryDomain
from rishivan.graph.nodes.intake import intake_node, warmth_node
from rishivan.graph.state import initial_state


class FakeClassifier:
    def __init__(self, payload):
        self.payload = dict(payload)
        self.calls = 0
        self.seen = None

    def __call__(self, client, question, **kw):
        self.calls += 1
        self.seen = (client, question, kw)
        return dict(self.payload)


def spec(**kw):
    """A classifier payload with the two keys the orchestrator indexes directly."""
    base = {"primary_rishi": "dhruvan", "query_domain": QueryDomain.GENERAL}
    base.update(kw)
    return base


class TestIntake:
    def test_it_records_the_classification(self):
        fake = FakeClassifier(spec(intent="predict"))
        out = intake_node(initial_state("will I be rich?"), classify=fake)
        assert out["classification"]["intent"] == "predict"
        assert fake.calls == 1

    def test_it_returns_only_the_keys_it_owns(self):
        """A node that returns the whole state defeats LangGraph's merge and
        makes every write look like it came from everywhere."""
        out = intake_node(initial_state("q"), classify=FakeClassifier(spec()))
        assert set(out) <= {
            "classification", "routing", "primary_rishi", "rishi_title",
            "query_domain", "search_query",
        }

    def test_an_override_beats_the_classifier(self):
        fake = FakeClassifier(spec(primary_rishi="dhruvan"))
        s = initial_state("q", rishi_override="agam")
        assert intake_node(s, classify=fake)["primary_rishi"] == "agam"

    def test_an_override_is_written_back_into_the_classification(self):
        """`council_consult:106` does this, and downstream prompts read the
        classification rather than the result key."""
        fake = FakeClassifier(spec(primary_rishi="dhruvan"))
        s = initial_state("q", rishi_override="agam")
        out = intake_node(s, classify=fake)
        assert out["classification"]["primary_rishi"] == "agam"

    def test_the_rishi_title_comes_from_the_persona(self):
        out = intake_node(initial_state("q"), classify=FakeClassifier(spec()))
        assert out["rishi_title"]

    def test_the_conversation_is_passed_to_the_classifier(self):
        """Follow-up routing is folded into that one call rather than a second
        round trip, so dropping the conversation silently breaks continuity."""
        fake = FakeClassifier(spec())
        convo = object()
        intake_node(initial_state("q", conversation=convo), classify=fake)
        assert fake.seen[2]["conversation"] is convo

    def test_routing_is_recorded_for_the_result(self):
        out = intake_node(initial_state("will I be wealthy?"),
                          classify=FakeClassifier(spec()))
        assert "primary" in out["routing"]
        assert "matched" in out["routing"]


class TestNatalFallback:
    """`council_consult:138-141` — the behaviour the plan originally got wrong."""

    def test_a_natal_question_without_a_chart_becomes_prashna(self):
        """It is not a refusal and not a request for input: the moment of asking
        becomes the chart."""
        fake = FakeClassifier(spec(query_domain=QueryDomain.NATAL))
        out = intake_node(initial_state("when will I marry?"), classify=fake)
        assert out["query_domain"] == QueryDomain.PRASHNA

    def test_the_rewrite_is_visible_in_the_classification(self):
        """The orchestrator writes it back so downstream prompts see prashna,
        not natal. A rewrite only in the result key would let the prompt claim a
        birth chart it never had."""
        fake = FakeClassifier(spec(query_domain=QueryDomain.NATAL))
        out = intake_node(initial_state("q"), classify=fake)
        assert out["classification"]["query_domain"] == QueryDomain.PRASHNA

    def test_a_natal_question_with_a_chart_stays_natal(self):
        fake = FakeClassifier(spec(query_domain=QueryDomain.NATAL))
        s = initial_state("q", birth_data=object())
        assert intake_node(s, classify=fake)["query_domain"] == QueryDomain.NATAL

    def test_a_non_natal_domain_is_left_alone(self):
        fake = FakeClassifier(spec(query_domain=QueryDomain.MUHURTA))
        out = intake_node(initial_state("q"), classify=fake)
        assert out["query_domain"] == QueryDomain.MUHURTA


class TestDomainCoercion:
    def test_a_string_domain_is_accepted(self):
        """`classify_query` returns the enum today, but a JSON round trip
        through a checkpointer gives back a string."""
        fake = FakeClassifier(spec(query_domain="natal"))
        s = initial_state("q", birth_data=object())
        assert intake_node(s, classify=fake)["query_domain"] == QueryDomain.NATAL

    def test_an_unknown_domain_falls_back_to_general_rather_than_raising(self):
        """A classifier returning a value we do not know is a bad day, not an
        outage."""
        fake = FakeClassifier(spec(query_domain="astrocartography"))
        out = intake_node(initial_state("q"), classify=fake)
        assert out["query_domain"] == QueryDomain.GENERAL


class TestWarmth:
    def test_it_marks_the_turn_and_supplies_a_stream(self):
        out = warmth_node(
            initial_state("hi"), respond=lambda *a, **k: iter(["hello"])
        )
        assert out["is_warmth"] is True
        assert list(out["answer_stream"]) == ["hello"]

    def test_it_stays_with_the_rishi_already_speaking(self):
        """Continuity: a greeting mid-conversation should not switch voices."""
        class Convo:
            is_empty = False
            current_rishi = "medhan"

        s = initial_state("thanks!", conversation=Convo())
        out = warmth_node(s, respond=lambda *a, **k: iter([""]))
        assert out["primary_rishi"] == "medhan"

    def test_it_defaults_to_vyom_with_no_conversation(self):
        out = warmth_node(initial_state("hi"), respond=lambda *a, **k: iter([""]))
        assert out["primary_rishi"] == "vyom"

    def test_it_carries_the_persona_title(self):
        out = warmth_node(initial_state("hi"), respond=lambda *a, **k: iter([""]))
        assert out["rishi_title"]
