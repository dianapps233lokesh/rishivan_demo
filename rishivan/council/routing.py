"""Question -> client life domains. Eight Rishis §1 and §12.

§1 puts an intent classifier ahead of a primary Rishi and its secondaries; §12 gives
thirteen worked examples of the result. This module is the deterministic half of that:
the keyword taxonomy §14 calls "every question type the Rishi can answer", read straight
off each §4-11 section's "Questions it owns" list.

Deliberately not a model call. The persona routing already costs one, and this decides
which *coverage sets* apply -- a step that must be reproducible, because it gates which
rules may reach the answer. It also gives §18's "routing accuracy" something to measure
against §12's table.

`primary` is None when nothing matches, which §20 requires: "Unsupported questions must
be surfaced as unsupported rather than hallucinated."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

QUESTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    # §4 -- "Who am I? What is my personality? ... What are my major life themes?"
    "atma": (
        "who am i", "personality", "my strength", "my strengths", "strengths",
        "weakness",
        "motivates me", "my talent", "talents", "tendencies", "life direction",
        "life theme", "life themes", "self-development", "inclination",
        "what kind of person", "my nature", "temperament", "successful period",
        "most successful", "my life will be", "character",
    ),
    # §5 -- "Will I marry? When? What kind of spouse? ... Compatibility?"
    "prema": (
        "marry", "marriage", "married", "spouse", "wife", "husband", "partner",
        "relationship", "relationships", "love", "romance", "compatibility",
        "separation", "divorce", "remarriage", "in-laws", "girlfriend", "boyfriend",
    ),
    # §6 -- "Will I be wealthy? ... Income capacity? Savings? Assets?"
    "artha": (
        "wealth", "wealthy", "rich", "billionaire", "millionaire", "money",
        "income", "savings", "asset", "assets", "financial", "finances", "profit",
        "inheritance", "speculation", "passive income", "prosperity", "earn",
    ),
    # §7 -- "What career suits me? Job or business? ... Promotions?"
    "karma": (
        "career", "profession", "job", "business", "industry", "leadership",
        "entrepreneur", "entrepreneurship", "promotion", "promotions", "employment",
        "reputation", "authority", "recognition", "work", "occupation", "startup",
        "my company", "office",
    ),
    # §8 -- "Family life? Parents? Mother? Father? Siblings? ... Children?"
    "vansh": (
        "children", "child", "son", "daughter", "progeny", "childbirth", "family",
        "parents", "mother", "father", "sibling", "siblings", "brother", "sister",
        "lineage", "descendants", "family conflict",
    ),
    # §9 -- "Traditional vitality indicators? Strong/weak constitution?"
    "aarogya": (
        "health", "healthy", "vitality", "constitution", "illness", "disease",
        "recovery", "resilience", "body", "wellbeing", "well-being", "longevity",
        "how long will i live", "lifespan", "immunity", "energy levels",
    ),
    # §10 -- "Foreign travel? Foreign settlement? Migration? Relocation? Property?"
    "yatra": (
        "travel", "abroad", "foreign", "settle", "settlement", "migration",
        "migrate", "relocation", "relocate", "move", "moving", "property",
        "real estate", "residence", "house purchase", "land", "vehicle",
        "journey", "transition",
    ),
    # §11 -- "What is my Dharma? ... Spiritual path? Moksha themes?"
    "dharma": (
        "dharma", "life purpose", "my purpose", "spiritual", "spirituality",
        "moksha", "liberation", "meditation", "karma means", "philosophical",
        "bhagavad gita", "gita", "shloka", "rebirth", "detachment", "duty",
        "enlightenment", "why am i here",
    ),
}
"""Client domain -> the question language §4-11 lists as its own.

