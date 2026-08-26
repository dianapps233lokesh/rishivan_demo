"""Domain-filtered page retrieval, and Koonji rule matching beside it.

Port of `council_consult:392-535`. Two things here are load-bearing and easy to
lose in a refactor, so they are called out rather than left in the diff:

**Rules run alongside page retrieval, not instead of it.** The approved rule
base is thin, so most questions still match nothing; a reading that silently
returned less because of that would be a regression on the page search that
already works.

**Rules are exact-matched against the chart FIRST, then ranked.** Nominating by
similarity first was measured losing 11 to 14 of the 21 rules true of a test
chart - a similarity window cannot prefer what it has no way of knowing is true.
Matching first makes recall total by construction.
"""

from __future__ import annotations

from datetime import datetime

from rishivan.graph.state import RishivanState

MAX_FACT_QUERIES = None
"""No cap: every chart fact (a full natal chart yields ~30) is used as a search
query against the corpus."""

MAX_PAGES = 20

MAX_MATCHED_RULES = 10
"""Matched rules to put in the prompt.

Bounded because a rule block is prose the model must read before it answers, and
because one verse can fan out into siblings that share a condition: BPHS 26.1
produced six rules for one placement, so an unbounded list would spend the
prompt on near-duplicates."""


def retrieve_node(state: RishivanState, *, vector_store, client) -> dict:
    """Note the parameter name.

    It cannot be `store`: LangGraph injects several parameters *by name* -
    `config`, `store`, `writer`, `runtime` - and a node whose signature has
    `store` gets the framework's long-term-memory store, silently overriding
    whatever the partial bound. That produced `None` here, and the only symptom
    was an AttributeError deep in retrieval.
    """
    from rishivan.council.client import model_name
    from rishivan.council.source_matrix import slugs_for_universe
    from rishivan.rag.retrieve import collect_chart_context, expand_to_page_window

    embed_model = model_name("embed")
    routing = state.get("routing") or {}

    def embed_fn(texts):
        r = client.models.embed_content(model=embed_model, contents=texts)
        return [e.values for e in r.embeddings]

    # Blueprint §4 level 1: retrieve within the universes this question invokes.
    # School is deliberately NOT filtered - every §4-11 protocol ends in
    # "cross-school confirmation".
    domain_filter = sorted(
        slug
        for universe in routing.get("universes", [])
        for slug in slugs_for_universe(universe)
    )

    def search_with_fallback(emb, n=10):
        """A store with no tagged documents must not read as an empty corpus."""
        if domain_filter:
            hits = vector_store.search_filtered(emb, n_results=n, domain_filter=domain_filter)
            if hits:
                return hits
        return vector_store.search(emb, n_results=n)

    search_query = state.get("search_query") or state["question"]
    chart_facts = state.get("chart_facts")

    if chart_facts:
        try:
            context_text, page_groups = collect_chart_context(
                vector_store, embed_fn, search_query, chart_facts,
                domain_filter=domain_filter or None,
                max_queries=MAX_FACT_QUERIES,
                max_pages=MAX_PAGES,
                domain=routing.get("primary"),
            )
        except Exception:  # noqa: BLE001 - fall back to a plain search, not to nothing
            hits = search_with_fallback(embed_fn([search_query])[0])
            context_text, page_groups = (
                expand_to_page_window(vector_store, [h["metadata"] for h in hits])
                if hits else ("", [])
            )
    else:
        hits = search_with_fallback(embed_fn([search_query])[0])
        context_text, page_groups = (
            expand_to_page_window(vector_store, [h["metadata"] for h in hits])
            if hits else ("", [])
        )

    out: dict = {"sources": page_groups, "context_text": context_text}
    out.update(_match_rules(state, embed_fn, search_query, routing))
    return out


def _match_rules(state: RishivanState, embed_fn, search_query: str, routing: dict) -> dict:
    """Step 4b. Wrapped whole in `except Exception` on purpose: a missing or
    stale rule base must degrade to page retrieval, never to no answer.

    **The rules come from the Koonji reading, not from Qdrant.** Both matchers
    existed and they disagreed: Qdrant held rules in the old extractor's format
    and the engine held them in the frame's, so the panel and the answer were
    counting different corpora. Everything the extractor has produced since the
    format changed -- 274 rules -- was invisible in the panel while firing
    correctly in the reading behind it.

    `koonji_read` runs before this node (see `build.STATIC_EDGES`), so the
    reading is already computed and nothing here re-evaluates it.
    """
    chart = state.get("chart")
    if chart is None:
        return {"matched_rules": [], "contributors": [], "contributor_reports": ()}

    out: dict = {}
    try:
        from rishivan.chart.tokens import all_chart_tokens
        from rishivan.council.contributors import gather
        from rishivan.council.routing import merge_supporting, route_question
        from rishivan.graph.nodes.koonji import _engine
        from rishivan.koonji.panel import counts_from_reading, hits_from_reading

        # Dated by the reading, not the wall clock. Dasha tokens are the only
        # ones that move, and matching them against `now` while every other
        # token came from `query_time` would evaluate a Prashna cast for a
        # stated moment against today's periods.
        when = state.get("query_time") or datetime.now()
        tokens = all_chart_tokens(chart, when=when)
        out["chart_tokens"] = tokens

        engine = _engine()
        reading = state.get("reading")
        # The gap between rules true of the chart and rules this Rishi was
        # shown is the specialisation doing its job, and it should be visible
        # rather than implied.
        out.update(counts_from_reading(reading, engine=engine))

        routing_obj = merge_supporting(
            route_question(state["question"]),
            state["classification"].get("supporting_rishis") or [],
        )
        matched = hits_from_reading(
            reading, engine=engine, domain=routing.get("primary"),
            limit=MAX_MATCHED_RULES,
        )
        # `gather` reports what each Rishi computed and wants rules true of the
        # chart, which is exactly the fired set rather than the ten displayed.
        contributors = gather(
            chart, matched, routing=routing_obj,
            question=state["question"], when=state.get("query_time"),
        )
        out["matched_rules"] = matched
        # Two shapes, deliberately. `contributor_context` reads attributes off
        # the reports; the result contract is a list of plain dicts. Collapsing
        # them raised `AttributeError: 'dict' object has no attribute 'rishi'`
        # on every chart reading that reached a live rule store.
        out["contributor_reports"] = tuple(contributors)
        out["contributors"] = [
            {"rishi": c.rishi, "computed": c.computed,
             "rules": len(c.rules), "note": c.note}
            for c in contributors
        ]
        return out
    except Exception:  # noqa: BLE001
        # Whatever was computed before the failure is kept. The counters exist
        # to make a stale index visible, and zeroing them on a partial failure
        # is the silent degradation they were built to prevent.
        out.setdefault("matched_rules", [])
        out.setdefault("contributors", [])
        out.setdefault("contributor_reports", ())
        return out
