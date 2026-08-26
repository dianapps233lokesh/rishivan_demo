"""Write down what happened, in a form somebody can argue with.

`Engine.trace(reading)` already produces the Koonji half of the audit chain -
which rules were considered, which fired, which were cancelled by what, which
could not be decided and why, and the verse behind each one. It is not
reimplemented here. This node composes it with the council half and hands the
whole thing to a sink, along with any dated predictions the plan produced.

**The sink is injected.** It defaults to MongoDB when credentials are present
and to JSONL on disk when they are not, decided per call so adding the
credentials takes effect on the next request rather than the next restart. Not
Postgres: Streamlit Cloud has none and the demo's requirements exclude it.

**A sink failure never fails the turn.** A full disk must not cost the reader
their answer. The trace still reaches state, so it is visible in the result even
when it did not reach storage.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, Optional

from rishivan.graph.state import RishivanState

logger = logging.getLogger(__name__)

TRACE_DIR = Path("traces")
LEDGER_PATH = Path("traces/predictions.jsonl")


def _koonji_trace(state: RishivanState) -> Optional[dict]:
    """The rule engine's own audit chain, or None if it never ran.

    Reached through `graph.nodes.koonji`'s cached engine rather than a fresh
    one: `Engine.trace` reads `self._by_id` and `self.registry`, and a second
    engine built from the same rules would be equal but not identical - and
    would pay the 1,117-rule compile to say so.
    """
    reading = state.get("reading")
    if reading is None:
        return None
    try:
        from rishivan.graph.nodes.koonji import _engine

        return _engine().trace(reading)
    except Exception:  # noqa: BLE001
        logger.warning("could not build the koonji trace", exc_info=True)
        return None


def _plan_dict(plan) -> Optional[dict]:
    if plan is None:
        return None
    return {
        "domain": plan.domain,
        "insufficient": plan.insufficient,
        "disagreement": plan.disagreement,
        "must_say": list(plan.must_say),
        "must_not_say": list(plan.must_not_say),
        "allowed": [
            {
                "claim_id": c.claim_id,
                "band": c.band,
                "confidence": c.confidence,
                "tier": c.tier,
                "citations": list(c.citations),
                "rule_ids": list(c.rule_ids),
                "counter": list(c.counter),
                "corroborated": c.corroborated,
                "window": c.window,
            }
            for c in plan.allowed
        ],
    }


def _council_dict(state: RishivanState) -> dict:
    audit = state.get("audit")
    return {
        "reports": [
            {
                "rishi": r.rishi,
                "score": r.score,
                "confidence": r.confidence,
                "abstained": r.abstained,
                "supporting": [i.statement for i in r.supporting],
                "weakening": [i.statement for i in r.weakening],
                "assumptions": list(r.assumptions),
                "would_change_my_mind": list(r.would_change_my_mind),
            }
            for r in (state.get("reports") or [])
        ],
        "audit": None if audit is None else {
            "findings": [
                {"kind": f.kind, "rishi": f.rishi, "detail": f.detail}
                for f in audit.findings
            ],
            "note": audit.note,
        },
        "convergence": state.get("convergence") or {},
        "revisions": state.get("revisions", 0),
    }


def _vargas_dict(selection) -> Optional[dict]:
    if selection is None:
        return None
    return {
        "selected": list(selection.selected),
        "withheld": [
            {"code": w.code, "reason": w.reason} for w in selection.withheld
        ],
        "notes": list(selection.notes),
    }


def build_trace(state: RishivanState) -> dict:
    """Everything needed to replay and argue with one answer."""
    return {
        "run_id": state.get("run_id", ""),
        "question": state.get("question", ""),
        "outcome": state.get("outcome", ""),
        "domain": state.get("koonji_domain", ""),
        "primary_rishi": state.get("primary_rishi", ""),
        # The drift alarm. A digest that does not reproduce means the
        # calculation stack changed under an answer already given.
        "chart_digest": state.get("chart_digest", ""),
        "unreviewed": bool(state.get("reading_is_unreviewed")),
        "koonji": _koonji_trace(state),
        "council": _council_dict(state),
        "answer_plan": _plan_dict(state.get("answer_plan")),
        "vargas": _vargas_dict(state.get("vargas")),
        "sources": [
            s.get("book_slug") or s.get("document_id")
            for s in (state.get("sources") or [])
            if isinstance(s, dict)
        ],
    }


def mongo_sink(trace: dict, predictions) -> None:
    """Telemetry into MongoDB Atlas. Trimmed first — see `store/slim.py`."""
    from rishivan.store.telemetry import record_turn

    record_turn(trace, predictions)


def default_sink(trace: dict, predictions) -> None:
    """Mongo when it is configured, files otherwise.

    Chosen per call rather than at import, so adding the credentials to
    `secrets.toml` takes effect on the next request instead of the next
    restart — which is what actually happens during a client test round.
    """
    from rishivan.store import mongo

    if mongo.is_configured():
        mongo_sink(trace, predictions)
        return
    jsonl_sink(trace, predictions)


def jsonl_sink(trace: dict, predictions) -> None:
    """The local fallback. One trace per file, predictions in one ledger."""
    from rishivan.council.ledger import Ledger

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    run_id = trace.get("run_id") or "unknown"
    (TRACE_DIR / f"{run_id}.json").write_text(json.dumps(trace, indent=2))
    Ledger(LEDGER_PATH).extend(predictions)


def persist_node(
    state: RishivanState, *, sink: Optional[Callable] = None
) -> dict:
    """Compose the trace, write it, and put it in state either way."""
    from rishivan.council.ledger import predictions_from

    trace = build_trace(state)
    when = state.get("query_time")
    predictions = predictions_from(
        state.get("answer_plan"),
        run_id=state.get("run_id", ""),
        # Passed in, never read from the clock: a Prashna cast for a stated
        # moment and a backtest about 1998 must both be stamped with what they
        # were about, not with today.
        asked_at=when.isoformat() if when is not None else "",
    )

    try:
        (sink or default_sink)(trace, predictions)
    except Exception:  # noqa: BLE001
        # A full disk must not cost the reader their answer. The trace still
        # reaches state, so it is visible in the result even when it did not
        # reach storage.
        logger.warning("could not persist the trace", exc_info=True)

    return {"trace": trace}