Matched as whole-word substrings against the lowercased question. Multi-word entries
carry more signal than single words and are the ones that disambiguate: "life purpose"
must reach Dharma rather than Atma, and "most successful" must reach Atma at all.
"""

GENERIC_PHRASES: frozenset[str] = frozenset({
    # PREMA's, but a relationship is equally a family, business or workplace one.
    "relationship",
    "relationships",
    "partner",
    # KARMA's, but "how will this work out" is not a career question.
    "work",
    # YATRA's, but "move up", "move on" and "a difficult transition" are not journeys.
    "move",
    "moving",
    "transition",
})
"""Phrases a domain lists but does not own -- they occur in every domain's questions.

Scored below a one-word specific match so a named subject wins. "What is my relationship
with my father?" tied at 1.0 between PREMA's "relationship" and VANSH's "father", and
document order broke the tie toward PREMA -- so a question about a parent was answered
with marriage rules. Demoting rather than deleting keeps "will my relationship last?"
routable: worth less than a specific term, not worth nothing.
"""

GENERIC_WEIGHT = 0.5
"""Below any specific single-word match (1.0), above nothing."""


def _specificity(phrase: str) -> float:
    """A phrase's score. Multi-word entries are the disambiguating ones and count per
    word; a phrase its domain does not own counts a fraction."""
    if phrase in GENERIC_PHRASES:
        return GENERIC_WEIGHT
    return 1.0 + phrase.count(" ")


TIMING_MARKERS = re.compile(
    r"\bwhen\b|\bwhat time\b|\bwhich year|\bwhich period|\bwhat period|"
    r"\bhow soon\b|\bat what age\b|\btiming\b|\bdasha\b|\bmahadasha\b|"
    r"\bantardasha\b|\bbhukti\b|\btransit\b|\bmuhurta\b|\bperiods?\b|"
    r"\bby (?:19|20)\d\d\b|\bnext year\b|\bthis year\b",
    re.IGNORECASE,
)
"""Language that makes a question about WHEN rather than WHETHER.

Blueprint §4's level 5, and §8's rule 2: "Separate potential from timing. Natal promise
and event timing are different reasoning problems." Without the distinction, "will I
marry" and "when will I marry" retrieve the same rules.
"""

APPLICATION_TIMING = "timing"
APPLICATION_POTENTIAL = "potential"

APPLICATION_RULE_CATEGORY: dict[str, str] = {
    APPLICATION_POTENTIAL: "formation",
    APPLICATION_TIMING: "timing",
}
"""Application type -> the `rule_category` that answers it.

Two vocabularies for one distinction, and they do not coincide: the extractor calls a
natal promise `formation` while §4 level 5 calls the question `potential`. Comparing the
strings directly matched only on "timing" -- by accident -- and silently gave a
whether-question no preference at all.
"""

NUMEROLOGY_MARKERS = re.compile(
    r"\bnumerolog|\bmulank\b|\bbhagyaank\b|\bbhagyank\b|\blucky number|"
    r"\bmy name\b|\bname number|\bdate of birth number|\bnumber say|"
    r"\bnumbers say|\bchaldean\b|\bpythagorean\b",
    re.IGNORECASE,
)
"""Language that invokes the numerology modality.

Blueprint §4 level 1 separates Jyotisha from Numerology; ER §13 makes numerology "a
shared specialist modality callable by the relevant Rishi(s)" which "must never silently
override natal astrology". So it is ADDED to Jyotisha when asked for, never substituted:
a natal question must not retrieve numerology pages as though they were natal evidence.
"""

JYOTISHA = "jyotisha"
NUMEROLOGY = "numerology"

MAX_DOMAINS = 3
"""§12: "Do not invoke all eight by default. Invoke the minimum set that provides
independent, relevant evidence." A cap makes that structural rather than advisory."""


