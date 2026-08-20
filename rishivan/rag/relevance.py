"""Is this rule this Rishi's evidence? Eight Rishis §4-11 coverage, applied.

The house a rule speaks about is the life area it belongs to, so a Rishi's coverage set
is a **gate**, not a hint: a rule whose subject house lies outside it is not that Rishi's
evidence at any score. Planets, factors and vargas then refine what survives, because
§5 naming Venus for PREMA means a 7th-house rule about Venus is stronger evidence than a
7th-house rule about Saturn.

Without the gate, relevance came from the extractor's free-text `life_domains` tag, and
two rules scored identically for a marriage question:

    BPHS 26.74  the 7th lord in the 2nd    tagged Relationships   subject: 7
    BPHS 22.6   the 9th lord in the 10th   tagged father          subject: 9

The tag cannot tell them apart. The subject house can.
"""

from __future__ import annotations

from rishivan.council.constitution import Constitution
from rishivan.council.routing import Routing
from rishivan.knowledge.concepts import RuleConcepts

HOUSE_WEIGHT = 0.70
"""Share of the score carried by subject-house agreement. Dominant because the house is
the life area, and the rest is refinement."""

REFINEMENT_WEIGHT = 0.30
"""Planets, factors and vargas together."""

SUPPORTING_FACTOR = 0.50
"""How much a supporting house counts against the Rishi's own. §5 gives PREMA the 7th
and then "2nd/8th/11th"; weighting them equally ranked "promoter of wealth" -- a 2nd-house
rule -- level with "the native will have many wives" on a marriage question."""

HOUSELESS_CEILING = 0.50
"""Cap for a rule that names no house at all -- `dignity_is`, `conjunct`, `planet_in_sign`.
Coverage cannot judge its subject, so it may be admitted on a named planet but must not
outrank a rule whose house the Rishi actually owns."""

SECONDARY_WEIGHT = 0.50
"""§12 invokes secondary Rishis for independent evidence, not as equals. A rule claimed
only by a secondary domain must rank below one the primary claims."""


def _overlap(left: frozenset, right: frozenset) -> float:
    """Share of `left` that `right` covers. 0.0 when `left` is empty."""
    return len(left & right) / len(left) if left else 0.0


def concept_relevance(concepts: RuleConcepts, constitution: Constitution) -> float:
    """How far this rule falls inside this Rishi's stated coverage, 0..1.

    Zero means "not this Rishi's evidence" and is a gate rather than a low score: a rule
    about the 9th house is not weak evidence about marriage, it is evidence about
    something else.
    """
    refinement = (
        _overlap(concepts.planets, constitution.planets)
        + _overlap(concepts.factors, _factors_of(constitution))
        + _overlap(concepts.vargas, constitution.vargas)
    ) / 3.0

    if concepts.subject_houses:
        own = _overlap(concepts.subject_houses, constitution.primary_houses)
        supporting = _overlap(concepts.subject_houses, constitution.supporting_houses)
        if own == 0.0 and supporting == 0.0:
            return 0.0
        house_agreement = own + SUPPORTING_FACTOR * supporting
        return min(
            1.0, HOUSE_WEIGHT * house_agreement + REFINEMENT_WEIGHT * refinement
        )

    # No house named. Admissible only on a planet this Rishi's section lists.
    if not concepts.planets & constitution.planets:
        return 0.0
    return HOUSELESS_CEILING * refinement


def _factors_of(constitution: Constitution) -> frozenset[str]:
    """Modifier families a Rishi's protocol examines, read off its own protocol steps.

    Derived rather than declared: every §4-11 protocol already names its modifiers
    ("strength", "Dasha", "transit", "D9 confirmation"), so a second list would be a
    second thing to drift.
    """
    text = " ".join(constitution.protocol).lower()
    return frozenset(
        factor
        for factor, needle in (
            ("dignity", "dignity"),
            ("aspect", "aspect"),
            ("conjunction", "conjunction"),
            ("dasha", "dasha"),
            ("transit", "transit"),
            ("nakshatra", "nakshatra"),
            ("sign", "sign"),
            ("occupancy", "occupan"),
        )
        if needle in text
    )


def domain_relevance(
    concepts: RuleConcepts, routing: Routing
) -> tuple[float, str | None]:
    """Best score across the routed domains, and which domain earned it.

    Returns `(0.0, None)` for an unsupported question (§20) or a rule no routed domain
    claims. The domain is returned so an answer can say which Rishi claimed each piece
    of evidence, which is §21's traceability at the routing level.
    """
    best_score = 0.0
    best_domain: str | None = None

    from rishivan.council.constitution import CONSTITUTIONS

    for position, domain in enumerate(routing.domains):
        constitution = CONSTITUTIONS.get(domain)
        if constitution is None:
            continue
        score = concept_relevance(concepts, constitution)
        if position > 0:
            score *= SECONDARY_WEIGHT
        if score > best_score:
            best_score = score
            best_domain = domain

    return best_score, best_domain
