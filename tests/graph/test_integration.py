"""One run through the whole graph, asserting on the prompt.

This file exists because 133 node-level tests missed two shipping bugs, and both
lived in the seam between a node and the graph — the one place a node-level test
cannot see:

  * `retrieve_node` returned `context_text`; `RishivanState` did not declare it;
    LangGraph discarded it **silently**. Every answer was generated with an empty
    context block while the sources panel rendered normally. The node test
    asserted the key was in the node's return value, and passed.
  * `contributors` was collapsed from two shapes into one, so the prompt builder
    got dicts where it does attribute access and raised on every chart reading.

Both are prompt-assembly bugs, and nothing was looking at the prompt. So this
does: fakes for the store and the model, a real chart, and assertions on the
string that reaches `generate_content_stream`.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.council.domains import QueryDomain
from rishivan.graph.state import RishivanState

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)

PAGE_TEXT = "MARKER-VERSE-TEXT: the tenth lord in the eleventh gives gains."


class FakeStore:
    def search_filtered(self, emb, n_results=10, domain_filter=None):
        return [self._hit()]

    def search(self, emb, n_results=10):
        return [self._hit()]

    def fetch_pages(self, pages_by_doc):
        return [
            {"document": PAGE_TEXT,
             "metadata": {"document_id": doc, "page_number": page,
                          "element_index": 0, "book_slug": "bphs"}}
            for doc, pages in pages_by_doc.items() for page in pages
        ]

    @staticmethod
    def _hit():
        return {"text": PAGE_TEXT,
                "metadata": {"document_id": 1, "page_number": 5,
                             "element_index": 0, "book_slug": "bphs"}}


class RecordingClient:
    """Captures the prompt instead of calling a model."""

    REPORT = (
        '{"supporting": [{"statement": "the 2nd lord is exalted in the 11th", '
        '"rule_ids": ["r1"], "chart_basis": ["x"], "weight": 0.5, '
        '"tier": "house"}], "weakening": [{"statement": "Saturn aspects it", '
        '"rule_ids": ["r2"], "chart_basis": ["y"], "weight": 0.3, '
        '"tier": "house"}], "score": 0.4, "confidence": 0.6, '
        '"assumptions": [], "would_change_my_mind": [], '
        '"confidence_reasons": ["two independent sources"]}'
    )

    def __init__(self):
        self.prompts: list[str] = []
        self.council_prompts: list[str] = []
        self.report_json = self.REPORT
        outer = self

        class _Models:
            @staticmethod
            def embed_content(model=None, contents=None):
                n = len(contents) if isinstance(contents, list) else 1
                return type("R", (), {
                    "embeddings": [
                        type("E", (), {"values": [0.1] * 8})() for _ in range(n)
                    ]
                })()

            @staticmethod
            def generate_content_stream(model=None, contents=None):
                outer.prompts.append(contents)
                return iter([type("C", (), {"text": "a reading."})()])

            @staticmethod
            def generate_content(model=None, contents=None, config=None):
                """The Rishi and auditor calls.

                Present deliberately. Without it every Rishi hit an
                AttributeError, degraded to an abstention, and the council
                tests below passed while exercising nothing - which is the
                exact shape of the bug this file exists to catch.
                """
                outer.council_prompts.append(contents)
                return type("C", (), {"text": outer.report_json})()

        self.models = _Models()


@pytest.fixture
def served(monkeypatch):
    """A natal reading, driven all the way to the prompt."""
    from rishivan.council import classifier
    from rishivan.graph.build import build_graph
    from rishivan.graph.state import initial_state

    monkeypatch.setattr(
        classifier, "classify_query",
        lambda client, question, **kw: {
            "is_smalltalk_or_gibberish": False,
            "primary_rishi": "dhruvan",
            "query_domain": QueryDomain.NATAL,
            "intent": "predict",
            "search_query": "wealth dhana yoga",
            "dasha_level": "none",
            "relevant_vargas": [],
        },
    )
    client = RecordingClient()
    final = build_graph(store=FakeStore(), client=client).invoke(
        initial_state("will I be wealthy?", birth_data=BIRTH, query_time=WHEN)
    )
    # Narration happens outside the graph now (Phase 5), so the test does what
    # `council_consult` does: build the stream from the plan the graph
    # produced, then drain it. Draining matters — the prompt is built eagerly
    # but `generate_content_stream` is not called until something reads the
    # generator.
    from rishivan.council import narrate

    final["answer_text"] = "".join(
        narrate.stream_for(final, client=client) or [""]
    )
    return final, client


class TestTheRetrievedTextReachesTheModel:
    def test_the_prompt_was_built_at_all(self, served):
        _, client = served
        assert client.prompts, "the run never reached the answer node"

    def test_the_retrieved_passage_is_in_the_prompt(self, served):
        """The regression that shipped. `sources` being populated proves only
        that retrieval ran — not that its text reached the model."""
        _, client = served
        assert PAGE_TEXT in client.prompts[0], (
            "retrieved text never reached the prompt: the answer would read "
            "like a grounded reading and be grounded in nothing"
        )

    def test_context_text_survives_the_graph(self, served):
        """LangGraph drops writes to undeclared channels without a word."""
        final, _ = served
        assert final.get("context_text")

    def test_sources_alone_do_not_prove_grounding(self, served):
        """Pinning the distinction that made the bug invisible: the UI panel and
        the model's context come from different keys."""
        final, client = served
        assert final["sources"]
        assert PAGE_TEXT in client.prompts[0]

    def test_the_chart_facts_reach_the_prompt(self, served):
        final, client = served
        assert final["chart_facts"]
        assert any(f[:24] in client.prompts[0] for f in final["chart_facts"])


