"""Grounding, council routing, retrieval, and the answer that declines.

The store and the embedding client are faked. Everything asserted here is a
decision the orchestrator makes before the model is called - which is the half
that can be wrong silently.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.council.domains import QueryDomain
from rishivan.graph.nodes.answer import insufficient_node
from rishivan.graph.nodes.ground import council_routing_node, ground_node
from rishivan.graph.nodes.retrieve import retrieve_node
from rishivan.graph.state import initial_state

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


def state(**kw):
    s = initial_state(kw.pop("question", "will I be wealthy?"))
    s.setdefault("classification", {})
    s.update(kw)
    return s


class FakeStore:
    """Returns hits only when unfiltered - the exact shape of the
    POC-compatibility fallback the orchestrator already has."""

    def __init__(self, *, hits_when_filtered=False):
        self.hits_when_filtered = hits_when_filtered
        self.filtered_calls = 0
        self.plain_calls = 0

    def search_filtered(self, emb, n_results=10, domain_filter=None):
        self.filtered_calls += 1
        return [self._hit()] if self.hits_when_filtered else []

    def search(self, emb, n_results=10):
        self.plain_calls += 1
        return [self._hit()]

    def fetch_pages(self, pages_by_doc):
        return [
            {"document": "a verse from the text",
             "metadata": {"document_id": doc, "page_number": page,
                          "element_index": 0, "book_slug": "bphs"}}
            for doc, pages in pages_by_doc.items() for page in pages
        ]

    @staticmethod
    def _hit():
        """Shaped like a real hit: `expand_to_page_window` indexes
        `document_id`, `page_number` and `element_index` directly, so a thinner
        fake would pass while the real store raised."""
        return {
            "text": "a verse",
            "metadata": {"document_id": 1, "page_number": 5,
                         "element_index": 0, "book_slug": "bphs"},
        }


class FakeClient:
    class models:
        @staticmethod
        def embed_content(model=None, contents=None):
            n = len(contents) if isinstance(contents, list) else 1
            return type("R", (), {
                "embeddings": [type("E", (), {"values": [0.1] * 8})() for _ in range(n)]
            })()


class TestGrounding:
    def test_the_search_query_defaults_to_the_question(self):
        assert ground_node(state())["search_query"] == "will I be wealthy?"

    def test_the_classifier_supplies_the_search_query(self):
        """It rides along with the routing decision - it used to be a second
        serial round trip costing ~5s on every consultation."""
        s = state(classification={"search_query": "dhana yoga wealth"})
        assert ground_node(s)["search_query"] == "dhana yoga wealth"

    def test_a_named_dasha_level_grounds_the_query_in_its_lord(self, chart):
        s = state(chart=chart, query_time=WHEN,
                  classification={"dasha_level": "maha"})
        assert "mahadasha lord" in ground_node(s)["search_query"]

    def test_dasha_level_all_grounds_the_whole_chain(self, chart):
        s = state(chart=chart, query_time=WHEN,
                  classification={"dasha_level": "all"})
        assert "current dasha:" in ground_node(s)["search_query"]

    def test_no_dasha_level_leaves_the_query_alone(self, chart):
        s = state(chart=chart, query_time=WHEN,
                  classification={"dasha_level": "none"})
        assert ground_node(s)["search_query"] == "will I be wealthy?"

    def test_the_remedies_rishi_grounds_by_the_mahadasha_lord(self, chart):
        """BPHS titles its remedy chapters by planet name, so a bare "remedies"
        query misses them entirely."""
        s = state(chart=chart, query_time=WHEN, primary_rishi="tejan")
        assert "remedies for" in ground_node(s)["search_query"]

    def test_nakshatra_now_is_reported_for_a_natal_chart(self, chart):
        s = state(chart=chart, query_domain=QueryDomain.NATAL, query_time=WHEN)
        now = ground_node(s)["nakshatra_now"]
        assert now["birth"]["nakshatra"]
        assert now["today"]["nakshatra"]
        assert now["dasha"]

    def test_nakshatra_now_is_skipped_without_a_natal_chart(self):
        s = state(query_domain=QueryDomain.PRASHNA)
        assert ground_node(s).get("nakshatra_now") is None


class TestCouncilRouting:
    def test_the_routed_domain_decides_who_speaks(self):
        """Not the classifier. The coverage gate keys off the domain, so letting
        the model pick the voice independently let a persona with no coverage of
        the subject answer."""
        s = state(question="when will I marry?", primary_rishi="dhruvan")
        out = council_routing_node(s)
        assert out["primary_rishi"]
        assert out["rishi_title"]

    def test_it_records_the_life_domain_and_routing(self):
        out = council_routing_node(state(question="will I be wealthy?"))
        assert "life_domain" in out
        assert "unsupported" in out["routing"]

    def test_supporting_rishis_widen_the_routing(self):
        """A short question matches one phrase and routes to one domain; the
        classifier's supporting picks are a second source at no extra cost."""
        bare = council_routing_node(state(question="Will I become a billionaire?"))
        widened = council_routing_node(state(
            question="Will I become a billionaire?",
            classification={"supporting_rishis": ["dhruvan", "agam"]},
        ))
        assert len(widened["routing"]["secondary"]) >= len(bare["routing"]["secondary"])


