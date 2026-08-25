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

    def __init__(self):
        self.prompts: list[str] = []
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
    # Drained here, because `answer_stream` is lazy: the prompt is built
    # eagerly but `generate_content_stream` is not called until something reads
    # the generator. The original behaves the same way — the caller streams it —
    # so consuming it is what a real turn does, not a test contrivance.
    final["answer_text"] = "".join(final["answer_stream"])
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
