"""Blueprint §12: settle what kind of question this is, once, deterministically.

Everything downstream keys off this node's `koonji_domain`: which divisional
charts may speak, which rules the index admits, how a firing is weighted, and
which Rishis are invited. Running it once and writing the answer to state is
what stops four nodes each guessing separately - which is not hypothetical.
Before this node existed, `varga_select` and `dasha_windows` both read
`routing["koonji_domains"]`, a key nothing in the graph ever wrote, and both
silently fell back to a default on every request.

**Deterministic, and deliberately model-free.** The domain comes from
`koonji/router.py`'s keyword table, which is a table a reviewer can read and
correct. A classifier call here would be one more thing to be irreproducible
about, and the classifier already ran at intake for a different purpose.

Placed after the chart because the chart costs an ephemeris call and this does
not - but it reads nothing from the chart, so if a later phase wants it earlier,
it moves without argument.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState


def hierarchy_node(state: RishivanState) -> dict:
    """Parse the question, pick its evidence hierarchy, plan the retrieval."""
    from rishivan.council.hierarchy import DEFAULT_DOMAIN, hierarchy_for
    from rishivan.koonji.router import parse, retrieval_plan

    when = state.get("query_time")
    spec = parse(state["question"], now=when)

    # First rather than all: the hierarchy is a single table row, and a
    # question routed to three domains is primarily about the first. The other
    # two survive in `spec.routing.domains` and reach the index filter through
    # `retrieval_plan`, so nothing is discarded - only the *weighting* commits
    # to one subject.
    domains = spec.routing.domains
    domain = domains[0] if domains else DEFAULT_DOMAIN

    return {
        "spec": spec,
        "koonji_domain": domain,
        "hierarchy": hierarchy_for(domain),
        "retrieval_plan": retrieval_plan(spec, when=when),
    }
