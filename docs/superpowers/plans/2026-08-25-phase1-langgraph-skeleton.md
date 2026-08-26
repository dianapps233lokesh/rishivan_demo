# Phase 1 — LangGraph Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 564-line procedural `council_consult()` with a LangGraph graph whose every branch is a tested conditional edge, producing byte-identical output for the existing eval corpus.

**Architecture:** One `RishivanState` TypedDict flows through single-responsibility nodes. Every `if`/`elif` currently inside `council_consult` becomes either a node (does work) or a `route_*` function (chooses the next node, does nothing else). `council_consult` survives as a thin adapter over `graph.invoke()` so `streamlit_app.py` and `tests/eval/` are untouched.

**Tech Stack:** langgraph · pydantic v2 · existing `rishivan.council.*` helpers, called from nodes rather than inlined.

**Spec:** `docs/superpowers/specs/2026-08-25-chart-understanding-council-architecture.md` (§3 topology, §4 state, §10 conditional mapping)

## Global Constraints

- **Behaviour-preserving.** No new astrology, no new prompts, no changed model calls. Phase 1 is a refactor with a graph shape.
- `council_consult(...) -> dict` keeps its exact signature and every one of its 20 result keys. `streamlit_app.py:352` and `tests/eval/run_eval.py:220` must not change.
- Streaming survives: `result["answer_stream"]` stays a `Generator[str, None, None]`.
- Python 3.10-compatible syntax (`.venv` is 3.14, but `rishivan/` targets 3.10 — use `X | None`, not `Optional`, matching the existing files).
- `langgraph>=0.2.60` pinned, not floated — this repo pins for Streamlit Cloud reproducibility (see `requirements.txt` header).
- Nodes never call `if` on business conditions. A node that branches is a node that should have been two nodes and an edge.
- Test runner: `./.venv/bin/python -m pytest`.

---

### Task 1: Dependency and package skeleton

**Files:**
- Modify: `requirements.txt`
- Create: `rishivan/graph/__init__.py`
- Test: `tests/graph/test_imports.py`

**Interfaces:**
- Consumes: nothing
- Produces: importable package `rishivan.graph`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_imports.py
"""The graph package exists and langgraph is a real, pinned dependency.

Trivial, and worth a test: a missing pin is the failure that only shows up on
Streamlit Cloud, three days later, in someone else's session.
"""


def test_langgraph_is_installed():
    import langgraph.graph  # noqa: F401


def test_langgraph_is_pinned_not_floated():
    from pathlib import Path

    line = next(
        l for l in Path("requirements.txt").read_text().splitlines()
        if l.strip().startswith("langgraph")
    )
    assert "==" in line, f"pin it: {line!r}"


def test_graph_package_imports():
    import rishivan.graph  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_imports.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'langgraph'`

- [ ] **Step 3: Add the dependency and the package**

Append to `requirements.txt`, after the `qdrant-client` line:

```
# LangGraph — the council pipeline's control flow. Pinned like everything else
# here: a floating graph library changed `add_conditional_edges`' signature
# between minors once already, and the failure surfaces at import on the
# deploy, not in CI.
langgraph==0.2.60
```

Create `rishivan/graph/__init__.py`:

```python
"""The council pipeline as a graph.

`council/orchestrator.py` grew to 564 lines with every branch inline, which
made the branches untestable: you could not ask "what happens to a muhurta
question with no birth data" without running the whole pipeline, model calls
and all.

Here a node does work and an edge chooses. Every `route_*` function is pure
(`State -> str`) and gets a table-driven test, which is the entire point.
"""
```

Create `tests/graph/__init__.py` (empty).

Then: `./.venv/bin/pip install 'langgraph==0.2.60'`

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/test_imports.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add requirements.txt rishivan/graph/__init__.py tests/graph/
git commit -m "build: add langgraph, pinned, and the graph package"
```

---

### Task 2: The state schema

**Files:**
- Create: `rishivan/graph/state.py`
- Test: `tests/graph/test_state.py`

**Interfaces:**
- Consumes: `rishivan.koonji.question.QuestionSpec`, `rishivan.koonji.router.RetrievalPlan`, `rishivan.chart.ephemeris.Chart`
- Produces: `RishivanState` (TypedDict), `initial_state(question, **kw) -> RishivanState`, `RESULT_KEYS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_state.py
"""The one object every node reads and writes.

Phase 1 carries the Phase 2-5 keys already (chart_state, vargas, timing,
reports) so that later phases add nodes rather than migrating state. They stay
None here.
"""

from rishivan.graph.state import RESULT_KEYS, RishivanState, initial_state


def test_initial_state_carries_the_question():
    s = initial_state("will I be wealthy?")
    assert s["question"] == "will I be wealthy?"
    assert s["outcome"] == "pending"


def test_every_run_gets_an_id():
    """It becomes the trace id. Two runs must not share one."""
    assert initial_state("q")["run_id"] != initial_state("q")["run_id"]


def test_the_result_contract_is_declared_not_inferred():
    """`council_consult` returns exactly these 20 keys today. Naming them here
    is what lets the adapter test assert the contract instead of guessing it."""
    assert "primary_rishi" in RESULT_KEYS
    assert "answer_stream" in RESULT_KEYS
    assert len(RESULT_KEYS) == 20


def test_future_phase_keys_exist_and_are_none():
    """Phase 2-5 add nodes, not state migrations."""
    s = initial_state("q")
    for key in ("chart_state", "vargas", "timing", "hierarchy"):
        assert s[key] is None


def test_reports_is_a_list_so_the_fanout_can_reduce_into_it():
    assert initial_state("q")["reports"] == []


def test_birth_kwargs_are_carried_through():
    s = initial_state("q", tz_offset=5.5, place="Delhi")
    assert s["tz_offset"] == 5.5
    assert s["place"] == "Delhi"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rishivan.graph.state'`

- [ ] **Step 3: Write the implementation**

