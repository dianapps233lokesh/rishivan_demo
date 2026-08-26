"""Turn telemetry: what was asked, what was decided, and what was said.

**Written in two halves, because that is genuinely when the two halves exist.**
The `persist` node runs inside the graph and knows everything except the
answer — narration happens outside the graph, after `invoke` returns, so the
prose does not exist yet. `record_answer` attaches it once the stream closes,
along with whatever the verifier found in it.

That second call is also where the verifier earns its keep: a violation is only
useful if somebody can read it later next to the plan it violated.

**Nothing here may take down a reading.** Every function returns a bool and
swallows its own failures. A full disk, an expired Atlas cluster or a network
partition costs the telemetry, never the answer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """The wall clock, and the ONE place in this codebase that reads it.

    Everything astrological takes an explicit `when` - a backtest asks about
    1998 and a Prashna asks about a stated moment, and an engine that quietly
    answers about today is wrong in a way that produces plausible output. But
    "when was this row written" is a fact about the database, not about the
    chart, and it genuinely is now.
    """
    return datetime.now(timezone.utc)


def record_turn(trace: dict, predictions=()) -> bool:
    """Write the deterministic half: everything the graph decided.

    Upserted on `run_id`, so a retried request updates its row rather than
    growing a second one - which matters on a 512 MB tier.
    """
    from rishivan.store import mongo
    from rishivan.store.slim import slim_trace

    turns = mongo.turns()
    if turns is None:
        return False

    document = slim_trace(trace)
    document["created_at"] = _now()
    document["_schema"] = 1

    try:
        turns.update_one(
            {"run_id": document.get("run_id", "")},
            {"$set": document},
            upsert=True,
        )
    except Exception:  # noqa: BLE001
        logger.warning("could not write turn telemetry", exc_info=True)
        return False

    return record_predictions(predictions)


def record_predictions(predictions) -> bool:
    """Upsert the ledger entries. Idempotent on `prediction_id`.

    `$setOnInsert` rather than `$set`: a prediction already resolved must not
    be reset to `open` because the same run was replayed. The ledger is the one
    place where an accidental overwrite destroys the only record of whether we
    were right.
    """
    from rishivan.store import mongo

    rows = list(predictions or ())
    if not rows:
        return True
    collection = mongo.predictions()
    if collection is None:
        return False

    try:
        for prediction in rows:
            payload = prediction.to_dict()
            payload["created_at"] = _now()
            collection.update_one(
                {"prediction_id": payload["prediction_id"]},
                {"$setOnInsert": payload},
                upsert=True,
            )
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not write the prediction ledger", exc_info=True)
        return False


def record_answer(
    run_id: str,
    answer: str,
    *,
    violations=(),
    rishi: str = "",
    thread_id: str = "",
) -> bool:
    """Attach the prose, once it exists, to the turn the graph already wrote."""
    from rishivan.store import mongo

    turns = mongo.turns()
    if turns is None or not run_id:
        return False

    try:
        turns.update_one(
            {"run_id": run_id},
            {"$set": {
                "answer": answer,
                "answer_chars": len(answer or ""),
                "rishi": rishi,
                "thread_id": thread_id,
                "answered_at": _now(),
                "violations": [
                    {"kind": v.kind, "detail": v.detail} for v in violations
                ],
                # Denormalised so "how often did the gate leak" is one query
                # rather than an aggregation over an array.
                "violation_count": len(list(violations)),
            }},
            upsert=False,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.warning("could not attach the answer to its trace", exc_info=True)
        return False


def recent(limit: int = 20) -> list[dict]:
    from rishivan.store import mongo

    turns = mongo.turns()
    if turns is None:
        return []
    try:
        return list(turns.find().sort("created_at", -1).limit(limit))
    except Exception:  # noqa: BLE001
        logger.warning("could not read recent turns", exc_info=True)
        return []


def open_predictions(limit: int = 100) -> list[dict]:
    """What has been predicted and not yet scored."""
    from rishivan.store import mongo

    collection = mongo.predictions()
    if collection is None:
        return []
    try:
        return list(collection.find({"outcome": "open"}).limit(limit))
    except Exception:  # noqa: BLE001
        logger.warning("could not read the prediction ledger", exc_info=True)
        return []


def resolve(prediction_id: str, *, outcome: str, note: str = "") -> bool:
    """Score one prediction. The whole reason the ledger exists."""
    from rishivan.council.ledger import OUTCOMES
    from rishivan.store import mongo

    if outcome not in OUTCOMES:
        raise ValueError(
            f"{outcome!r} is not an outcome; use one of "
            f"{', '.join(sorted(OUTCOMES))}"
        )
    collection = mongo.predictions()
    if collection is None:
        return False
    try:
        result = collection.update_one(
            {"prediction_id": prediction_id},
            {"$set": {"outcome": outcome, "note": note,
                      "resolved_at": _now()}},
        )
        return result.matched_count == 1
    except Exception:  # noqa: BLE001
        logger.warning("could not resolve a prediction", exc_info=True)
        return False
