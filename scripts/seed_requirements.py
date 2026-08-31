"""Write the built-in requirement catalogue into MongoDB. Read it back to check.

    python -m scripts.seed_requirements --dry-run   # what would be written
    python -m scripts.seed_requirements             # write it
    python -m scripts.seed_requirements --check     # diff Mongo against the code

**Why both carriers exist.** `council/requirements/catalog.py` is the authored
source and the offline fallback; Mongo is the editable copy the deployed app
reads, so a requirement can be changed without a redeploy. They cannot disagree
at birth, only after somebody edits Atlas — which is the entire point, and which
`--check` is for.

Idempotent. Documents are replaced by `_id`, so re-running after editing the
catalogue updates rather than duplicates. It does NOT delete rows Mongo has and
the catalogue does not: a hand-authored row for a domain nobody has coded yet is
somebody's work, and a seed script is a poor place to discover that.
"""

from __future__ import annotations

import argparse
import sys


def _mongo_documents():
    from rishivan.store import mongo

    collection = mongo.requirements()
    if collection is None:
        return None
    return {doc["_id"]: doc for doc in collection.find({})}


def _normalise(doc: dict) -> tuple:
    """A document reduced to what is worth comparing.

    Ordering is not: the catalogue emits requirements sorted, a hand edit in
    Atlas will not be, and reporting that as drift would train whoever reads
    `--check` to ignore it.
    """
    return (
        doc.get("domain", ""), doc.get("kind", ""), doc.get("constitution", ""),
        tuple(sorted(
            (r.get("key", ""), int(r.get("step", 0)),
             bool(r.get("mandatory", False)), int(r.get("priority", 2)))
            for r in (doc.get("requires") or [])
        )),
    )


def check() -> int:
    from rishivan.council.requirements.store import as_documents

    live = _mongo_documents()
    if live is None:
        print("MongoDB is not reachable. The app would run on the built-in "
              "catalogue, which is fully specified — but nothing you edit in "
              "Atlas is in effect.")
        return 2

    builtin = {doc["_id"]: doc for doc in as_documents()}
    missing = sorted(set(builtin) - set(live))
    extra = sorted(set(live) - set(builtin))
    differing = sorted(
        doc_id for doc_id in set(builtin) & set(live)
        if _normalise(builtin[doc_id]) != _normalise(live[doc_id])
    )

    print(f"{len(builtin)} documents in the catalogue, {len(live)} in Mongo")
    for doc_id in missing:
        print(f"  not seeded yet:  {doc_id}")
    for doc_id in extra:
        print(f"  only in Mongo:   {doc_id}  (hand-authored, left alone)")
    for doc_id in differing:
        builtin_keys = {r["key"] for r in builtin[doc_id]["requires"]}
        live_keys = {r["key"] for r in (live[doc_id].get("requires") or [])}
        print(f"  edited in Mongo: {doc_id}")
        for key in sorted(builtin_keys - live_keys):
            print(f"      removed in Mongo: {key}")
        for key in sorted(live_keys - builtin_keys):
            print(f"      added in Mongo:   {key}")
        if builtin_keys == live_keys:
            print("      same keys, different step/priority/mandatory")

    if not (missing or extra or differing):
        print("Mongo matches the built-in catalogue exactly.")
        return 0
    return 1


def seed(*, dry_run: bool) -> int:
    from rishivan.council.requirements.catalog import invalid_keys
    from rishivan.council.requirements.producers import known
    from rishivan.council.requirements.store import as_documents

    bad = invalid_keys()
    if bad:
        # A token the vocabulary does not recognise is a requirement nobody can
        # satisfy and nobody notices. Refusing to seed is the only point at
        # which that is cheap to find.
        print("REFUSING TO SEED — these keys are not valid under "
              "rishivan.astro.vocab:", file=sys.stderr)
        for key in bad:
            print(f"  {key}", file=sys.stderr)
        return 1

    documents = as_documents()
    unproduced = sorted({
        r["key"] for doc in documents for r in doc["requires"] if not known(r["key"])
    })
    if unproduced:
        # A warning, not a refusal. A requirement with no producer is how a
        # protocol step declares itself unavailable, and that is a legitimate
        # state - `prema` step 5 lived there for months.
        print(f"note: {len(unproduced)} key(s) have no producer and will be "
              f"declared unavailable to the model:")
        for key in unproduced:
            print(f"  {key}")

    rows = sum(len(doc["requires"]) for doc in documents)
    print(f"{len(documents)} documents, {rows} requirement rows")
    if dry_run:
        print("--dry-run: nothing written")
        return 0

    from rishivan.store import mongo

    collection = mongo.requirements()
    if collection is None:
        print("MongoDB is not reachable — nothing written.", file=sys.stderr)
        return 2

    from pymongo import ReplaceOne

    result = collection.bulk_write(
        [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in documents],
        ordered=False,
    )
    print(f"upserted {result.upserted_count}, modified {result.modified_count}")

    from rishivan.council.requirements import store
    store.reset()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_requirements")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be written, write nothing")
    parser.add_argument("--check", action="store_true",
                        help="diff what is in Mongo against the built-in catalogue")
    args = parser.parse_args(argv)

    if args.check:
        return check()
    return seed(dry_run=args.dry_run)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