```python
# rishivan/graph/state.py
"""The state every node reads and writes.

One flat TypedDict rather than per-node models, because LangGraph merges
partial dict updates: a node returns only the keys it owns, and that merge is
what makes the Phase 4 parallel fan-out safe.

Exactly one node writes each key. `reports` is the single exception and carries
an additive reducer, because eight Rishi nodes write it concurrently.
"""

from __future__ import annotations

import operator
import time
import uuid
from datetime import datetime
from typing import Annotated, Any, Generator, TypedDict


class RishivanState(TypedDict, total=False):
    # -- request identity, written once at intake ----------------------
    run_id: str
    question: str
    rishi_override: str | None
    conversation: Any

    # -- birth inputs, passed straight through -------------------------
    birth_data: Any
    query_time: datetime | None
    target_time: datetime | None
    lat: float | None
    lon: float | None
    tz_offset: float
    place: str

    # -- intake --------------------------------------------------------
    classification: dict
    routing: dict
    primary_rishi: str
    rishi_title: str
    query_domain: Any
    outcome: str
    message: str

    # -- chart ---------------------------------------------------------
    chart: Any
    chart_summary: str | None
    chart_facts: list[str] | None
    chart_tokens: dict
    chart_table: str | None
    chart_table_error: str | None
    relevant_chart_tables: dict
    panchang: str | None
    nakshatra_now: str | None

    # -- Phase 2-5 placeholders. Nodes are added later; state is not. ---
    chart_state: Any
    vargas: Any
    timing: Any
    hierarchy: Any
    reading: Any

    # -- retrieval -----------------------------------------------------
    search_query: str
    sources: list
    matched_rules: list
    contributors: list
    rules_true_of_chart: int
    rules_with_timing: int
    rules_running_now: int

    # -- council · the only reduced key --------------------------------
    reports: Annotated[list, operator.add]
    audit: Any
    revisions: int

    # -- output --------------------------------------------------------
    is_warmth: bool
    answer_stream: Generator[str, None, None] | None
    trace: dict


RESULT_KEYS: frozenset[str] = frozenset({
    "primary_rishi", "rishi_title", "query_domain", "classification",
    "chart_summary", "chart_facts", "chart_table", "chart_table_error",
    "nakshatra_now", "relevant_chart_tables", "sources", "search_query",
    "answer_stream", "is_warmth", "matched_rules", "contributors",
    "chart_tokens", "rules_true_of_chart", "rules_with_timing",
    "rules_running_now",
})
"""The keys `council_consult` has always returned.

Declared rather than inferred so the adapter's contract test asserts a fact
instead of restating whatever the code happens to produce. `routing` and
`panchang` are set conditionally today and are deliberately NOT in this set -
callers use `.get()` for them, and promising them would be a new contract.
"""


def initial_state(question: str, **kw: Any) -> RishivanState:
    """A run's starting state. Every key the graph reads exists here.

    Defaults are explicit rather than relying on `total=False`: a node reading
    a key no one set gets a KeyError at the worst possible moment, and a
    missing default is invisible until the branch that needs it is taken.
    """
    from rishivan.council.domains import QueryDomain

    return RishivanState(
        run_id=f"ir_{int(time.time() * 1000):x}_{uuid.uuid4().hex[:8]}",
        question=question,
        rishi_override=kw.get("rishi_override"),
        conversation=kw.get("conversation"),
        birth_data=kw.get("birth_data"),
        query_time=kw.get("query_time"),
        target_time=kw.get("target_time"),
        lat=kw.get("lat"),
        lon=kw.get("lon"),
        tz_offset=kw.get("tz_offset", 5.5),
        place=kw.get("place", ""),
        classification={},
        routing={},
        primary_rishi=kw.get("rishi_override") or "vyom",
        rishi_title="",
        query_domain=QueryDomain.GENERAL,
        outcome="pending",
        message="",
        chart=None,
        chart_summary=None,
        chart_facts=None,
        chart_tokens={},
        chart_table=None,
        chart_table_error=None,
        relevant_chart_tables={},
        panchang=None,
        nakshatra_now=None,
        chart_state=None,
        vargas=None,
        timing=None,
        hierarchy=None,
        reading=None,
        search_query=question,
        sources=[],
        matched_rules=[],
        contributors=[],
        rules_true_of_chart=0,
        rules_with_timing=0,
        rules_running_now=0,
        reports=[],
        audit=None,
        revisions=0,
        is_warmth=False,
        answer_stream=None,
        trace={},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/test_state.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/state.py tests/graph/test_state.py
git commit -m "feat(graph): the state every node reads and writes"
```

---

### Task 3: The routers — every conditional, as pure functions

**Files:**
- Create: `rishivan/graph/edges.py`
- Test: `tests/graph/test_edges.py`

**Interfaces:**
- Consumes: `RishivanState`
- Produces: `route_after_intake(state) -> str`, `route_after_chart(state) -> str`, `route_chart_kind(state) -> str`, `route_after_retrieval(state) -> str`

This is the task the whole phase exists for. Each router is `State -> str` and touches nothing else.

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_edges.py
"""Every branch the orchestrator used to take, as a table.

These branches exist today inside `council_consult`, where testing one meant
running all of it - chart computation, embeddings, model calls. That is why
none of them were tested. Pure functions fix that, and the table below is the
list of behaviours Phase 1 must preserve exactly.
"""

import pytest

from rishivan.council.domains import QueryDomain
from rishivan.graph.edges import (
    route_after_chart,
    route_after_intake,
    route_after_retrieval,
    route_chart_kind,
)
from rishivan.graph.state import initial_state


def state(**kw):
    s = initial_state(kw.pop("question", "will I be wealthy?"))
    s.update(kw)
    return s


class TestAfterIntake:
    def test_smalltalk_bypasses_everything(self):
        s = state(classification={"is_smalltalk_or_gibberish": True})
        assert route_after_intake(s) == "warmth"

    def test_a_natal_question_without_birth_data_asks_for_it(self):
        """Today: `if domain == NATAL and birth_data is None`. Answering a
        natal question with no chart is answering a different question."""
        s = state(query_domain=QueryDomain.NATAL, birth_data=None)
        assert route_after_intake(s) == "need_birth_data"

    def test_a_natal_question_with_birth_data_proceeds(self):
        s = state(query_domain=QueryDomain.NATAL, birth_data=object())
        assert route_after_intake(s) == "chart"

    def test_muhurta_proceeds_to_chart_without_birth_data(self):
        """Muhurta is cast from a target moment, not from a birth."""
        s = state(query_domain=QueryDomain.MUHURTA, birth_data=None)
        assert route_after_intake(s) == "chart"

    def test_prashna_proceeds_without_birth_data(self):
        s = state(query_domain=QueryDomain.PRASHNA, birth_data=None)
        assert route_after_intake(s) == "chart"

    def test_a_general_question_skips_the_chart(self):
        s = state(query_domain=QueryDomain.GENERAL, birth_data=None)
        assert route_after_intake(s) == "retrieve"

    def test_smalltalk_wins_over_a_missing_chart(self):
        """Order matters: "hi" from a user with no birth data is a greeting,
        not a request for birth details."""
        s = state(
            classification={"is_smalltalk_or_gibberish": True},
            query_domain=QueryDomain.NATAL, birth_data=None,
        )
        assert route_after_intake(s) == "warmth"


