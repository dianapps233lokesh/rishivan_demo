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

from rishivan.knowledge.match.engine import satisfies
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
    vector: list[float] = field(default_factory=list)
    sensitivities: set = field(default_factory=set)
    """Categories of claim this rule makes -- death, diagnosis, intimate. Carried so the
    prompt can require a hedge even when the rule is admissible."""
    merged_from: list[str] = field(default_factory=list)
    """Rule keys folded into this one because they share a verse and a condition.

    BPHS 26.60 was extracted as three separate rules -- "adopted son", "purchased son",
    "bereft of his own sons" -- while 26.13 kept all six of its outcomes on one rule. The
    extractor split inconsistently, and on a real chart 17 matching rules turned out to be
    only 10 distinct verses, so 40% of the display budget was repetition.
    """

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


TOPICAL_WEIGHT = 0.6
"""How much the question's wording counts, next to the Rishi's domain ownership.

Domain ownership is a hard statement and comes first; topical similarity is a soft signal.
But it needs real weight rather than a tiebreak, because ownership alone cannot order
anything: every rule touching one of a persona's domains scores 1.0, so a marriage question
returned "honoured by the King" and "lives in foreign lands" ranked equal to "happiness
through wife".
"""


def focus(affinity: dict, domain: str) -> float:
    """How much of this rule is about `domain`, from 0 to 1.

    A rule tagged only "marriage" is more about marriage than one tagged "marriage,
    wealth, career, travel, health" -- and under a plain maximum the two score identically.
    This is the share of the rule's affinity mass sitting on the matched domain, which is
    what separates a specialist rule from a scattered one.
    """
    total = sum(affinity.values()) or 1.0
    return affinity.get(domain, 0.0) / total


def rank_score(
    rishi: str,
    affinity: dict,
    query_embedding: list[float],
    rule_vector: list[float],
) -> tuple[float, float]:
    """(relevance, score) for one true rule.

    `relevance` is the raw domain agreement, kept for display -- it answers "is this this
    Rishi's evidence at all". `score` is what ordering uses, and it multiplies agreement by
    focus before adding topical similarity, so a rule that is squarely about the asked
    domain outranks one that merely mentions it.
    """
    from rishivan.council.domains import RISHI_LIFE_DOMAINS

    weights = RISHI_LIFE_DOMAINS.get(rishi.lower(), {})
    if not weights or not affinity:
        return 0.0, 0.0

    best_agreement = 0.0
    best_focus = 0.0
    for domain, persona_weight in weights.items():
        agreement = persona_weight * float(affinity.get(domain, 0.0) or 0.0)
        if agreement > best_agreement:
            best_agreement = agreement
            best_focus = focus(affinity, domain)

    topical = (
        _cosine(query_embedding, rule_vector)
        if query_embedding and rule_vector
        else 0.0
    )
    return best_agreement, best_agreement * best_focus + TOPICAL_WEIGHT * topical


def rank_true_rules(
    rules,
    query_embedding: list[float],
    *,
    rishi: str,
    limit: int = 10,
    question: str = "",
) -> list[RuleHit]:
    """Rank rules already proven true of the chart, by relevance to the question.

    This inverts the older nominate-then-filter order, and the inversion is the point.
    Measured on a test chart against 204 approved rules of which 21 are true:

        question                   true rules the vector nominated
        "will my wife be healthy"   10 / 21   -- 11 lost
        "will I be wealthy"          6 / 21   -- 14 lost
        "what about my career"       6 / 21   -- 14 lost

    Nominating by similarity spends its window on rules that *read* like the question while
    true rules sit outside it -- it was drawing 72 of 204, over a third of the base, and
    still losing half. Similarity cannot know what is true, so going first caps recall at
    whatever it happens to surface. Exact-match everything, then rank here.
    """
    from rishivan.knowledge.match.safety import sensitivities, withhold_reasons

    scored: list[tuple[float, RuleHit]] = []
    for rule in rules:
        affinity = getattr(rule, "rishi_affinity", None) or {}
        relevance, score = rank_score(
            rishi, affinity, query_embedding, getattr(rule, "vector", None) or []
        )
        if relevance < MIN_RELEVANCE:
            continue
        hit = rule if isinstance(rule, RuleHit) else RuleHit(
            rule_key=rule.rule_key,
            condition=getattr(rule, "condition", None) or {},
            effects=getattr(rule, "effects", None) or [],
            source=getattr(rule, "source", None) or {},
            life_domains=getattr(rule, "life_domains", None) or [],
            relevance=relevance,
        )
        hit.relevance = relevance
        # A rule predicting the manner of the querent's death is wrong on a question
        # about marriage before any question of tone arises. Eight Rishis §9.
        if withhold_reasons(hit, question):
            continue
        hit.sensitivities = sensitivities(hit)
        scored.append((score, hit))

    scored.sort(key=lambda row: -row[0])
    return [hit for _, hit in scored[:limit]]


