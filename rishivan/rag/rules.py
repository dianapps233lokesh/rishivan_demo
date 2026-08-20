"""The runtime's view of the approved rule base, held in the vector store.

Two problems solved by one decision. The answering path has no database -- it is Qdrant
plus Swiss Ephemeris, and a `grep` for SQLAlchemy across `rishivan/` returns nothing -- so
rules had to reach it somehow. And rules need to be *found* before they can be tested,
because a chart satisfies a few hundred rules across a whole corpus and only a handful are
about what the user asked.

So Qdrant holds the rules, and the two jobs are split:

**Vector search decides relevance.** "Will I be wealthy" should surface wealth rules. That
is a similarity question and embeddings answer it well.

**Exact evaluation decides truth.** Whether a rule *applies to this chart* is a boolean
over discrete tokens, and similarity cannot represent it. Measured on `text-embedding-004`
against the real corpus:

    chart: "the 7th lord is in the 6th house"
      0.8434  "the 7th lord is placed in the 5th house"              <- FALSE, ranked 1st
      0.8396  "the 7th lord is placed in the 6th, 8th or 12th house" <- TRUE,  ranked 2nd
      0.8277  "the 7th lord is NOT placed in the 6th, 8th or 12th"   <- FALSE, and it is
                                                                        the negation

The wrong rule outranks the right one, and a rule's own negation scores within 0.02 of it.
One house's difference is a rounding error in embedding space and a total flip in truth
value -- and chapter 26 alone contributes 128 rules that differ only by two digits. This is
the failure Blueprint §11 names: "A vector database alone cannot reliably represent a
complex rule system."

So `satisfies()` from the knowledge layer is imported rather than reimplemented, and it
runs over the payload after retrieval. A second evaluator would be a second thing to
drift, and a drifted evaluator produces confidently wrong readings.
"""

import json
from dataclasses import dataclass, field

from app.knowledge.match.engine import satisfies
from rishivan.council.domains import rule_relevance

RULE_COLLECTION_SUFFIX = "_rules"
"""The rule collection sits beside the page collection rather than inside it. Mixing them
would let a page hit and a rule hit compete on the same similarity score, and they are not
comparable: a page is evidence to read, a rule is a claim to test."""

MIN_RELEVANCE = 0.3
"""Below this a rule is not this Rishi's evidence.

Matches `DOMAIN_LOW`: a persona may reach adjacent material, but not material it has no
stated relationship to. Set to 0.0 and any Rishi can cite any rule, which dissolves the
specialisation the client's whole design rests on.
"""

CANDIDATE_MULTIPLIER = 6
"""How many vector candidates to fetch per rule wanted.

Retrieval is by topical similarity and the filter is exact, so most candidates fail the
condition. Fetching only `limit` would return almost nothing: on a real chart roughly 10%
of the rule base is satisfied, so the multiplier buys the exact filter something to work
with. Not unbounded, because each candidate is a payload to deserialise.
"""


@dataclass
class RuleHit:
    rule_key: str
    condition: dict
    effects: list[dict]
    source: dict
    relevance: float
    life_domains: list[str] = field(default_factory=list)

    @property
    def citation(self) -> str:
        chapter = self.source.get("chapter", "?")
        verse = self.source.get("verse_ref", "?")
        return f"BPHS {chapter}.{verse}"


def rule_collection_name(page_collection: str) -> str:
    return f"{page_collection}{RULE_COLLECTION_SUFFIX}"


def _payload_to_hit(payload: dict, relevance: float) -> RuleHit | None:
    """Rebuild a rule from its Qdrant payload.

    Qdrant payloads are flat-ish, and nested dicts survive round-tripping unevenly across
    client versions, so `condition` / `effects` / `source` travel as JSON strings and are
    parsed here. A payload that will not parse is skipped rather than raised: one corrupt
    point must not take down an answer.
    """
    try:
        return RuleHit(
            rule_key=payload["rule_key"],
            condition=json.loads(payload["condition"]),
            effects=json.loads(payload.get("effects") or "[]"),
            source=json.loads(payload.get("source") or "{}"),
            life_domains=json.loads(payload.get("life_domains") or "[]"),
            relevance=relevance,
        )
    except (KeyError, TypeError, ValueError):
        return None


def match_rules(
    store,
    query_embedding: list[float],
    *,
    tokens: dict,
    rishi: str,
    limit: int = 12,
) -> list[RuleHit]:
    """Rules that are about the question AND true of this chart, strongest first.

    `store` is a `VectorStore` already pointed at the rule collection. Returns [] when the
    collection is absent, so a runtime with no rule base degrades to page retrieval instead
    of failing.
    """
    try:
        if not store.exists():
            return []
        candidates = store.search(query_embedding, limit * CANDIDATE_MULTIPLIER)
    except Exception:  # noqa: BLE001 - an unreachable rule store must not break an answer
        return []

    hits: list[RuleHit] = []
    for candidate in candidates:
        payload = candidate.get("metadata") or {}
        relevance = rule_relevance(rishi, json.loads(payload.get("rishi_affinity") or "{}"))
        if relevance < MIN_RELEVANCE:
            continue
        hit = _payload_to_hit(payload, relevance)
        if hit is None or not satisfies(hit.condition, tokens):
            continue
        hits.append(hit)
        if len(hits) >= limit:
            break

    hits.sort(key=lambda hit: -hit.relevance)
    return hits