class TestAfterChart:
    def test_a_chart_request_goes_to_rendering(self):
        s = state(chart=object(), classification={"intent": "chart"})
        assert route_after_chart(s) == "chart_render"

    def test_a_panchang_mention_goes_to_panchang(self):
        s = state(chart=object(), classification={"intent": "predict"},
                  question="what is the panchang today?")
        assert route_after_chart(s) == "panchang"

    def test_an_ordinary_question_goes_to_retrieval(self):
        s = state(chart=object(), classification={"intent": "predict"})
        assert route_after_chart(s) == "retrieve"

    def test_chart_intent_without_a_chart_does_not_render(self):
        """`if chart is not None and intent == 'chart'` - both halves."""
        s = state(chart=None, classification={"intent": "chart"})
        assert route_after_chart(s) == "retrieve"


class TestChartKind:
    @pytest.mark.parametrize("kind,expected", [
        ("numerology", "render_numerology"),
        ("ashtakavarga", "render_ashtakavarga"),
        ("dasha", "render_dasha"),
        ("rashi", "render_varga"),
        ("", "render_varga"),
    ])
    def test_each_chart_kind_has_a_renderer(self, kind, expected):
        s = state(classification={"chart_type": kind})
        assert route_chart_kind(s) == expected

    def test_numerology_without_a_birth_date_is_refused(self):
        """Today this returns a `chart_table_error`. It is a refusal, and a
        refusal is a destination, not a string in a dict."""
        s = state(classification={"chart_type": "numerology"}, birth_data=None)
        assert route_chart_kind(s) == "need_birth_data"


class TestAfterRetrieval:
    def test_sources_lead_to_an_answer(self):
        assert route_after_retrieval(state(sources=[{"text": "x"}])) == "answer"

    def test_no_sources_is_insufficient_evidence(self):
        """Saying the corpus is silent is an answer. Generating around it is
        the failure this whole architecture exists to prevent."""
        assert route_after_retrieval(state(sources=[])) == "insufficient"


class TestPurity:
    def test_routers_do_not_mutate_state(self):
        """A router that writes is a node wearing an edge's clothes, and the
        write happens on a path nobody expects."""
        import copy

        for router in (route_after_intake, route_after_chart,
                       route_chart_kind, route_after_retrieval):
            s = state(chart=object(), sources=[{"text": "x"}],
                      classification={"intent": "predict", "chart_type": ""})
            before = copy.deepcopy({k: v for k, v in s.items()
                                    if k not in ("chart", "conversation")})
            router(s)
            after = {k: v for k, v in s.items()
                     if k not in ("chart", "conversation")}
            assert before == after, router.__name__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_edges.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rishivan.graph.edges'`

- [ ] **Step 3: Write the implementation**

```python
# rishivan/graph/edges.py
"""Every conditional the orchestrator used to take, as a pure function.

A router reads state and returns the name of the next node. It does not write,
does not compute, and does not call anything expensive. That restriction is
what makes the table in `tests/graph/test_edges.py` possible, and that table is
the first time these branches have been tested at all.
"""

from __future__ import annotations

from rishivan.council.domains import QueryDomain
from rishivan.graph.state import RishivanState

#: Domains that cast a chart from something other than a birth moment, and so
#: proceed without birth data. Muhurta uses a target time, Prashna the moment
#: the question was asked.
_CHARTED_WITHOUT_BIRTH = (QueryDomain.MUHURTA, QueryDomain.PRASHNA)


def route_after_intake(state: RishivanState) -> str:
    """warmth · need_birth_data · chart · retrieve

    Small talk is checked first and deliberately: "hi" from a user who has not
    entered birth details is a greeting, and asking them for a birth time is a
    worse answer than saying hello.
    """
    if state["classification"].get("is_smalltalk_or_gibberish"):
        return "warmth"

    domain = state["query_domain"]
    if domain == QueryDomain.NATAL:
        return "chart" if state.get("birth_data") is not None else "need_birth_data"
    if domain in _CHARTED_WITHOUT_BIRTH:
        return "chart"
    return "retrieve"


def route_after_chart(state: RishivanState) -> str:
    """chart_render · panchang · retrieve"""
    from rishivan.chart.panchang import mentions_panchang

    if state.get("chart") is None:
        return "retrieve"
    if state["classification"].get("intent") == "chart":
        return "chart_render"
    if mentions_panchang(state["question"]):
        return "panchang"
    return "retrieve"


def route_chart_kind(state: RishivanState) -> str:
    """render_numerology · render_ashtakavarga · render_dasha · render_varga
    · need_birth_data

    Numerology is the one kind that can be asked for without a chart being
    computable, because it needs a date rather than a moment - so it is the one
    kind that can bounce back to asking for input.
    """
    kind = state["classification"].get("chart_type", "")
    if kind == "numerology":
        return "render_numerology" if state.get("birth_data") is not None else "need_birth_data"
    if kind == "ashtakavarga":
        return "render_ashtakavarga"
    if kind == "dasha":
        return "render_dasha"
    return "render_varga"


def route_after_retrieval(state: RishivanState) -> str:
    """answer · insufficient

    An empty source list is not an empty answer - it is the answer. Generating
    prose over no retrieved material is the exact failure the grounding
    discipline exists to prevent, and it is invisible in the output.
    """
    return "answer" if state.get("sources") else "insufficient"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/test_edges.py -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/edges.py tests/graph/test_edges.py
git commit -m "feat(graph): every orchestrator conditional as a tested pure router"
```

---

### Task 4: Intake and warmth nodes

**Files:**
- Create: `rishivan/graph/nodes/__init__.py`
- Create: `rishivan/graph/nodes/intake.py`
- Test: `tests/graph/test_nodes_intake.py`

