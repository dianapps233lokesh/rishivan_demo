"""Run the rule engine against this chart, under this question's hierarchy.

**This node is what connects the extracted rule base to a user's question.**
Before it existed, `grep -rn koonji rishivan/graph` found two reads of a state
key nothing wrote, and nothing else: every rule extracted from every book was
unreachable from the product.

Three things it does that `Engine.answer()` does not, which is why it is a node
rather than a call to that method:

  * **The fact set is compiled with the vargas Phase 3 selected**, not the
    six-varga default. The set is built once, so a division not named here can
    never match a rule however the policy scoped it.
  * **The evidence graph is weighted by the hierarchy** (blueprint §12), so a
    D1 house placement outranks a D9 confirmation of it, and a longevity claim
    is held to a corroboration floor a temperament claim is not.
  * **The question gates already ran.** `intake_node` classified, and
    `hierarchy_node` parsed and planned. `Engine.answer` would re-parse and
    re-gate, which makes the graph's routing and the engine's routing two
    things that can disagree about the same question.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState

SERVED_STATUSES = frozenset({"candidate", "production"})
"""Which rules may reach a reader, and the reason this is stated rather than
inherited.

**Every one of the 1,117 extracted rules is `candidate`. None has been promoted
to `production`.** `Engine.read` defaults to production-only, so a reading taken
at that default returns zero candidates - silently, and looking exactly like a
chart the classical material has nothing to say about. That is the worst
available failure: an honest-sounding silence caused by a deployment fact.

So candidates are served, and `reading_is_unreviewed` travels with them. A rule
nobody has reviewed may still be shown; it may not be shown as though somebody
had. When a review pass promotes rules, this set stops mattering and the flag
goes false on its own.
"""

_ENGINE = None


def _engine():
    """The compiled bundle, loaded once.

    `from_rules()` compiles 1,117 rules from YAML. Paying that per request
    would put seconds on the critical path of every chart question. When this
    starts showing up as first-request latency the fix is a content-addressed
    bundle built in CI (`Engine.from_bundle`), not a cleverer cache - the
    artifact serving traffic should be the exact one CI tested.
    """
    global _ENGINE
    if _ENGINE is None:
        from rishivan.koonji.engine import Engine

        _ENGINE = Engine.from_rules()
    return _ENGINE


def koonji_read_node(state: RishivanState) -> dict:
    """Fire the rules, or say plainly that there was no reading."""
    chart = state.get("chart")
    if chart is None:
        return {"reading": None, "reading_is_unreviewed": False}

    hierarchy = state.get("hierarchy")
    plan = state.get("retrieval_plan")
    selection = state.get("vargas")

    try:
        engine = _engine()
        reading = engine.read(
            chart,
            when=state.get("query_time"),
            domains=set(plan.domains) if plan and plan.domains else None,
            schools=set(plan.schools) if plan and plan.schools else None,
            statuses=SERVED_STATUSES,
            min_domain_weight=plan.min_domain_weight if plan else 0.0,
            vargas=selection.selected if selection else None,
            tier_weights=hierarchy.tier_weights if hierarchy else None,
            min_independent=(
                hierarchy.min_independent_sources if hierarchy else None
            ),
        )
    except Exception:  # noqa: BLE001
        # A stale or missing bundle costs the rule half of the answer. Page
        # retrieval is untouched and still grounds a reply. Failing the whole
        # turn here would turn a deployment problem into what reads as a
        # corpus that has nothing to say.
        return {"reading": None, "reading_is_unreviewed": False}

    return {
        "reading": reading,
        "reading_is_unreviewed": any(
            r.status == "candidate" for r in _engine().bundle.rules
        ),
    }
