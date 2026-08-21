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
from rishivan.council.source_matrix import authority_tier
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
"""Documents per request, as an upper bound. The binding constraint is tokens."""

TOKEN_BUDGET = 16000
"""Estimated input tokens per embedding request.

`text-embedding-004` accepts 20,000 tokens PER REQUEST, summed across the batch --
not per document. Batching by count alone worked at 376 rules and failed at 1,046 with
`input token count is 20191 but the model supports up to 20000`, after `--reset` had
already emptied the collection.

16,000 rather than 20,000 because the estimate below is chars/4 and real tokenisation
varies; the headroom is what stops a marginal batch from failing the whole run.
"""


def estimated_tokens(text: str) -> int:
    """Rough token count. Four characters per token is the usual English approximation,
    and a deliberate over-estimate is the safe direction here."""
    return max(1, len(text) // 4 + 1)


def token_batches(texts: list[str], budget: int):
    """Group `texts` into request-sized batches, in order.

    Order is preserved because the caller zips the returned vectors back against the
    rules by position -- a reordered batch would attach every embedding to the wrong
    rule. A single text over budget is yielded alone rather than dropped or truncated:
    the API may still reject it, which is a visible failure on one rule instead of a
    silently lost batch.
    """
    batch: list[str] = []
    total = 0
    for text in texts:
        cost = estimated_tokens(text)
        if batch and (total + cost > budget or len(batch) >= BATCH):
            yield batch
            batch, total = [], 0
        batch.append(text)
        total += cost
    if batch:
        yield batch
"""Embedding requests per call. Vertex accepts batches; 64 keeps a single failure cheap to
retry without making the run chatty."""


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed with the same model the page collection was built from.

    Dimensions must match the existing collection or Qdrant rejects the upsert, which is
    why the model name comes from the shared helper rather than being written here.
    """
    from rishivan.council.client import get_vertex_client, model_name

    client = get_vertex_client()
    model = model_name("embed")
    vectors: list[list[float]] = []
    for batch in token_batches(texts, TOKEN_BUDGET):
        response = client.models.embed_content(model=model, contents=batch)
        vectors.extend(embedding.values for embedding in response.embeddings)
        print(f"  embedded {len(vectors)}/{len(texts)}", flush=True)
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
            # Blueprint §6 lists MODIFIERS and EXCEPTIONS as Koonji fields, and
            # `rag.rules.true_rules` reads both to decide whether the source itself
            # cancels a rule for this chart. They were stored in Postgres and dropped
            # here, so `applies()` silently degenerated to `satisfies()` in production.
            "modifiers": json.dumps((rule.effect or {}).get("modifiers") or []),
            "exceptions": json.dumps((rule.effect or {}).get("exceptions") or []),
            # BP §6 lists REMEDIES alongside MODIFIERS and EXCEPTIONS. Compiled onto the
            # rule by `knowledge/compile/persist.py` and stored in Postgres, but never
            # published here -- so no consumer could reach it.
            "remedies": json.dumps((rule.effect or {}).get("remedies") or []),
            # BP §4 level 2 and §8 rule 5: "never mix schools silently -- label both".
            # Carried so an answer can group its evidence by school rather than pooling
            # Parashari and Prashna into one indistinguishable claim.
            "school": rule.school or "unknown",
            # BP §4 level 5: potential vs timing. A "when" question and a "whether"
            # question are different reasoning problems (§8 rule 2).
            "rule_category": (rule.effect or {}).get("rule_category") or "formation",
            # The atoms that say WHEN the promise fires -- 393 rules carry them, 343 of
            # category `timing`. Compiled and stored in Postgres from the first
            # extraction and never published here, so no consumer could tell a running
            # period from a dormant one and every "when" question was answered from the
            # promise alone. Fourth field lost at this boundary after `modifiers`,
            # `exceptions` and `remedies`.
            "activation": json.dumps(
                ((rule.effect or {}).get("timing") or {}).get("activation_factors")
                or {}
            ),
            # BP §12 tier, for §8 rule 4's hierarchy of evidence. Derived from the
            # rule's own book rather than stored on `rule`, which has no tier column --
            # this repo does not own that schema.
            "tier": authority_tier((rule.source or {}).get("book_slug")),
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