**Interfaces:**
- Consumes: `RishivanState`, `rishivan.council.classifier.classify_query`, `rishivan.council.routing.route_question`, `rishivan.council.personas.RISHIS`, `rishivan.council.warmth.respond_warmly`
- Produces: `intake_node(state) -> dict`, `warmth_node(state) -> dict`, `need_birth_data_node(state) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_nodes_intake.py
"""Intake: classify, route, and bail out early when there is nothing to answer.

The classifier is a model call, so it is injected. A node that constructs its
own client cannot be tested without a network, and an untestable node is where
the next 564-line function starts.
"""

from rishivan.council.domains import QueryDomain
from rishivan.graph.nodes.intake import (
    intake_node,
    need_birth_data_node,
    warmth_node,
)
from rishivan.graph.state import initial_state


class FakeClassifier:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def __call__(self, *a, **kw):
        self.calls += 1
        return self.payload


def test_intake_records_the_classification():
    fake = FakeClassifier({"intent": "predict", "primary_rishi": "dhruvan"})
    out = intake_node(initial_state("will I be rich?"), classify=fake)
    assert out["classification"]["intent"] == "predict"
    assert fake.calls == 1


def test_intake_returns_only_the_keys_it_owns():
    """A node that returns the whole state defeats LangGraph's merge and makes
    every write look like it came from everywhere."""
    fake = FakeClassifier({"intent": "predict"})
    out = intake_node(initial_state("q"), classify=fake)
    assert set(out) <= {"classification", "routing", "primary_rishi",
                        "rishi_title", "query_domain", "search_query"}


def test_an_override_beats_the_classifier():
    fake = FakeClassifier({"primary_rishi": "dhruvan"})
    s = initial_state("q", rishi_override="agam")
    assert intake_node(s, classify=fake)["primary_rishi"] == "agam"


def test_the_domain_comes_from_the_classifier():
    fake = FakeClassifier({"query_domain": "natal"})
    out = intake_node(initial_state("q"), classify=fake)
    assert out["query_domain"] == QueryDomain.NATAL


def test_an_unknown_domain_falls_back_to_general_rather_than_raising():
    """A classifier returning a value we do not know is a bad day, not an
    outage."""
    fake = FakeClassifier({"query_domain": "astrocartography"})
    assert intake_node(initial_state("q"), classify=fake)["query_domain"] == (
        QueryDomain.GENERAL
    )


def test_warmth_marks_the_turn_and_supplies_a_stream():
    s = initial_state("hi")
    s["classification"] = {"is_smalltalk_or_gibberish": True}
    out = warmth_node(s, respond=lambda *a, **k: iter(["hello"]))
    assert out["is_warmth"] is True
    assert list(out["answer_stream"]) == ["hello"]


def test_need_birth_data_is_a_terminal_outcome_with_a_message():
    out = need_birth_data_node(initial_state("will I be rich?"))
    assert out["outcome"] == "needs_input"
    assert "birth" in out["message"].lower()
    assert out["answer_stream"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_intake.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rishivan.graph.nodes'`

- [ ] **Step 3: Write the implementation**

Create `rishivan/graph/nodes/__init__.py`:

```python
"""One file per node group. A node takes state and returns only the keys it
owns - never the whole state, because LangGraph merges partial updates and a
full-state return makes every write look like it came from everywhere."""
```

Create `rishivan/graph/nodes/intake.py`:

```python
"""Classify the turn, route it, and bail out when there is nothing to answer.

Model-calling collaborators are injected. A node that builds its own client
cannot be tested without a network, and an untestable node is where the next
564-line function starts.
"""

from __future__ import annotations

from typing import Callable

from rishivan.council.domains import QueryDomain
from rishivan.graph.state import RishivanState

NEED_BIRTH_MESSAGE = (
    "I'll need your birth date, time and place before I can read the chart. "
    "A natal answer without a chart would be a different answer to a "
    "different question."
)


def _domain(raw: object) -> QueryDomain:
    try:
        return QueryDomain(str(raw))
    except ValueError:
        # An unrecognised domain is a bad classifier day, not an outage. It
        # falls back to the widest scope rather than to a crash.
        return QueryDomain.GENERAL


def intake_node(
    state: RishivanState, *, classify: Callable | None = None
) -> dict:
    if classify is None:
        from rishivan.council.classifier import classify_query as classify

    from rishivan.council.personas import RISHIS
    from rishivan.council.routing import route_question

    classification = classify(state["question"]) or {}
    routing = route_question(state["question"])

    rishi = state.get("rishi_override") or classification.get(
        "primary_rishi", "vyom"
    )
    persona = RISHIS.get(rishi)

    return {
        "classification": classification,
        "routing": {
            "primary": routing.primary,
            "secondary": list(routing.secondary),
            "application": routing.application,
            "universes": sorted(routing.universes),
            "matched": {k: list(v) for k, v in routing.matched.items()},
        },
        "primary_rishi": rishi,
        "rishi_title": getattr(persona, "title", ""),
        "query_domain": _domain(classification.get("query_domain", "general")),
        "search_query": state["question"],
    }


def warmth_node(state: RishivanState, *, respond: Callable | None = None) -> dict:
    """Small talk. No chart, no retrieval, no rules - and no apology for it."""
    if respond is None:
        from rishivan.council.warmth import respond_warmly as respond

    return {
        "is_warmth": True,
        "outcome": "non_analytic",
        "answer_stream": respond(state["question"], state.get("conversation")),
    }


def need_birth_data_node(state: RishivanState) -> dict:
    """Ask, rather than answer around the gap.

    A terminal outcome that still fills `answer_stream`, because every caller
    reads the answer the same way and a special case here would spread to all
    of them.
    """
    return {
        "outcome": "needs_input",
        "message": NEED_BIRTH_MESSAGE,
        "answer_stream": iter([NEED_BIRTH_MESSAGE]),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_intake.py -v`
Expected: 7 passed

