"""One policy per divisional chart. Additive, in the Koonji sense.

Blueprint §7 is unusually direct: *"Do not use every Varga merely because it
exists. Each Varga must have a documented purpose, calculation method and
evidence hierarchy."* This is that table, seeded verbatim, with two things the
blueprint leaves implicit made mechanical:

**The confidence floor is derived, not asserted.** `min_birth_confidence` comes
from the varga's own arc via `min_confidence_for_arc`, so adding D81 later needs
arithmetic rather than somebody's judgement about how careful to be. A D60
division is half a degree; hour-level birth uncertainty moves the ascendant 7.5
degrees; the floor follows.

**No method without a source.** Divisional schemes are precisely where
authorities diverge - D30 alone has three common constructions - so a policy
that names a method it cannot cite is a policy nobody can check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from rishivan.varga.confidence import BirthConfidence, min_confidence_for_arc


class Usage(str, Enum):
    """How freely a varga may be reached for, straight from the table."""

    ALWAYS = "always"
    MANDATORY_CROSSCHECK = "mandatory_crosscheck"
    DOMAIN_ENGINE = "domain_engine"
    METHOD_SPECIFIC = "method_specific"
    VALIDATED_ONLY = "validated_only"
    """Not served. The blueprint says "use only with validated methodology",
    and until that validation exists the honest reading of it is: not yet."""


@dataclass(frozen=True, slots=True)
class VargaPolicy:
    code: str
    name: str
    domain: str
    purpose: str
    method: str
    method_source: str
    usage: Usage
    evidence_tier: int
    """1 corroborates D1 directly; 2 is supporting evidence only. Phase 4's
    hierarchies weight by this."""

    @property
    def divisor(self) -> int:
        return int(self.code[1:])

    @property
    def min_birth_confidence(self) -> BirthConfidence:
        return min_confidence_for_arc(arc_of(self.code))


def arc_of(code: str) -> float:
    """Degrees per division. 30 for D1, 0.5 for D60."""
    return 30.0 / int(code[1:])


_PARASHARA = "bphs ch6 (Shodashavarga)"

_ROWS: tuple[tuple, ...] = (
    # code  name              domain               tier usage
    ("D1", "Rashi", "domain.temperament",
     "Whole-life foundation. Every other division is read against it.",
     "sign of the natal longitude", _PARASHARA, Usage.ALWAYS, 1),
    ("D2", "Hora", "domain.wealth",
     "Wealth and resources.",
     "half-sign, to the Sun's or Moon's hora", _PARASHARA, Usage.DOMAIN_ENGINE, 2),
    ("D3", "Drekkana", "domain.status",
     "Siblings, courage, effort.",
     "third of a sign, to the 1st/5th/9th from it", _PARASHARA, Usage.DOMAIN_ENGINE, 2),
    ("D4", "Chaturthamsha", "domain.property",
     "Property, fortune, home.",
     "quarter-sign, to the 1st/4th/7th/10th from it", _PARASHARA,
     Usage.DOMAIN_ENGINE, 2),
    ("D7", "Saptamsha", "domain.progeny",
     "Children and progeny.",
     "seventh, forward from the sign for odd signs and from the 7th for even",
     _PARASHARA, Usage.DOMAIN_ENGINE, 2),
    ("D9", "Navamsha", "domain.relationship",
     "Marriage, dharma, and the maturity of every planet. The mandatory "
     "cross-check on any D1 reading.",
     "ninth, from the sign itself for movable, the 9th for fixed, the 5th for "
     "dual", _PARASHARA, Usage.MANDATORY_CROSSCHECK, 1),
    ("D10", "Dashamsha", "domain.career",
     "Career and profession. The mandatory career cross-check.",
     "tenth, from the sign for odd and the 9th for even", _PARASHARA,
     Usage.MANDATORY_CROSSCHECK, 1),
    ("D12", "Dwadashamsha", "domain.status",
     "Parents and ancestry.",
     "twelfth, forward from the sign itself", _PARASHARA, Usage.DOMAIN_ENGINE, 2),
    ("D16", "Shodashamsha", "domain.property",
     "Comforts and vehicles. Used only where the method supports it.",
     "sixteenth, from Aries/Leo/Sagittarius by movable/fixed/dual", _PARASHARA,
     Usage.METHOD_SPECIFIC, 2),
    ("D20", "Vimshamsha", "domain.spiritual",
     "Spiritual practice and inclination.",
     "twentieth, from Aries/Sagittarius/Leo by movable/fixed/dual", _PARASHARA,
     Usage.DOMAIN_ENGINE, 2),
    ("D24", "Chaturvimshamsha", "domain.education",
     "Learning and education.",
     "twenty-fourth, from Leo for odd signs and Cancer for even", _PARASHARA,
     Usage.DOMAIN_ENGINE, 2),
    ("D27", "Bhamsa", "domain.health",
     "Innate strengths and weaknesses. Served only against a validated "
     "methodology, which does not yet exist here.",
     "twenty-seventh, from the first sign of the element", _PARASHARA,
     Usage.VALIDATED_ONLY, 2),
    ("D30", "Trimsamsha", "domain.health",
     "Misfortune and negative indications. Read with caution: the scheme is "
     "method-specific and the nodes have no place in it.",
     "unequal five-part division by the five non-luminary lords", _PARASHARA,
     Usage.METHOD_SPECIFIC, 2),
    ("D40", "Khavedamsha", "domain.status",
     "Maternal lineage and auspicious influence. Method-specific.",
     "fortieth, from Aries for odd signs and Libra for even", _PARASHARA,
     Usage.METHOD_SPECIFIC, 2),
    ("D45", "Akshavedamsha", "domain.temperament",
     "Character and paternal inheritance. Method-specific.",
     "forty-fifth, from Aries/Leo/Sagittarius by movable/fixed/dual",
     _PARASHARA, Usage.METHOD_SPECIFIC, 2),
    ("D60", "Shashtiamsha", "domain.temperament",
     "The deep karmic layer. Requires exact-time confidence and a strict "
     "method; withheld otherwise rather than presented as precision it "
     "does not have.",
     "sixtieth, by the classical sixty-fold naming", _PARASHARA,
     Usage.METHOD_SPECIFIC, 2),
)

POLICIES: dict[str, VargaPolicy] = {
    row[0]: VargaPolicy(
        code=row[0], name=row[1], domain=row[2], purpose=row[3],
        method=row[4], method_source=row[5], usage=row[6], evidence_tier=row[7],
    )
    for row in _ROWS
}


def policy_for(code: str) -> VargaPolicy:
    """Raises on an unknown code. A varga the engine can compute and nobody
    scoped is a varga that will eventually be used for something it was never
    meant for."""
    try:
        return POLICIES[code]
    except KeyError:
        raise KeyError(
            f"no policy for varga {code!r} - every computable division needs a "
            f"documented purpose, method and evidence tier before it may speak"
        ) from None


def policies_for_domain(domain: str) -> tuple[VargaPolicy, ...]:
    """The divisions scoped to this life domain, strongest evidence first.

    D1 is excluded: it is always in scope, and returning it here would double
    it. An unmapped domain returns nothing rather than everything - falling back
    to the full set is how "do not use every varga merely because it exists"
    gets quietly undone.
    """
    return tuple(sorted(
        (p for p in POLICIES.values()
         if p.domain == domain and p.usage is not Usage.ALWAYS),
        key=lambda p: (p.evidence_tier, p.divisor),
    ))