class TestTheAnswerContract:
    def test_a_stream_comes_back(self, served):
        final, _ = served
        assert final["answer_text"].strip()

    def test_the_outcome_is_served(self, served):
        final, _ = served
        assert final["outcome"] == "served"

    def test_council_routing_overrode_the_classifier_pick(self, served):
        """Step 3b: the routed life domain decides who speaks, not the model."""
        final, _ = served
        assert final["primary_rishi"]
        assert final["rishi_title"]
        assert final["life_domain"]


class TestNodesOnlyWriteDeclaredKeys:
    def test_every_node_return_key_is_declared_in_the_state(self):
        """The guard for the whole class of bug above.

        A key a node returns but the state does not declare is dropped in
        silence, so this walks the node modules for the literal keys they write
        and checks each against the schema. Three lines of test against four
        remaining phases of new nodes.
        """
        import ast
        import pathlib

        declared = set(RishivanState.__annotations__)
        nodes_dir = pathlib.Path("rishivan/graph/nodes")
        offenders: list[str] = []

        for path in sorted(nodes_dir.glob("*.py")):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                # `return {...}` and `out["key"] = ...`
                keys: list[str] = []
                if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                    keys = [k.value for k in node.value.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                elif (isinstance(node, ast.Assign)
                      and len(node.targets) == 1
                      and isinstance(node.targets[0], ast.Subscript)
                      and isinstance(node.targets[0].value, ast.Name)
                      and node.targets[0].value.id == "out"
                      and isinstance(node.targets[0].slice, ast.Constant)):
                    keys = [node.targets[0].slice.value]
                for key in keys:
                    if isinstance(key, str) and key not in declared:
                        offenders.append(f"{path.name}: {key!r}")

        assert not offenders, (
            "these keys are written by a node and not declared in "
            f"RishivanState, so LangGraph discards them silently: {offenders}"
        )


class TestTheCouncilReachesTheAnswer:
    """The Phase 1 lesson applied to Phase 4.

    Node-level tests cannot see the node-to-graph seam, and both bugs that
    shipped lived there. So these assert on the string that reaches
    `generate_content_stream`.
    """

    def test_the_council_was_convened(self, served):
        _, client = served
        assert client.council_prompts, "no Rishi was ever called"

    def test_reports_came_back(self, served):
        final, _ = served
        assert final["reports"], "the fan-out produced no reports"

    def test_no_rishi_abstained_on_a_valid_generation(self, served):
        """An abstention here means the report never met the contract, and a
        council of abstentions is indistinguishable from a council that
        agreed."""
        final, _ = served
        assert not [r for r in final["reports"] if r.abstained], [
            r.abstained for r in final["reports"] if r.abstained
        ]

    def test_the_council_summary_survives_the_graph(self, served):
        final, _ = served
        assert final.get("council_summary")

    def test_the_council_summary_reaches_the_prompt(self, served):
        """The whole point of Phase 4. A council that reasons and whose
        reasoning never reaches the narrative model has cost eight calls to
        produce nothing."""
        _, client = served
        assert "COUNCIL" in client.prompts[0]

    def test_the_weakening_evidence_reaches_the_prompt(self, served):
        """The half every product drops. If it survives everywhere except the
        prompt, it has been dropped."""
        _, client = served
        assert "Saturn aspects it" in client.prompts[0]

    def test_the_rishi_prompt_carried_the_fired_rules(self, served):
        _, client = served
        assert any("RULES THAT FIRED" in p for p in client.council_prompts)

    def test_the_rishi_prompt_carried_the_hierarchy(self, served):
        _, client = served
        assert any("EVIDENCE HIERARCHY" in p for p in client.council_prompts)

    def test_the_auditor_ran(self, served):
        final, _ = served
        assert final.get("audit") is not None

    def test_the_reading_reached_the_state(self, served):
        """Everything above is downstream of the rule engine actually running.
        Before Phase 4 it was unreachable from the graph entirely."""
        final, _ = served
        assert final.get("reading") is not None
        assert final["reading"].considered > 0

    def test_the_run_terminated(self, served):
        """A bounded critic loop. If `route_after_sakshi` ever stops bounding,
        this test does not fail - it hangs, which is the point."""
        final, _ = served
        assert final["revisions"] <= 1


class TestTheGraphIsNowSerialisable:
    """Phase 5's structural deliverable, asserted on a real run.

    A live generator in state is the one thing a checkpointer cannot persist,
    and the graph put one there on every served turn. These are the tests that
    say it no longer does.
    """

    def test_the_graph_no_longer_puts_a_generator_in_state(self, served):
        import types

        final, _ = served
        assert not isinstance(final.get("answer_stream"), types.GeneratorType)

    def test_the_graph_produces_a_plan_instead(self, served):
        final, _ = served
        assert final.get("answer_plan") is not None

    def test_every_value_in_the_final_state_is_serialisable(self, served):
        """One live object anywhere and the phase is back where it started."""
        from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

        final, _ = served
        JsonPlusSerializer().dumps_typed(final)

    def test_the_narration_prompt_is_built_from_the_plan(self, served):
        final, client = served
        assert "WHAT YOU MAY SAY" in client.prompts[0]

    def test_the_retrieved_passage_still_reaches_the_narration_prompt(self, served):
        """The regression Phase 5 introduced for one commit. The gate covers
        chart *claims*; page text is separate grounding, and most questions in
        this corpus still answer from it alone."""
        _, client = served
        assert PAGE_TEXT in client.prompts[0]

    def test_a_claim_below_the_floor_is_never_licensed(self, served):
        """The gate. A model cannot assert what it was never licensed to.

        The test is on the LICENCE, not on whether the claim id appears
        anywhere in the prompt — the auditor legitimately names an
        under-corroborated claim in order to caution against it, and a naive
        substring check reads that caution as a leak."""
        from rishivan.koonji.evidence import INSUFFICIENT_BELOW

        final, client = served
        allowed = set(final["answer_plan"].claim_ids())
        below = {c.claim_id for c in final["reading"].claims
                 if c.confidence < INSUFFICIENT_BELOW}
        assert not (below & allowed), sorted(below & allowed)

    def test_only_licensed_claims_appear_in_the_may_say_block(self, served):
        """Tighter than the above, and where the gate actually bites: the
        block headed "WHAT YOU MAY SAY" contains the licensed claims and
        nothing else."""
        final, client = served
        prompt = client.prompts[0]
        block = prompt.split("WHAT YOU MAY SAY", 1)[1].split("YOU MUST", 1)[0]
        from rishivan.koonji.evidence import INSUFFICIENT_BELOW

        for claim in final["reading"].claims:
            if claim.confidence < INSUFFICIENT_BELOW:
                assert claim.claim_id not in block, claim.claim_id