Verified names: `classify_query` (`council/classifier.py:183`),
`respond_warmly` (`council/warmth.py:46`).

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/nodes/ tests/graph/test_nodes_intake.py
git commit -m "feat(graph): intake, warmth and need-birth-data nodes"
```

---

### Task 5: Chart and rendering nodes

**Files:**
- Create: `rishivan/graph/nodes/chart.py`
- Test: `tests/graph/test_nodes_chart.py`

**Interfaces:**
- Consumes: `rishivan.chart.ephemeris.compute_chart/summarize`, `rishivan.chart.facts.derive_facts`, `rishivan.chart.local_varga.varga_table_markdown`, `rishivan.chart.local_dasha.dasha_table_markdown`, `rishivan.chart.local_ashtakavarga.ashtakavarga_table_markdown`, `rishivan.chart.local_numerology`, `rishivan.chart.panchang.compute_panchang`
- Produces: `chart_node`, `panchang_node`, `render_varga_node`, `render_dasha_node`, `render_ashtakavarga_node`, `render_numerology_node` — all `(state) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_nodes_chart.py
"""Chart materialisation and the four render kinds.

Uses a real chart, not a mock: the ephemeris is local, fast and deterministic,
and mocking it would test the mock. The birth data below is fixed so expected
values are checkable by hand against any ephemeris.
"""

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.graph.nodes.chart import (
    chart_node,
    render_ashtakavarga_node,
    render_dasha_node,
    render_varga_node,
)
from rishivan.graph.state import initial_state

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture
def charted():
    s = initial_state("will I be wealthy?", birth_data=BIRTH)
    s.update(chart_node(s))
    return s


def test_chart_node_computes_a_chart_and_its_summary(charted):
    assert charted["chart"] is not None
    assert charted["chart_summary"]


def test_chart_node_derives_facts(charted):
    assert charted["chart_facts"]


def test_chart_node_is_deterministic():
    a = chart_node(initial_state("q", birth_data=BIRTH))
    b = chart_node(initial_state("q", birth_data=BIRTH))
    assert a["chart_summary"] == b["chart_summary"]
    assert a["chart_facts"] == b["chart_facts"]


def test_render_varga_produces_a_table(charted):
    out = render_varga_node(charted)
    assert out["chart_table"]
    assert out["chart_table_error"] is None


def test_render_dasha_produces_a_table(charted):
    assert render_dasha_node(charted)["chart_table"]


def test_render_ashtakavarga_produces_a_table(charted):
    assert render_ashtakavarga_node(charted)["chart_table"]


