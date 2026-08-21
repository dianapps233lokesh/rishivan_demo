"""What a rule is about, read off its own condition atoms.

Blueprint §6 lists `CONCEPTS` as a Koonji field and the extractor never produced one.
It does not need to: the condition already names them. Deriving rather than re-extracting
means the whole rule base gains concepts without another pass over the book, and the
derivation cannot drift from the condition it describes.

The distinction that matters is **subject** versus **location**. `lord_of_house_in_house`
carries two houses and they are not interchangeable -- in "the 7th lord in the 2nd" the
rule speaks about the 7th house's affairs, and the 2nd is only where its lord sits. A
Rishi's coverage set (Eight Rishis §4-11) is a set of subjects, so matching on both
houses equally is what let BPHS 22.6, whose subject is the 9th, reach a marriage
question.
"""

from __future__ import annotations

from dataclasses import dataclass

SUBJECT_HOUSE_FIELDS: dict[str, tuple[str, ...]] = {
    "lord_of_house_in_house": ("lord_of",),
    "lord_of_house_in_sign": ("lord_of",),
    "planet_in_house": ("house", "houses"),
    "house_is_empty": ("house", "houses"),
    "aspected_by": ("target",),
    "transit_over": ("house", "houses"),
}
"""Per atom type, the field naming the house the rule is ABOUT.

`planet_in_house` and `lord_of_house_in_house` differ here, which looks inconsistent and
is not: "Saturn in the 7th" is a statement about marriage, so the house is the subject,
while "the 7th lord in the 2nd" is also a statement about marriage, so the *lord's* house
is the subject. In both the subject is the 7th.
"""

ATOM_FACTORS: dict[str, str] = {
    "dignity_is": "dignity",
    "conjunct": "conjunction",
    "aspected_by": "aspect",
    "planet_in_nakshatra": "nakshatra",
    "planet_in_sign": "sign",
    "dasha_of": "dasha",
    "transit_over": "transit",
    "house_is_empty": "occupancy",
}
"""The modifier family each atom type exercises, for matching against a Rishi's
coverage -- §4-11 name "dignity", "aspects", "conjunctions", "Dashas", "transits"."""

PLANET_FIELDS = ("planet", "other")

_ALL_HOUSE_FIELDS = ("house", "houses", "lord_of", "target")


def _houses(atom: dict, fields: tuple[str, ...]) -> set[int]:
    found: set[int] = set()
    for name in fields:
        value = atom.get(name)
        if value is None:
            continue
        for item in value if isinstance(value, list) else [value]:
            try:
                number = int(item)
            except (TypeError, ValueError):
                continue  # `planet: "7th lord"` and friends, from unparsed rules
            if 1 <= number <= 12:
                found.add(number)
    return found


@dataclass(frozen=True)
class RuleConcepts:
    """The concepts one rule touches. `subject_houses` is what coverage matches on."""

    subject_houses: frozenset[int] = frozenset()
    other_houses: frozenset[int] = frozenset()
    planets: frozenset[str] = frozenset()
    factors: frozenset[str] = frozenset()
    vargas: frozenset[str] = frozenset()

    @property
    def houses(self) -> frozenset[str]:
        """Every house named, subject or location."""
        return self.subject_houses | self.other_houses


def concepts_of(condition: dict | None) -> RuleConcepts:
    """Read a condition's concepts. Negated atoms count -- a rule that requires the 5th
    lord NOT to be in the 6th is still a rule about the 5th house."""
    if not condition:
        return RuleConcepts()

    atoms = (condition.get("atoms") or []) + (condition.get("none") or [])
    subject: set[int] = set()
    other: set[int] = set()
    planets: set[str] = set()
    factors: set[str] = set()
    vargas: set[str] = set()

    for atom in atoms:
        atom_type = atom.get("type")
        subject_fields = SUBJECT_HOUSE_FIELDS.get(atom_type, ())
        subject |= _houses(atom, subject_fields)
        # Split by FIELD, not by value: "the Ascendant lord in the Ascendant" has house
        # 1 as both subject and location, and dropping the duplicate loses a location.
        other |= _houses(
            atom, tuple(f for f in _ALL_HOUSE_FIELDS if f not in subject_fields)
        )

        for name in PLANET_FIELDS:
            value = atom.get(name)
            if isinstance(value, str) and value.strip():
                planets.add(value.strip().lower())

        factor = ATOM_FACTORS.get(atom_type)
        if factor:
            factors.add(factor)

        scope = (atom.get("scope") or "").strip().lower()
        # A varga is a different chart; `from_moon.`/`from_sun.` re-count this one.
        if scope.startswith("d") and scope.endswith("."):
            vargas.add(scope[:-1].upper())

    return RuleConcepts(
        subject_houses=frozenset(subject),
        other_houses=frozenset(other),
        planets=frozenset(planets),
        factors=frozenset(factors),
        vargas=frozenset(vargas),
    )
