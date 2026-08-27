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
            "classification", "stated_facts", "primary_rishi", "rishi_title",
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

    def test_it_does_not_write_routing(self):
        """`council_routing_node` owns that key and writes a different shape.
        Two writers with two shapes under one key is the ownership violation
        that makes the Phase 4 parallel fan-out unsafe, and nothing reads
        routing between the two nodes anyway."""
        out = intake_node(initial_state("will I be wealthy?"),
                          classify=FakeClassifier(spec()))
        assert "routing" not in out


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
    def test_it_marks_the_turn_without_speaking(self):
        """It settles who is speaking; `narrate.stream_for` does the speaking.

        Phase 5 moved the generator out: a live one in state cannot be
        checkpointed, and leaving it on the greeting path would have meant
        persistence that works until somebody says hello."""
        out = warmth_node(initial_state("hi"))
        assert out["is_warmth"] is True
        assert "answer_stream" not in out

    def test_it_makes_no_model_call(self):
        """The signature is the strongest way to say so — there is no client
        to call one with."""
        import inspect

        assert set(inspect.signature(warmth_node).parameters) == {"state"}

    def test_the_greeting_path_is_recognised_outside_the_graph(self):
        """`stream_for` is what decides a warmth turn gets a greeting rather
        than a reading, and it keys off `is_warmth`."""
        from rishivan.council import narrate

        calls = []

        class _Client:
            class models:
                @staticmethod
                def generate_content_stream(**kw):
                    calls.append(kw)
                    return iter([type("C", (), {"text": "hello"})()])

        final = dict(initial_state("hi"), is_warmth=True, outcome="non_analytic")
        assert "".join(narrate.stream_for(final, client=_Client())) == "hello"

    def test_it_stays_with_the_rishi_already_speaking(self):
        """Continuity: a greeting mid-conversation should not switch voices."""
        class Convo:
            is_empty = False
            current_rishi = "medhan"

        s = initial_state("thanks!", conversation=Convo())
        out = warmth_node(s)
        assert out["primary_rishi"] == "medhan"

    def test_it_defaults_to_vyom_with_no_conversation(self):
        out = warmth_node(initial_state("hi"))
        assert out["primary_rishi"] == "vyom"

    def test_it_carries_the_persona_title(self):
        out = warmth_node(initial_state("hi"))
        assert out["rishi_title"]

    def test_it_reports_a_general_domain_and_no_routing(self):
        """The original returned before either was recorded, so a greeting
        reported GENERAL and `{}`. Intake now runs to completion first, so the
        warmth node restores both explicitly."""
        from rishivan.council.domains import QueryDomain

        out = warmth_node(initial_state("hi"))
        assert out["query_domain"] == QueryDomain.GENERAL
        assert out["routing"] == {}