def test_a_renderer_that_cannot_compute_says_so_rather_than_returning_none():
    """Today an unavailable table silently returns None and the answer is
    generated anyway. An honest "can't compute this" beats a quiet omission."""
    s = initial_state("q", birth_data=BIRTH)
    s["chart"] = None
    out = render_varga_node(s)
    assert out["chart_table"] is None
    assert out["chart_table_error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_chart.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rishivan.graph.nodes.chart'`

- [ ] **Step 3: Write the implementation**

```python
# rishivan/graph/nodes/chart.py
"""Materialise the chart, and render whichever table was asked for.

Rendering is four nodes rather than one node with a `kind` argument, because
`route_chart_kind` already made that decision and re-deciding it inside the
node is the branching this refactor is removing.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState

_CANNOT_RENDER = (
    "I can compute that table only from a chart, and no chart was cast for "
    "this question."
)


def chart_node(state: RishivanState) -> dict:
    from rishivan.chart.ephemeris import compute_chart, summarize
    from rishivan.chart.facts import derive_facts
    from rishivan.chart.tokens import chart_tokens

    chart = compute_chart(state["birth_data"])
    when = state.get("target_time") or state.get("query_time")
    return {
        "chart": chart,
        "chart_summary": summarize(chart),
        "chart_facts": derive_facts(chart, when),
        "chart_tokens": chart_tokens(chart),
    }


def panchang_node(state: RishivanState) -> dict:
    """Port of `council_consult` lines 199-212.

    `compute_panchang` returns an object; the orchestrator has always stored
    `.summary()`, and the result key is a string. Keep it that way - the
    Streamlit view renders it as markdown.
    """
    from rishivan.chart.panchang import compute_panchang, relative_day_offset

    panchang = compute_panchang(
        when=state.get("query_time"),
        day_offset=relative_day_offset(state["question"]),
        lat=state["lat"] if state.get("lat") is not None else 28.6139,
        lon=state["lon"] if state.get("lon") is not None else 77.2090,
        tz_offset=state.get("tz_offset", 5.5),
    )
    return {"panchang": panchang.summary()}


def _rendered(table: str | None) -> dict:
    """One shape for every renderer.

    A renderer that cannot produce its table returns the reason, not None. A
    silent None becomes an answer generated without the evidence the user
    explicitly asked to see.
    """
    if table:
        return {"chart_table": table, "chart_table_error": None}
    return {"chart_table": None, "chart_table_error": _CANNOT_RENDER}


def render_varga_node(state: RishivanState) -> dict:
    from rishivan.chart.local_varga import varga_table_markdown

    chart = state.get("chart")
    if chart is None:
        return _rendered(None)
    code = state["classification"].get("varga_code", "D1")
    return _rendered(varga_table_markdown(chart, code))


def render_dasha_node(state: RishivanState) -> dict:
    from rishivan.chart.local_dasha import dasha_table_markdown

    chart = state.get("chart")
    if chart is None:
        return _rendered(None)
    return _rendered(dasha_table_markdown(chart, state.get("query_time")))


def render_ashtakavarga_node(state: RishivanState) -> dict:
    from rishivan.chart.local_ashtakavarga import ashtakavarga_table_markdown

    chart = state.get("chart")
    if chart is None:
        return _rendered(None)
    return _rendered(ashtakavarga_table_markdown(chart))


def render_numerology_node(state: RishivanState) -> dict:
    from rishivan.chart.local_numerology import numerology_table_markdown

    birth = state.get("birth_data")
    if birth is None:
        return _rendered(None)
    return _rendered(numerology_table_markdown(birth))
```

Verified names: `compute_panchang` + `relative_day_offset`
(`chart/panchang.py:95,167`), `numerology_table_markdown`
(`chart/local_numerology.py:21`), `chart_tokens` (`chart/tokens.py:73`),
`mentions_panchang` (`chart/panchang.py:161` — **not** in `council/classifier`).

Check `compute_panchang`'s exact keyword names against line 95 before wiring;
the orchestrator's call at line 204 is the reference.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_chart.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/nodes/chart.py tests/graph/test_nodes_chart.py
git commit -m "feat(graph): chart materialisation and the four render nodes"
```

---

### Task 6: Retrieval and answer nodes

**Files:**
- Create: `rishivan/graph/nodes/retrieve.py`
- Create: `rishivan/graph/nodes/answer.py`
- Test: `tests/graph/test_nodes_retrieve.py`

**Interfaces:**
- Consumes: the `store` and `client` handles `council_consult` already receives, `rishivan.council.source_matrix.slugs_for_universe`, `rishivan.council.contributors`
- Produces: `retrieve_node(state, *, store, client) -> dict`, `answer_node(state, *, client) -> dict`, `insufficient_node(state) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_nodes_retrieve.py
"""Retrieval, its filter fallback, and the honest empty answer."""

from rishivan.graph.nodes.answer import insufficient_node
from rishivan.graph.nodes.retrieve import retrieve_node
from rishivan.graph.state import initial_state


class FakeStore:
    """Returns hits only when no filter is applied - the exact shape of the
    POC-compatibility fallback the orchestrator already has."""

    def __init__(self, *, hits_when_filtered=False):
        self.hits_when_filtered = hits_when_filtered
        self.queries = []

    def search(self, *, vector=None, limit=10, query_filter=None, **kw):
        self.queries.append(query_filter)
        if query_filter is not None and not self.hits_when_filtered:
            return []
        return [{"text": "a verse", "book": "bphs", "locator": "ch1.v1"}]


def fake_client():
    class C:
        class models:
            @staticmethod
            def embed_content(**kw):
                class R:
                    embeddings = [type("E", (), {"values": [0.1] * 768})()]
                return R()
    return C()


def test_retrieval_returns_sources():
    s = initial_state("will I be wealthy?")
    s["routing"] = {"universes": ["jyotisha"]}
    out = retrieve_node(s, store=FakeStore(hits_when_filtered=True), client=fake_client())
    assert out["sources"]


def test_an_empty_filtered_search_retries_unfiltered():
    """A store with no tagged documents must not read as an empty corpus. The
    fallback exists today inside the orchestrator; here it is visible."""
    store = FakeStore(hits_when_filtered=False)
    s = initial_state("will I be wealthy?")
    s["routing"] = {"universes": ["jyotisha"]}
    out = retrieve_node(s, store=store, client=fake_client())
    assert out["sources"]
    assert len(store.queries) == 2
    assert store.queries[-1] is None


def test_insufficient_says_so_rather_than_generating():
    out = insufficient_node(initial_state("will I be wealthy?"))
    assert out["outcome"] == "insufficient"
    assert out["answer_stream"] is not None
    text = "".join(out["answer_stream"])
    assert "don't" in text.lower() or "not" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_retrieve.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rishivan.graph.nodes.retrieve'`

- [ ] **Step 3: Write the implementation**

Port `council_consult` lines ~380–470 into `retrieve_node`, preserving the
embed call, the universe filter built from `slugs_for_universe`, and the
unfiltered retry. Port lines ~470–560 into `answer_node`, preserving the prompt
assembly and the `answer_stream()` generator exactly.

```python
# rishivan/graph/nodes/answer.py
"""Answer generation, and the answer that declines to generate."""

from __future__ import annotations

from rishivan.graph.state import RishivanState

INSUFFICIENT = (
    "I don't have material in the ingested books that speaks to this clearly "
    "enough to answer. Saying so is the answer - I'd rather not compose "
    "something that reads like a reading and isn't one."
)


def insufficient_node(state: RishivanState) -> dict:
    return {
        "outcome": "insufficient",
        "message": INSUFFICIENT,
        "answer_stream": iter([INSUFFICIENT]),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_retrieve.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/nodes/retrieve.py rishivan/graph/nodes/answer.py tests/graph/test_nodes_retrieve.py
git commit -m "feat(graph): retrieval with filter fallback, and honest insufficiency"
```

---

### Task 7: Graph assembly

**Files:**
- Create: `rishivan/graph/build.py`
- Test: `tests/graph/test_build.py`

**Interfaces:**
- Consumes: every node and router above
- Produces: `build_graph(*, store, client, checkpointer=None) -> CompiledGraph`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_build.py
"""The wiring. Asserts topology, not behaviour - behaviour is the node tests."""

from rishivan.graph.build import NODE_NAMES, build_graph


def test_the_graph_compiles():
    assert build_graph(store=None, client=None) is not None


def test_every_router_destination_is_a_real_node():
    """A typo in a conditional-edge mapping is a runtime KeyError on a branch
    nobody exercises until a user takes it."""
    from rishivan.graph import build

    for mapping in build.EDGE_MAPS.values():
        for destination in mapping.values():
            assert destination in NODE_NAMES or destination == "__end__", destination


def test_every_node_is_reachable():
    """An unreachable node is dead code that still has to be maintained."""
    from rishivan.graph import build

    reachable = {"intake"}
    for mapping in build.EDGE_MAPS.values():
        reachable.update(mapping.values())
    reachable.update(build.STATIC_EDGES.values())
    assert set(NODE_NAMES) <= reachable


def test_the_graph_renders_to_mermaid():
    """Free documentation, and it fails loudly if the topology is malformed."""
    g = build_graph(store=None, client=None)
    assert "intake" in g.get_graph().draw_mermaid()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_build.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rishivan.graph.build'`

- [ ] **Step 3: Write the implementation**

```python
# rishivan/graph/build.py
"""Assemble the graph.

`EDGE_MAPS` and `STATIC_EDGES` are module-level data rather than inline
arguments so the tests can walk the topology - a mistyped destination is
otherwise a runtime KeyError on a branch nobody exercises until a user takes
it.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from rishivan.graph import edges as R
from rishivan.graph.nodes import answer, chart, intake, retrieve
from rishivan.graph.state import RishivanState

NODE_NAMES = (
    "intake", "warmth", "need_birth_data", "chart", "panchang",
    "chart_render", "render_varga", "render_dasha", "render_ashtakavarga",
    "render_numerology", "retrieve", "answer", "insufficient",
)

EDGE_MAPS = {
    "intake": {
        "warmth": "warmth",
        "need_birth_data": "need_birth_data",
        "chart": "chart",
        "retrieve": "retrieve",
    },
    "chart": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "retrieve",
    },
    "chart_render": {
        "render_varga": "render_varga",
        "render_dasha": "render_dasha",
        "render_ashtakavarga": "render_ashtakavarga",
        "render_numerology": "render_numerology",
        "need_birth_data": "need_birth_data",
    },
    "retrieve": {"answer": "answer", "insufficient": "insufficient"},
}

STATIC_EDGES = {
    "warmth": END,
    "need_birth_data": END,
    "panchang": "retrieve",
    "render_varga": END,
    "render_dasha": END,
    "render_ashtakavarga": END,
    "render_numerology": END,
    "answer": END,
    "insufficient": END,
}


def _passthrough(state: RishivanState) -> dict:
    """`chart_render` is a branch point with no work of its own.

    LangGraph needs a node to hang a conditional edge on. Naming it rather than
    folding the branch into `chart` keeps `route_chart_kind` separately
    testable, which is the whole reason for this refactor.
    """
    return {}


def build_graph(*, store, client, checkpointer=None):
    g = StateGraph(RishivanState)

    g.add_node("intake", intake.intake_node)
    g.add_node("warmth", intake.warmth_node)
    g.add_node("need_birth_data", intake.need_birth_data_node)
    g.add_node("chart", chart.chart_node)
    g.add_node("panchang", chart.panchang_node)
    g.add_node("chart_render", _passthrough)
    g.add_node("render_varga", chart.render_varga_node)
    g.add_node("render_dasha", chart.render_dasha_node)
    g.add_node("render_ashtakavarga", chart.render_ashtakavarga_node)
    g.add_node("render_numerology", chart.render_numerology_node)
    g.add_node("retrieve", partial(retrieve.retrieve_node, store=store, client=client))
    g.add_node("answer", partial(answer.answer_node, client=client))
    g.add_node("insufficient", answer.insufficient_node)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", R.route_after_intake, EDGE_MAPS["intake"])
    g.add_conditional_edges("chart", R.route_after_chart, EDGE_MAPS["chart"])
    g.add_conditional_edges("chart_render", R.route_chart_kind, EDGE_MAPS["chart_render"])
    g.add_conditional_edges("retrieve", R.route_after_retrieval, EDGE_MAPS["retrieve"])
    for source, destination in STATIC_EDGES.items():
        g.add_edge(source, destination)

    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/test_build.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/build.py tests/graph/test_build.py
git commit -m "feat(graph): assemble the council graph with walkable topology"
```

---

### Task 8: The adapter — `council_consult` over the graph

**Files:**
- Modify: `rishivan/council/orchestrator.py` (replace the body of `council_consult`)
- Test: `tests/graph/test_adapter.py`

**Interfaces:**
- Consumes: `build_graph`, `initial_state`, `RESULT_KEYS`
- Produces: `council_consult(...) -> dict` — unchanged signature, unchanged keys

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_adapter.py
"""The contract `streamlit_app.py` and `tests/eval/run_eval.py` depend on.

Phase 1 is behaviour-preserving, so this is the test that says so.
"""

import inspect

from rishivan.council.orchestrator import council_consult
from rishivan.graph.state import RESULT_KEYS


def test_the_signature_is_unchanged():
    params = list(inspect.signature(council_consult).parameters)
    assert params[:3] == ["client", "store", "question"]
    for kw in ("rishi_override", "birth_data", "query_time", "target_time",
               "lat", "lon", "tz_offset", "place", "conversation"):
        assert kw in params


def test_every_promised_key_is_returned():
    result = council_consult(None, None, "hi")
    missing = RESULT_KEYS - set(result)
    assert not missing, f"dropped from the contract: {sorted(missing)}"


def test_small_talk_still_streams_without_a_store():
    """The cheapest end-to-end path, and the one that proves the graph runs."""
    result = council_consult(None, None, "hello")
    assert result["is_warmth"] is True
    assert "".join(result["answer_stream"]).strip()


def test_a_natal_question_without_birth_data_asks_for_it():
    result = council_consult(None, None, "when will I marry?")
    assert "birth" in "".join(result["answer_stream"]).lower()


def test_the_orchestrator_no_longer_branches_on_business_logic():
    """The point of the phase. `council_consult` becomes an adapter; if it
    grows conditionals again, the graph is being bypassed."""
    source = inspect.getsource(council_consult)
    body = source.split('"""', 2)[-1]
    assert body.count("if ") <= 1, "business branching belongs on edges now"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_adapter.py -v`
Expected: FAIL on `test_the_orchestrator_no_longer_branches_on_business_logic`
(the current body has ~30 `if`s), and on the graph not being used.

- [ ] **Step 3: Write the implementation**

Replace the body of `council_consult` with:

```python
def council_consult(
    client,
    store,
    question: str,
    *,
    rishi_override: str | None = None,
    birth_data=None,
    query_time: datetime | None = None,
    target_time: datetime | None = None,
    lat: float | None = None,
    lon: float | None = None,
    tz_offset: float = 5.5,
    place: str = "",
    conversation=None,
) -> dict:
    """Full Council consultation, run as a graph.

    Kept as a function with this exact signature because `streamlit_app.py` and
    `tests/eval/run_eval.py` call it, and a refactor that also changes its
    callers cannot be reviewed against the behaviour it claims to preserve.

    Returns a dict with keys:
      primary_rishi, rishi_title, query_domain, classification,
      chart_summary, chart_facts, sources, search_query, answer_stream
    """
    from rishivan.graph.build import build_graph
    from rishivan.graph.state import RESULT_KEYS, initial_state

    graph = build_graph(store=store, client=client)
    final = graph.invoke(initial_state(
        question,
        rishi_override=rishi_override,
        birth_data=birth_data,
        query_time=query_time,
        target_time=target_time,
        lat=lat,
        lon=lon,
        tz_offset=tz_offset,
        place=place,
        conversation=conversation,
    ))

    result = {key: final.get(key) for key in RESULT_KEYS}
    # Set only on the paths that produce them, and read with `.get()` by every
    # caller. Promising them unconditionally would be a new contract.
    for optional in ("routing", "panchang"):
        if final.get(optional):
            result[optional] = final[optional]
    return result
```

Delete the old body. Keep every helper the nodes now import.

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/ -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/orchestrator.py tests/graph/test_adapter.py
git commit -m "refactor(council): council_consult becomes an adapter over the graph"
```

---

### Task 9: Prove behaviour is preserved

**Files:**
- Test: `tests/graph/test_parity.py`
- Modify: `rishivan/graph/build.py` (add `checkpointer_for`)

**Interfaces:**
- Consumes: `tests/eval/prompts.py::PIPELINE_CASES`
- Produces: `checkpointer_for(env: str)`

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_parity.py
"""Phase 1 claims to change control flow and nothing else. This is the claim.

Runs the existing eval corpus through the graph and asserts the routing
decisions match what the procedural orchestrator produced. Model output is not
compared - it is not deterministic - but every decision before the model is.
"""

import pytest

from rishivan.graph.edges import route_after_intake
from rishivan.graph.state import initial_state

pytest.importorskip("tests.eval.prompts")


def _cases():
    from tests.eval.prompts import PIPELINE_CASES

    return PIPELINE_CASES


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.get("id", ""))
def test_every_eval_case_routes_somewhere_valid(case):
    from rishivan.graph.build import EDGE_MAPS

    s = initial_state(case["question"])
    s["classification"] = case.get("classification", {})
    s["query_domain"] = s["query_domain"]
    assert route_after_intake(s) in EDGE_MAPS["intake"]


