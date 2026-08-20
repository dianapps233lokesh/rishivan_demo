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

from rishivan.knowledge.concepts import concepts_of
from rishivan.rag.relevance import domain_relevance

RULE_COLLECTION_SUFFIX = "_rules"
"""Rules live beside the pages, not among them: a page is evidence to read and a rule
is a claim to test, so their similarity scores are not comparable."""

MIN_RELEVANCE = 0.1
"""Floor on coverage relevance. The real gate is coverage itself — a rule whose subject
house lies outside every routed Rishi's §4-11 coverage scores exactly 0 — so this only
discards the marginal tail."""

TIER_WEIGHT_FACTOR = 0.15
"""How much Blueprint §12's tier moves a rule. §8 rule 4 asks for a hierarchy of
evidence, not a veto: a practitioner's rule that is true of the chart is still evidence,
it just yields to a classical one competing for the same slot."""

AFFINITY_WEIGHT = 0.3
"""Weight of the rule's own §15 affinity for the routed domain. Refinement, not a gate:
affinity says what the rule's OUTCOME is about, coverage says what its CONDITION is
about. BPHS 26.74 is a 7th-house rule whose effects span wives, wealth and character, and
affinity is what prefers it for a marriage question over a 7th-house rule about money."""

APPLICATION_BONUS = 0.25
"""Preference for a rule whose `rule_category` matches the question's application type
(Blueprint §4 level 5). A bonus, not a gate: §4-11's protocols run
"promise -> ... -> Dasha", so a timing question still needs the promise as evidence --
it just should not lead with it."""

TOPICAL_WEIGHT = 0.3
"""Weight of the question's wording. Refinement only — it cannot rescue a rule the
coverage gate rejected, which is the point: similarity has no idea what a rule is about."""


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
    domain: str | None = None
    """Which routed client domain claimed this rule, for §21 traceability."""
    school: str = "unknown"
    """Blueprint §4 level 2. Carried so evidence can be grouped and labelled by school:
    §8 rule 5 forbids mixing them silently, and every §4-11 protocol ends in
    "cross-school confirmation" -- so the answer is to label, never to exclude."""
    rule_category: str = "formation"
    """Blueprint §4 level 5: `formation` (natal promise) or `timing` (activation)."""
    tier: str = "S5"
    """Blueprint §12 source tier. Defaults to experimental, never classical: an
    untiered rule must not inherit authority nobody granted it."""
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
            school=payload.get("school") or "unknown",
            rule_category=payload.get("rule_category") or "formation",
            tier=payload.get("tier") or "S5",
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
    routing,
    condition: dict | None,
    affinity: dict,
    query_embedding: list[float],
    rule_vector: list[float],
    rule_category: str = "formation",
    tier: str = "S5",
) -> tuple[float, float, str | None]:
    """`(relevance, score, domain)` for one true rule.

    `relevance` is §4-11 coverage agreement, and it is the gate: 0 means the rule's
    subject house sits outside every routed Rishi's remit, and no amount of similarity
    may resurrect it. `score` orders whatever survives.
    """
    relevance, domain = domain_relevance(concepts_of(condition), routing)
    if relevance <= 0.0 or domain is None:
        return 0.0, 0.0, None

    outcome = float((affinity or {}).get(domain, 0.0) or 0.0) * focus(affinity, domain)
    topical = (
        _cosine(query_embedding, rule_vector)
        if query_embedding and rule_vector
        else 0.0
    )
    # Blueprint §4 level 5: prefer the category the question is asking for.
    from rishivan.council.routing import APPLICATION_RULE_CATEGORY

    wanted = APPLICATION_RULE_CATEGORY.get(
        getattr(routing, "application", "potential"), "formation"
    )
    application = APPLICATION_BONUS * (1.0 if rule_category == wanted else 0.0)
    from rishivan.rag.authority import TIER_WEIGHT

    score = (
        relevance
        + AFFINITY_WEIGHT * outcome
        + TOPICAL_WEIGHT * topical
        + application
        + TIER_WEIGHT_FACTOR * TIER_WEIGHT.get(tier, TIER_WEIGHT["S5"])
    )
    return relevance, score, domain


def rank_true_rules(
    rules,
    query_embedding: list[float],
    *,
    routing,
    limit: int = 10,
    question: str = "",
) -> list[RuleHit]:
    """Order rules already proven true of the chart by relevance to the question.

    Ranking comes after matching, never before. Nominating by similarity first cost
    11 to 14 of 21 true rules on the measured chart: a similarity window has no way to
    prefer rules that happen to be true, so going first caps recall.

    `routing` is a `council.routing.Routing` — the client domains this question belongs
    to (§12). An unsupported question routes nowhere and returns nothing (§20).
    """
    from rishivan.knowledge.match.safety import sensitivities, withhold_reasons

    scored: list[tuple[float, RuleHit]] = []
    for rule in rules:
        affinity = getattr(rule, "rishi_affinity", None) or {}
        relevance, score, domain = rank_score(
            routing, getattr(rule, "condition", None) or {}, affinity,
            query_embedding, getattr(rule, "vector", None) or [],
            getattr(rule, "rule_category", "formation"),
            getattr(rule, "tier", "S5"),
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
        hit.domain = domain
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
    routing,
    limit: int = 10,
    question: str = "",
) -> list[RuleHit]:
    """The whole rule path: match everything, then rank what survived."""
    return rank_true_rules(
        true_rules(store, tokens, with_vectors=True),
        query_embedding,
        routing=routing,
        limit=limit,
        question=question,
    )


def group_by_school(hits: list[RuleHit]) -> dict[str, list[RuleHit]]:
    """Evidence grouped by Blueprint §4 level 2, keeping the order it arrived in.

    §8 rule 5: "Never mix schools silently. If a Jaimini rule is used alongside
    Parashari, label both." Grouping rather than filtering is deliberate -- every §4-11
    protocol ends in "cross-school confirmation", so excluding a school would remove the
    corroboration the documents ask for. What must not happen is two schools merging into
    one undifferentiated claim.
    """
    grouped: dict[str, list[RuleHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.school or "unknown", []).append(hit)
    return grouped