def _condition_signature(condition: dict) -> str:
    """A stable identity for a condition, so siblings can be recognised.

    Sorted keys because two rules extracted from one verse can serialise the same atoms in
    different orders -- the model does not preserve field order -- and an order-sensitive
    signature would treat identical conditions as distinct.
    """
    return json.dumps(condition, sort_keys=True)


def merge_siblings(hits: list[RuleHit]) -> list[RuleHit]:
    """Fold rules that share a verse AND a condition into one, keeping every effect.

    They are the same claim about the same chart, stated once per outcome. BPHS 26.60 was
    extracted as three rules -- "adopted son", "purchased son", "bereft of his own sons" --
    while 26.13 kept all six of its outcomes on one rule; the extractor split
    inconsistently. On a real chart 17 matching rules proved to be only 10 distinct verses,
    so 40% of the display budget was repetition, and to a reader it looks like the book
    insisting rather than one verse being quoted once.

    Grouped on (verse, condition) rather than verse alone: one verse can legitimately hold
    several *different* conditions, as BPHS 15.1-2 does, and those must stay separate.
    """
    merged: dict[tuple, RuleHit] = {}
    for hit in hits:
        key = (
            hit.source.get("chapter"),
            hit.source.get("verse_ref"),
            _condition_signature(hit.condition),
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = hit
            continue
        seen = {
            (effect.get("polarity"), effect.get("statement"))
            for effect in existing.effects
        }
        for effect in hit.effects:
            if (effect.get("polarity"), effect.get("statement")) not in seen:
                existing.effects.append(effect)
        existing.merged_from.append(hit.rule_key)
        # The union of what the siblings were about: keeping only one sibling's affinity
        # would narrow the merged rule's reach for no reason.
        for domain, weight in (hit.rishi_affinity or {}).items():
            existing.rishi_affinity[domain] = max(
                existing.rishi_affinity.get(domain, 0.0), weight
            )
        for domain in hit.life_domains:
            if domain not in existing.life_domains:
                existing.life_domains.append(domain)
    return list(merged.values())


def true_rules(store, tokens: dict, *, with_vectors: bool = False) -> list[RuleHit]:
    """Every approved rule that applies to this chart. No similarity involved.

    `applies` rather than `satisfies`: a rule whose exception holds for this chart is one
    the source itself cancels, and presenting it would assert what the book denies.

    Scrolls the whole collection. At 204 rules that is one request; at 50,000 the caller
    should cache the scroll and re-run it per approval batch rather than per question,
    because the payloads change only when a reviewer approves something.
    """
    from rishivan.knowledge.match.engine import applies

    try:
        try:
            points = store.all_points(with_vectors=with_vectors)
        except TypeError:
            # A store predating the with_vectors argument. The retry has to sit INSIDE the
            # outer guard: as a bare handler it let a ConnectionError escape and take down
            # the whole answer, which is exactly what this function exists to prevent.
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
        hit.vector = point.get("vector") or []
        hits.append(hit)
    return merge_siblings(hits)


def rules_for_question(
    store,
    query_embedding: list[float],
    *,
    tokens: dict,
    rishi: str,
    limit: int = 10,
    question: str = "",
) -> list[RuleHit]:
    """The whole rule path: match everything, then rank what survived.

    Replaces `match_rules`. The difference is recall: nominating by similarity first lost
    11 to 14 of 21 true rules on the measured chart, because a similarity window has no way
    to prefer rules that happen to be true.
    """
    return rank_true_rules(
        true_rules(store, tokens, with_vectors=True),
        query_embedding,
        rishi=rishi,
        limit=limit,
        question=question,
    )