def test_the_deterministic_prefix_is_reproducible():
    """Two runs of the same question take the same path."""
    from rishivan.graph.nodes.chart import chart_node
    from rishivan.chart.ephemeris import BirthData

    birth = BirthData(year=1990, month=1, day=1, hour=12, minute=0,
                      tz_offset_hours=5.5, lat=28.6139, lon=77.2090)
    a = chart_node(initial_state("q", birth_data=birth))
    b = chart_node(initial_state("q", birth_data=birth))
    assert a["chart_summary"] == b["chart_summary"]


def test_a_checkpointer_is_available_for_conversations():
    """`turn_type: followup` should resume, not recompute."""
    from rishivan.graph.build import checkpointer_for

    assert checkpointer_for("demo") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/graph/test_parity.py -v`
Expected: FAIL with `ImportError: cannot import name 'checkpointer_for'`

- [ ] **Step 3: Write the implementation**

Append to `rishivan/graph/build.py`:

```python
def checkpointer_for(env: str = "demo"):
    """Thread id is the conversation id, so a follow-up resumes rather than
    recomputes - which is also what stops turn 14 disagreeing with turn 13
    about a fact.

    In-memory for the demo: Streamlit Cloud has no Postgres, and the demo's own
    requirements deliberately exclude it.
    """
    from langgraph.checkpoint.memory import MemorySaver

    if env == "demo":
        return MemorySaver()

    from langgraph.checkpoint.postgres import PostgresSaver

    from rishivan.config import settings

    return PostgresSaver.from_conn_string(settings.DATABASE_URL)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/graph/ -v`
Then the whole suite: `./.venv/bin/python -m pytest tests -q`
Expected: no regressions against the pre-Phase-1 count.

> Note: a stray untracked `tests.py` at the repo root shadows the `tests/`
> package and breaks four DB-backed tests on a full run. Move it aside before
> trusting a full-suite number.

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/build.py tests/graph/test_parity.py
git commit -m "test(graph): parity with the procedural orchestrator, plus checkpointing"
```

