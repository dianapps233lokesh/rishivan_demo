"""The approved rule base as the runtime sees it, held in Qdrant.

Qdrant stores the rules and ranks them; it never decides whether one is true.
Similarity cannot represent truth over discrete tokens — measured on
`text-embedding-004` for the chart "the 7th lord is in the 6th house":

    0.8434  "the 7th lord is placed in the 5th house"               FALSE, ranked 1st
    0.8396  "the 7th lord is placed in the 6th, 8th or 12th house"  TRUE,  ranked 2nd
    0.8277  "the 7th lord is NOT placed in the 6th, 8th or 12th"    FALSE, the negation

One house's difference is noise in embedding space and a flip in truth value, and
chapter 26 alone holds 128 rules that differ only by two digits. So `applies()` from
the knowledge layer is imported rather than reimplemented — a second evaluator would
be a second thing to drift.
"""

import json
from dataclasses import dataclass, field

from rishivan.council.domains import rule_relevance

RULE_COLLECTION_SUFFIX = "_rules"
"""Rules live beside the pages, not among them: a page is evidence to read and a rule
is a claim to test, so their similarity scores are not comparable."""

MIN_RELEVANCE = 0.3
"""Below this a rule is not this Rishi's evidence. Matches `DOMAIN_LOW`; at 0.0 any
Rishi may cite any rule, which dissolves the specialisation."""

TOPICAL_WEIGHT = 0.6
"""Weight of question wording against the Rishi's domain ownership. Ownership leads,
but cannot order anything on its own — every rule touching a persona's domain scores
1.0, which once ranked "honoured by the King" level with "happiness through wife"."""


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
    """Claim categories — death, diagnosis, intimate — so the prompt can require a
    hedge even when the rule is admissible."""
    merged_from: list[str] = field(default_factory=list)
    """Rule keys folded in by `merge_siblings`."""

    @property
    def citation(self) -> str:
        chapter = self.source.get("chapter", "?")
        verse = self.source.get("verse_ref", "?")
        return f"BPHS {chapter}.{verse}"


def rule_collection_name(page_collection: str) -> str:
    return f"{page_collection}{RULE_COLLECTION_SUFFIX}"


def _payload_to_hit(payload: dict, relevance: float) -> RuleHit | None:
    """Rebuild a rule from its Qdrant payload, or None if it will not parse.

    Nested dicts round-trip unevenly across client versions, so `condition`,
    `effects` and `source` travel as JSON strings. One corrupt point must not take
    down an answer, hence None rather than a raise.
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


def _cosine(left: list[float], right: list[float]) -> float:
    """Similarity between two embeddings. Four lines, so no numpy on the request path."""
    dot = sum(a * b for a, b in zip(left, right))
    norm = (sum(a * a for a in left) ** 0.5) * (sum(b * b for b in right) ** 0.5)
    return dot / norm if norm else 0.0


def focus(affinity: dict, domain: str) -> float:
    """Share of a rule's affinity mass sitting on `domain`, 0 to 1.

    Separates a specialist rule from a scattered one: tagged "marriage" alone beats
    tagged "marriage, wealth, career, travel, health", which a plain maximum ties.
    """
    total = sum(affinity.values()) or 1.0
    return affinity.get(domain, 0.0) / total


def rank_score(
    rishi: str,
    affinity: dict,
    query_embedding: list[float],
    rule_vector: list[float],
) -> tuple[float, float]:
    """`(relevance, score)` for one true rule.

    `relevance` is raw domain agreement, kept for display. `score` orders, and
    multiplies agreement by focus before adding topical similarity.
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
    """Order rules already proven true of the chart by relevance to the question.

    Ranking comes after matching, never before. Nominating by similarity first cost
    11 to 14 of 21 true rules on the measured chart: a similarity window has no way to
    prefer rules that happen to be true, so going first caps recall.
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
    """Stable identity for a condition. Sorted keys: the model does not preserve field
    order, so an order-sensitive signature would split identical conditions."""
    return json.dumps(condition, sort_keys=True)


def merge_siblings(hits: list[RuleHit]) -> list[RuleHit]:
    """Fold rules sharing a verse AND a condition into one, keeping every effect.

    They are one claim stated once per outcome — the extractor split inconsistently,
    giving BPHS 26.60 three rules and 26.13 one with six effects. On a real chart 17
    matches were only 10 distinct verses.

    Grouped on (verse, condition), not verse alone: one verse can hold several
    genuinely different conditions, as BPHS 15.1-2 does.
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
        # The union of what the siblings were about; keeping one sibling's affinity
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

    `applies` rather than `satisfies`: a rule whose exception holds is one the source
    itself cancels, and presenting it would assert what the book denies.

    Scrolls the whole collection — one request at 204 rules. At 50,000 the caller
    should cache the scroll per approval batch rather than per question.
    """
    from rishivan.knowledge.match.engine import applies

    try:
        try:
            points = store.all_points(with_vectors=with_vectors)
        except TypeError:
            # A store predating `with_vectors`. The retry sits INSIDE the outer guard:
            # as a bare handler it let ConnectionError escape and kill the answer.
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
    """The whole rule path: match everything, then rank what survived."""
    return rank_true_rules(
        true_rules(store, tokens, with_vectors=True),
        query_embedding,
        rishi=rishi,
        limit=limit,
        question=question,
    )
