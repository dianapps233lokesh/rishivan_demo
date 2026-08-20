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
        "who am i", "personality", "my strength", "my strengths", "weakness",
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

MAX_DOMAINS = 3
"""§12: "Do not invoke all eight by default. Invoke the minimum set that provides
independent, relevant evidence." A cap makes that structural rather than advisory."""


@dataclass(frozen=True)
class Routing:
    """Which Rishis own this question."""

    primary: str | None
    secondary: tuple[str, ...] = ()
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
    match, because the multi-word entries are the disambiguating ones. Ties keep the
    document's own domain order.
    """
    text = (question or "").lower()
    if not text.strip():
        return Routing(primary=None)

    scores: dict[str, float] = {}
    matched: dict[str, tuple[str, ...]] = {}
    for domain, keywords in QUESTION_KEYWORDS.items():
        hits = _hits(text, keywords)
        if not hits:
            continue
        scores[domain] = sum(1.0 + phrase.count(" ") for phrase in hits)
        matched[domain] = tuple(hits)

    if not scores:
        return Routing(primary=None)

    order = list(QUESTION_KEYWORDS)
    ranked = sorted(scores, key=lambda d: (-scores[d], order.index(d)))
    return Routing(
        primary=ranked[0],
        secondary=tuple(ranked[1:MAX_DOMAINS]),
        scores=scores,
        matched=matched,
    )
