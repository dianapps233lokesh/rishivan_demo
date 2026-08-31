"""Load the requirements, and be honest about where they came from.

**Three outcomes, and collapsing any two of them is a bug.**

  * Mongo answered with documents -> use them, `Source.MONGO`.
  * Mongo answered with nothing -> that is DATA, not an outage. An operator who
    deliberately emptied the collection gets the built-in catalogue and a
    warning, not silence.
  * Mongo could not be reached -> the built-in catalogue, `Source.BUILTIN`, and
    the UI says so.

`store/mongo.py` opens by saying "nothing in here may take down a reading",
which is right for telemetry and wrong here: telemetry is a byproduct, and this
decides which facts a reading is assembled from. So the swallowing stops at this
boundary. Nothing raises out of `load()` either — a dead cluster must not cost a
reader their answer — but the fallback is always named, never assumed.

Cached per process. The catalogue is read once per turn per question and a
round trip to Atlas on the request path costs a reader real seconds.
"""

from __future__ import annotations

import logging
import threading

from rishivan.council.requirements.types import Requirement, RequirementSet, Source

logger = logging.getLogger(__name__)

_cache: tuple[dict[str, RequirementSet], Source] | None = None
_lock = threading.Lock()


def reset() -> None:
    """Drop the cached catalogue. For tests, and after a seed."""
    global _cache
    with _lock:
        _cache = None


def _document(raw: dict) -> RequirementSet | None:
    """One Mongo document into a `RequirementSet`, or None if it is unusable.

    A malformed document is dropped with a warning rather than raising. One bad
    row hand-edited in Atlas must not take out the other fifty-one, and the
    warning is what stops it being invisible.
    """
    try:
        requires = tuple(
            Requirement(
                key=str(item["key"]),
                step=int(item.get("step", 0)),
                mandatory=bool(item.get("mandatory", False)),
                priority=int(item.get("priority", 2)),
            )
            for item in (raw.get("requires") or [])
            if isinstance(item, dict) and item.get("key")
        )
        return RequirementSet(
            domain=str(raw.get("domain", "")),
            kind=str(raw.get("kind", "")),
            constitution=str(raw.get("constitution", "")),
            requires=requires,
            source=Source.MONGO,
            notes=str(raw.get("notes", "")),
        )
    except Exception:  # noqa: BLE001
        logger.warning("skipping an unusable requirements document: %r",
                       raw.get("_id"), exc_info=True)
        return None


def _from_mongo() -> dict[str, RequirementSet] | None:
    """Every document, or None if the cluster could not be reached.

    The None/empty-dict distinction is the whole point of this function: `{}`
    means the collection is genuinely empty and somebody meant it, `None` means
    we do not know what is in there.
    """
    from rishivan.store import mongo

    if not mongo.is_configured():
        return None
    collection = mongo.requirements()
    if collection is None:
        return None
    try:
        documents = list(collection.find({}))
    except Exception:  # noqa: BLE001
        logger.warning("could not read the requirements collection", exc_info=True)
        return None

    loaded = {}
    for raw in documents:
        entry = _document(raw)
        if entry is not None:
            loaded[entry.doc_id] = entry
    return loaded


def _builtin() -> dict[str, RequirementSet]:
    from rishivan.council.requirements.catalog import catalogue

    return catalogue()


def load(*, refresh: bool = False) -> tuple[dict[str, RequirementSet], Source]:
    """The catalogue and its provenance. Never raises."""
    global _cache
    if _cache is not None and not refresh:
        return _cache

    with _lock:
        if _cache is not None and not refresh:
            return _cache

        from_mongo = _from_mongo()
        if from_mongo is None:
            logger.warning(
                "the requirements collection is unreachable - running on the "
                "built-in catalogue. Readings are still fully specified; edits "
                "made in Mongo are NOT in effect."
            )
            result = (_builtin(), Source.BUILTIN)
        elif not from_mongo:
            logger.warning(
                "the requirements collection is empty - running on the built-in "
                "catalogue. Run `python -m scripts.seed_requirements` to populate it."
            )
            result = (_builtin(), Source.BUILTIN)
        else:
            result = (from_mongo, Source.MONGO)

        _cache = result
        return result


def requirements_for(domain: str, kind: str) -> RequirementSet:
    """The set for one question, falling back along a declared path.

    (domain, kind) -> ("", kind) -> an empty set. The middle step matters: a
    domain nobody has written a row for still gets the whole-chart requirements
    for its question kind, which is a worse reading than a tailored one and a far
    better one than none.
    """
    catalogue, source = load()
    for doc_id in (f"{domain}:{kind}", f":{kind}"):
        entry = catalogue.get(doc_id)
        if entry is not None:
            # The provenance travels with the set, so whatever renders it can
            # say where it came from without asking a second question.
            return RequirementSet(
                domain=entry.domain, kind=entry.kind,
                constitution=entry.constitution, requires=entry.requires,
                source=source, notes=entry.notes,
            )
    logger.warning("no requirements row for %r/%r, and no fallback row either",
                   domain, kind)
    return RequirementSet(domain=domain, kind=kind, source=source)


def as_documents() -> list[dict]:
    """The built-in catalogue as Mongo documents. What the seed script writes."""
    return [
        {
            "_id": entry.doc_id,
            "domain": entry.domain,
            "kind": entry.kind,
            "constitution": entry.constitution,
            "requires": [
                {
                    "key": r.key, "step": r.step,
                    "mandatory": r.mandatory, "priority": r.priority,
                }
                for r in entry.requires
            ],
        }
        for entry in _builtin().values()
    ]