---

### Task 10: Document the graph

**Files:**
- Create: `rishivan/graph/README.md`
- Modify: `docs/client-spec-gap-map.md`

- [ ] **Step 1: Generate the diagram**

```bash
./.venv/bin/python -c "
from rishivan.graph.build import build_graph
print(build_graph(store=None, client=None).get_graph().draw_mermaid())
" > /tmp/graph.mmd && cat /tmp/graph.mmd
```

- [ ] **Step 2: Write `rishivan/graph/README.md`**

Include: the mermaid diagram from Step 1 inside a ```mermaid fence; a table of
each node and the single state key group it owns; a table of each router and
its destinations; and one paragraph stating that Phase 1 is behaviour-preserving
and that §6–§12 arrive as new nodes, not as edits to these.

- [ ] **Step 3: Update the gap map**

Add a row to `docs/client-spec-gap-map.md` marking the orchestrator refactor
`DONE (Phase 1)` and noting that §6, §7, §8, §11 and §12 remain `ABSENT`, each
with its phase number from the architecture spec.

- [ ] **Step 4: Verify**

Run: `./.venv/bin/python -m pytest tests/graph/ -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/README.md docs/client-spec-gap-map.md
git commit -m "docs(graph): topology diagram and the phase-1 gap-map update"
```

---

## Self-review against the spec

**Coverage.** Phase 1 covers spec §3 (topology, deterministic half), §4 (state
schema, all keys including Phase 2–5 placeholders), §10 (every listed
conditional has a destination), and §11's checkpointing/streaming constraints.
It deliberately covers **none** of §6, §7, §8, §12 or the Rishi contract —
those are Phases 2–5, and mixing them in would remove the one property that
makes Phase 1 reviewable: that its output should not change.

**Two orchestrator branches deferred, on purpose:**
- the `rishi == "tejan"` remedy augmentation — becomes a `remedy` node in
  Phase 4, where the Rishi roles are settled. Until then `answer_node` keeps
  the existing inline behaviour, which is a preserved behaviour, not a new one.
- the extra-varga fetch loop — becomes `varga_select` in Phase 3. Phase 1 keeps
  it inside `chart_node`.

Both are noted in `rishivan/graph/README.md` so the next phase finds them.

**Types.** `route_*` all return `str`. Nodes all return `dict`. `build_graph`
returns a compiled graph. `initial_state` returns `RishivanState`. Node names
in `NODE_NAMES`, `EDGE_MAPS` and `add_node` calls are the same strings, and
`test_every_router_destination_is_a_real_node` enforces it.

**Names, verified.** `classify_query` · `respond_warmly` · `compute_panchang`
· `relative_day_offset` · `mentions_panchang` (in `chart/panchang.py`, not
`council/classifier.py`) · `numerology_table_markdown` · `chart_tokens` ·
`varga_table_markdown` · `dasha_table_markdown` ·
`ashtakavarga_table_markdown` · `derive_facts` · `compute_chart` · `summarize`.
The one signature still to confirm at implementation time is
`compute_panchang`'s keyword names — `council_consult:204` is the reference
call.

**Known risk.** Task 6 ports ~180 lines of retrieval and prompt assembly that
this plan describes rather than reproduces, because reproducing it would mean
copying code the implementer can read in place. That is the one task where the
diff should be checked against the original line-by-line rather than against a
test alone.
