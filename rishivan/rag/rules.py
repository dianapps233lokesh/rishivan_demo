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
"""How many vector candidates to fetch per rule wanted, in the legacy nominate-first path.

Kept only for `match_rules`, which is superseded. See `rank_true_rules` for why.
"""


@dataclass
class RuleHit:
    rule_key: str
    condition: dict
    effects: list[dict]
    source: dict
    relevance: float
    life_domains: list[str] = field(default_factory=list)
    rishi_affinity: dict = field(default_factory=dict)

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


def _cosine(left: list[float], right: list[float]) -> float:
    """Similarity between two embeddings, for RANKING rules already known to be true.

    Written here rather than pulled from a library because it is four lines and adding a
    numpy dependency to the Streamlit request path for four lines is a bad trade.
    """
    dot = sum(a * b for a, b in zip(left, right))
    norm = (sum(a * a for a in left) ** 0.5) * (sum(b * b for b in right) ** 0.5)
    return dot / norm if norm else 0.0


def rank_true_rules(
    rules,
    query_embedding: list[float],
    *,
    rishi: str,
    limit: int = 10,
    embeddings: dict[str, list[float]] | None = None,
) -> list[RuleHit]:
    """Rank rules already proven true of the chart, by relevance to the question.

    This inverts `match_rules`, and the inversion is the whole point. Measured on the
    Mumbai test chart against 204 approved rules, of which **21 are true**:

        question                  true rules the vector nominated
        "will my wife be healthy"  10 / 21   -- 11 lost
        "will I be wealthy"         6 / 21   -- 14 lost
        "what about my career"      6 / 21   -- 14 lost

    Nominating by similarity first spends its window on rules that *read* like the question
    while true rules sit outside it -- and it was nominating 72 of 204, over a third of the
    base, and still losing half. Similarity cannot know what is true, so letting it go first
    caps recall at whatever it happens to surface.

    So: exact-match everything first (the caller does that -- it is one indexed query), then
    rank the survivors here. Recall becomes total by construction, and ranking 21 known-true
    rules by topic is a far easier problem than retrieving from 204 by similarity.

    `embeddings` maps rule_key -> vector, for ordering by topical fit. Without it the order
    falls back to Rishi relevance alone, which is coarse but never wrong -- many rules tie
    at 1.0, and a stable sort keeps the caller's order within a tie.
    """
    scored: list[tuple[float, float, RuleHit]] = []
    for rule in rules:
        affinity = getattr(rule, "rishi_affinity", None) or {}
        relevance = rule_relevance(rishi, affinity)
        if relevance < MIN_RELEVANCE:
            continue
        hit = RuleHit(
            rule_key=rule.rule_key,
            condition=getattr(rule, "condition", None) or {},
            effects=getattr(rule, "effects", None) or [],
            source=getattr(rule, "source", None) or {},
            life_domains=getattr(rule, "life_domains", None) or [],
            relevance=relevance,
        )
        vector = (embeddings or {}).get(rule.rule_key)
        topical = _cosine(query_embedding, vector) if vector else 0.0
        scored.append((relevance, topical, hit))

    # Rishi relevance first because it is a hard statement about ownership; topical
    # similarity second because it is a soft signal and only meaningful within a tier.
    scored.sort(key=lambda row: (-row[0], -row[1]))
    return [hit for _, _, hit in scored[:limit]]


def true_rules(store, tokens: dict) -> list[RuleHit]:
    """Every approved rule that applies to this chart. No similarity involved.

    `applies` rather than `satisfies`: a rule whose exception holds for this chart is one
    the source itself cancels, and presenting it would assert what the book denies.

    Scrolls the whole collection. At 204 rules that is one request; at 50,000 the caller
    should cache the scroll and re-run it per approval batch rather than per question,
    because the payloads change only when a reviewer approves something.
    """
    from app.knowledge.match.engine import applies

    try:
        points = store.all_points()
    except Exception:  # noqa: BLE001 - an unreachable rule store must not break an answer
        return []

    hits: list[RuleHit] = []
    for point in points:
        payload = point.get("metadata") or {}
        hit = _payload_to_hit(payload, relevance=0.0)
        if hit is None:
            continue
        rule = {
            "condition": hit.condition,
            "exceptions": json.loads(payload.get("exceptions") or "[]"),
            "modifiers": json.loads(payload.get("modifiers") or "[]"),
        }
        if not applies(rule, tokens):
            continue
        hit.rishi_affinity = json.loads(payload.get("rishi_affinity") or "{}")
        hits.append(hit)
    return hits


def rules_for_question(
    store,
    query_embedding: list[float],
    *,
    tokens: dict,
    rishi: str,
    limit: int = 10,
) -> list[RuleHit]:
    """The whole rule path: match everything, then rank what survived.

    Replaces `match_rules`. The difference is recall: nominating by similarity first lost
    11 to 14 of 21 true rules on the measured chart, because a similarity window has no way
    to prefer rules that happen to be true.
    """
    return rank_true_rules(
        true_rules(store, tokens),
        query_embedding,
        rishi=rishi,
        limit=limit,
    )
