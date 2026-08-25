"""The state every node reads and writes.

One flat TypedDict rather than per-node models, because LangGraph merges partial
dict updates: a node returns only the keys it owns, and that merge is what makes
the Phase 4 parallel fan-out safe.

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
    # -- request identity, written once at intake --------------------------
    run_id: str
    question: str
    rishi_override: str | None
    conversation: Any

    # -- birth inputs, passed straight through -----------------------------
    birth_data: Any
    query_time: datetime | None
    target_time: datetime | None
    lat: float | None
    lon: float | None
    tz_offset: float
    place: str

    # -- intake ------------------------------------------------------------
    classification: dict
    routing: dict
    primary_rishi: str
    rishi_title: str
    query_domain: Any
    outcome: str
    message: str

    # -- chart --------------------------------------------------------------
    chart: Any
    chart_summary: str | None
    chart_facts: list[str] | None
    chart_tokens: dict
    chart_table: str | None
    chart_table_error: str | None
    relevant_chart_tables: dict
    panchang: str | None
    nakshatra_now: dict | None

    # -- §6 diagnosis (Phase 2) ----------------------------------------------
    chart_state: Any
    chart_digest: str
    """A mismatch on recomputation means the calculation stack drifted under
    stored answers. The highest-severity alarm in the system, and the one
    nobody would otherwise notice."""

    # -- Phase 3-5 placeholders. Nodes are added later; state is not. --------
    vargas: Any
    timing: Any
    hierarchy: Any
    reading: Any

    # -- retrieval ------------------------------------------------------------
    search_query: str
    sources: list
    context_text: str
    """The retrieved passage text handed to the prompt.

    Declared here because LangGraph DISCARDS writes to undeclared channels
    silently - no error, no warning. Omitting this key meant `retrieve_node`
    returned the corpus text and the graph threw it away, so every answer was
    generated with an empty context block while the sources panel still
    rendered normally. A silent ungrounding of the whole RAG path, invisible in
    the output. `test_state.py` now walks every node's returns against these
    annotations for exactly this reason."""

    life_domain: str | None
    contributor_reports: tuple
    """The `ContributorReport` objects, kept apart from the `contributors` dict
    list. `prompts.contributor_context` does attribute access
    (`report.computed.items()`); the dict list is the result contract that
    `streamlit_app` and `run_eval` read. One key cannot be both."""

    matched_rules: list
    contributors: list
    rules_true_of_chart: int
    rules_with_timing: int
    rules_running_now: int

    # -- council · the only reduced key ---------------------------------------
    reports: Annotated[list, operator.add]
    audit: Any
    revisions: int

    # -- output ----------------------------------------------------------------
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

Declared rather than inferred, so the adapter's contract test asserts a fact
instead of restating whatever the code happens to produce. `routing` and
`panchang` are set conditionally today and are deliberately NOT in this set -
callers read them with `.get()`, and promising them would be a new contract.
"""


def initial_state(question: str, **kw: Any) -> RishivanState:
    """A run's starting state. Every key the graph reads exists here.

    Defaults are explicit rather than left to `total=False`: a node reading a
    key nobody set gets a KeyError at the worst possible moment, and a missing
    default is invisible until the branch that needs it is taken.
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
        chart_digest="",
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