@dataclass(frozen=True)
class Routing:
    """Which Rishis own this question."""

    primary: str | None
    secondary: tuple[str, ...] = ()
    universes: frozenset[str] = frozenset({JYOTISHA})
    """Blueprint §4 level 1 -- which universes this question may retrieve from.

    Always includes Jyotisha; a modality is additive (ER §13), never a replacement."""
    application: str = APPLICATION_POTENTIAL
    """Blueprint §4 level 5. `timing` when the question asks WHEN, else `potential`.

    Matches `rule_category` on extracted rules, so a timing question can lead with the
    rules that activate a promise rather than the rules that establish it. A preference
    rather than a filter: §4-11's protocols run "promise -> ... -> Dasha", so the
    promise is still evidence for a timing question.
    """
    scores: dict[str, float] = field(default_factory=dict)
    matched: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Domain -> the phrases that matched it, so a routing decision can be explained."""

    @property
    def unsupported(self) -> bool:
        """§20: outside the currently supported knowledge boundary."""
        return self.primary is None

    @property
    def domains(self) -> tuple[str, ...]:
        """Primary first, then secondaries -- the order evidence should be gathered in."""
        return () if self.primary is None else (self.primary, *self.secondary)


def _hits(question: str, keywords: tuple[str, ...]) -> list[str]:
    found = []
    for phrase in keywords:
        # Word-bounded so "move" does not match "movement of the Moon", and "earn"
        # does not match "learn".
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", question):
            found.append(phrase)
    return found


def route_question(question: str) -> Routing:
    """The client domains this question belongs to, strongest first.

    A phrase's specificity is its score: a two-word match counts double a one-word
    match, because the multi-word entries are the disambiguating ones, and a phrase in
    `GENERIC_PHRASES` counts a fraction because its domain does not own it. Ties keep
    the document's own domain order.
    """
    text = (question or "").lower()
    application = (
        APPLICATION_TIMING if TIMING_MARKERS.search(text) else APPLICATION_POTENTIAL
    )
    universes = frozenset(
        {JYOTISHA} | ({NUMEROLOGY} if NUMEROLOGY_MARKERS.search(text) else set())
    )
    if not text.strip():
        return Routing(primary=None)

    scores: dict[str, float] = {}
    matched: dict[str, tuple[str, ...]] = {}
    for domain, keywords in QUESTION_KEYWORDS.items():
        hits = _hits(text, keywords)
        if not hits:
            continue
        scores[domain] = sum(_specificity(phrase) for phrase in hits)
        matched[domain] = tuple(hits)

    if not scores:
        return Routing(primary=None, application=application, universes=universes)

    order = list(QUESTION_KEYWORDS)
    ranked = sorted(scores, key=lambda d: (-scores[d], order.index(d)))
    return Routing(
        primary=ranked[0],
        secondary=tuple(ranked[1:MAX_DOMAINS]),
        universes=universes,
        application=application,
        scores=scores,
        matched=matched,
    )


def merge_supporting(routing: Routing, supporting_rishis: list[str]) -> Routing:
    """Add life domains implied by the classifier's supporting personas.

    The keyword table alone cannot produce secondaries on a short question: "Will I
    become a billionaire?" matches one phrase, so it routed to ARTHA with nothing
    beside it, while §12 asks for KARMA, ATMA and YATRA as well. The classifier
    already returns `supporting_rishis` on every call, so this is a second source at no
    extra cost.

    Those are PERSONAS, so they are mapped back through the weighted table. Only
    domains a persona owns outright count -- a service persona rates all eight MEDIUM,
    and admitting those would add every domain and make MAX_DOMAINS meaningless.

    An unrouted question stays unrouted (§20): a persona guess is not evidence that
    the question falls inside the supported boundary.
    """
    from rishivan.council.domains import DOMAIN_HIGH, RISHI_LIFE_DOMAINS

    if routing.primary is None:
        return routing

    extra: list[str] = []
    for rishi in supporting_rishis or []:
        weights = RISHI_LIFE_DOMAINS.get(str(rishi).strip().lower(), {})
        for domain, weight in weights.items():
            if weight < DOMAIN_HIGH:
                continue
            if domain == routing.primary or domain in routing.secondary:
                continue
            if domain not in extra:
                extra.append(domain)

    if not extra:
        return routing

    secondary = (*routing.secondary, *extra)[: MAX_DOMAINS - 1]
    return Routing(
        primary=routing.primary,
        secondary=secondary,
        universes=routing.universes,
        application=routing.application,
        scores=routing.scores,
        matched=routing.matched,
    )