class TestRetrieval:
    def test_it_returns_sources(self):
        s = state(routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        assert out["sources"]

    def test_an_empty_filtered_search_retries_unfiltered(self):
        """A store with no tagged documents must not read as an empty corpus.
        The fallback exists today inside the orchestrator; here it is visible."""
        store = FakeStore(hits_when_filtered=False)
        s = state(routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=store, client=FakeClient())
        assert store.filtered_calls >= 1
        assert store.plain_calls >= 1
        assert out["sources"]

    def test_rules_are_matched_against_the_chart_and_counted(self, chart):
        """Rules run ALONGSIDE page retrieval. The gap between rules true of the
        chart and rules this Rishi was shown is the specialisation working, and
        it is reported rather than implied."""
        s = state(chart=chart, query_time=WHEN,
                  routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        assert out["sources"]
        assert out["rules_true_of_chart"] >= len(out["matched_rules"])
        assert out["chart_tokens"]

    def test_a_broken_rule_base_degrades_to_page_retrieval(self, chart, monkeypatch):
        """`except Exception` around the whole Koonji block, deliberately: a
        missing or stale rule store must cost the rules, never the answer."""
        import rishivan.rag.vector_store as vs

        def boom(*a, **kw):
            raise RuntimeError("qdrant unreachable")

        monkeypatch.setattr(vs, "get_vector_store", boom)
        s = state(chart=chart, query_time=WHEN,
                  routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        assert out["sources"], "the pages must still come back"
        assert out["matched_rules"] == []

    def test_contributors_and_their_reports_are_kept_apart(self, chart):
        """`prompts.contributor_context` reads attributes off the reports;
        `streamlit_app` and `run_eval` read a list of plain dicts. One key
        cannot be both - collapsing them raised `AttributeError: 'dict' object
        has no attribute 'rishi'` on every chart reading with a live rule
        store."""
        s = state(chart=chart, query_time=WHEN,
                  routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        assert all(isinstance(c, dict) for c in out["contributors"])
        assert all(hasattr(r, "rishi") for r in out["contributor_reports"])

    def test_counters_survive_a_failure_after_matching(self, chart, monkeypatch):
        """The counters exist to make a stale index visible. Zeroing them on a
        partial failure is the silent degradation they were built to prevent.

        The failure is injected into `hits_from_reading` because that is what
        builds the panel now; it used to be Qdrant's ranker. The counters are
        computed before it and must outlive it.
        """
        import rishivan.koonji.panel as panel_mod
        from rishivan.koonji.engine import Engine

        engine = Engine.from_rules()
        reading = engine.read(
            chart, when=WHEN, statuses=frozenset({"candidate", "production"})
        )
        # Patched on the panel module rather than on the node: the node imports
        # it inside the function, so the name it binds is resolved at call time
        # from here.
        monkeypatch.setattr(
            panel_mod, "hits_from_reading",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("panel down")),
        )
        s = state(chart=chart, query_time=WHEN, reading=reading,
                  routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        assert out["matched_rules"] == []
        assert out["rules_true_of_chart"] > 0, "the count survived the panel builder"

    def test_it_returns_only_the_keys_it_owns(self):
        s = state(routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        assert set(out) <= {
            "sources", "context_text", "matched_rules", "contributors",
            "contributor_reports", "chart_tokens", "rules_true_of_chart",
            "rules_with_timing", "rules_running_now",
        }


class TestInsufficient:
    def test_it_declines_rather_than_generating(self):
        out = insufficient_node(state())
        assert out["outcome"] == "insufficient"
        assert out["message"].strip()

    def test_it_returns_no_stream(self):
        """`council_consult` returned `answer_stream=None` here and
        `streamlit_app` renders its own warning for that. Streaming a canned
        refusal instead would put it inside a Rishi answer card - a product
        decision, and Phase 1 changes control flow only."""
        assert insufficient_node(state())["answer_stream"] is None


class TestThePanelSeesTheNewRules:
    """The reason the panel was moved off Qdrant.

    Two matchers existed and they read different corpora: Qdrant held rules in
    the old extractor's format, the engine holds them in the frame's. Every
    rule extracted since the format changed fired correctly in the reading and
    was invisible in the panel above it, so the count on screen and the
    evidence behind the answer disagreed by construction.
    """

    def test_the_panel_is_built_from_the_reading(self, chart):
        from rishivan.koonji.engine import Engine

        engine = Engine.from_rules()
        reading = engine.read(
            chart, when=WHEN, statuses=frozenset({"candidate", "production"})
        )
        s = state(chart=chart, query_time=WHEN, reading=reading,
                  routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        assert out["matched_rules"], "the reading fired rules and the panel is empty"
        assert out["rules_true_of_chart"] >= len(out["matched_rules"])

    def test_no_reading_means_an_empty_panel_not_a_crash(self, chart):
        """A chart with no reading is a real state -- `koonji_read` returns None
        when the engine cannot load -- and it must degrade to page retrieval."""
        s = state(chart=chart, query_time=WHEN, reading=None,
                  routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        assert out["matched_rules"] == []
        assert out["rules_true_of_chart"] == 0
        assert out["sources"], "page retrieval still ran"

    def test_every_shown_rule_can_say_why_it_fired(self, chart):
        """`condition_text` is what the panel prints after "because". Empty
        means a reader is shown a citation with no reason attached."""
        from rishivan.koonji.engine import Engine

        engine = Engine.from_rules()
        reading = engine.read(
            chart, when=WHEN, statuses=frozenset({"candidate", "production"})
        )
        s = state(chart=chart, query_time=WHEN, reading=reading,
                  routing={"universes": ["jyotisha"], "primary": "artha"})
        out = retrieve_node(s, vector_store=FakeStore(hits_when_filtered=True),
                            client=FakeClient())
        for hit in out["matched_rules"]:
            assert hit.condition_text, f"{hit.rule_key} has no reason"
            assert hit.citation and "None" not in hit.citation
