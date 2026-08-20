"""Embed approved rules into their own Qdrant collection, for the runtime to search.

    uv run python -m scripts.embed_rules --dry-run
    uv run python -m scripts.embed_rules

Only rules satisfying `MATCHABLE_PREDICATE` are embedded, so this cannot publish
anything unapproved. Run it after every approval batch; `--reset` rebuilds from scratch
when a revoked rule would otherwise linger.

**The verse is embedded, not the condition.** The vector's job is to find rules *about*
the question, and the condition is tested exactly afterwards — embedding the condition
would optimise for the one thing embeddings are bad at here.
"""

import argparse
import asyncio
import json
import uuid

from sqlalchemy import select, text

from rishivan.db.session import async_session_factory
from rishivan.models.knowledge.rule import MATCHABLE_PREDICATE, Rule
from rishivan.config import settings
from rishivan.rag.rules import rule_collection_name

RULE_ID_NAMESPACE = uuid.UUID("6f1b0e6a-6c9f-5f6e-9c1a-000000000001")
"""Namespace for deriving a point id from a rule key.

Qdrant point ids must be an unsigned integer or a UUID -- `bphs-gcsharma-vol1:26.1.1` is
rejected outright with a 400. A uuid5 over the rule key is deterministic, so re-embedding a
rule replaces its point instead of adding a twin, which is what makes this script safe to
re-run after every approval batch.
"""


def point_id(rule_key: str) -> str:
    return str(uuid.uuid5(RULE_ID_NAMESPACE, rule_key))


BATCH = 64
"""Embedding requests per call. Vertex accepts batches; 64 keeps a single failure cheap to
retry without making the run chatty."""


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed with the same model the page collection was built from.

    Dimensions must match the existing collection or Qdrant rejects the upsert, which is
    why the model name comes from the shared helper rather than being written here.
    """
    from rishivan.council.client import get_vertex_client, model_name

    client = get_vertex_client()
    model = model_name("vertex", "embed")
    vectors: list[list[float]] = []
    for start in range(0, len(texts), BATCH):
        chunk = texts[start : start + BATCH]
        response = client.models.embed_content(model=model, contents=chunk)
        vectors.extend(embedding.values for embedding in response.embeddings)
        print(f"  embedded {min(start + BATCH, len(texts))}/{len(texts)}", flush=True)
    return vectors


def embedding_text(rule: Rule) -> str:
    """What the vector represents: the verse, its effects, and its domains.

    The source translation carries the classical language a user's question will resemble;
    the effect statements carry the outcome they are asking about. Both matter -- a question
    about "will my wife be sickly" matches the effect, while "what does BPHS say about the
    7th lord" matches the verse.
    """
    source = rule.source or {}
    effects = (rule.effect or {}).get("effects") or []
    outcomes = " ".join(effect.get("statement", "") for effect in effects)
    domains = " ".join(rule.life_domains or [])
    return f"{source.get('translation', '')}\n{outcomes}\n{domains}".strip()


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="embed approved rules into Qdrant")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="drop the rule collection first, so revoked rules disappear",
    )
    args = parser.parse_args(argv)

    async with async_session_factory() as session:
        rules = list(
            (
                await session.execute(select(Rule).where(text(MATCHABLE_PREDICATE)))
            ).scalars()
        )

    print(f"{len(rules)} approved rules to embed")
    if not rules:
        print(
            "nothing approved yet -- run scripts.approve_rules first, or the runtime has "
            "no rules to find"
        )
        return 0

    collection = rule_collection_name(settings.VECTOR_COLLECTION)
    print(f"target collection: {collection}")

    ids = [point_id(rule.rule_key) for rule in rules]
    documents = [embedding_text(rule) for rule in rules]
    metadatas = [
        {
            "rule_key": rule.rule_key,
            # JSON strings, not nested dicts: nested payloads survive round-tripping
            # unevenly across Qdrant client versions, and a silently flattened condition
            # is a rule that stops matching.
            "condition": json.dumps(rule.condition or {}),
            "effects": json.dumps((rule.effect or {}).get("effects") or []),
            "source": json.dumps(rule.source or {}),
            "life_domains": json.dumps(rule.life_domains or []),
            "rishi_affinity": json.dumps(
                (rule.effect or {}).get("rishi_affinity") or {}
            ),
        }
        for rule in rules
    ]

    if args.dry_run:
        print("dry run: not embedding. First document would be:")
        print("  " + documents[0][:200].replace("\n", " / "))
        missing = sum(
            1 for m in metadatas if m["rishi_affinity"] in ("{}", "null", "")
        )
        print(f"  rules with no rishi_affinity: {missing} (these reach no Rishi)")
        return 0

    from rishivan.rag.vector_store import get_vector_store

    store = get_vector_store(collection)
    if args.reset:
        print("resetting collection")
        store.reset()

    vectors = embed_texts(documents)
    store.upsert(ids=ids, embeddings=vectors, documents=documents, metadatas=metadatas)
    print(f"upserted {len(ids)} rules into {collection}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
