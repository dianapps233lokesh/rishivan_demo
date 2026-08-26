"""What a period lord touches.

This is the join between a dasha and a life area. A period lord that owns the
10th activates career; one that merely sits in the 3rd does not, however loudly
its dasha is running - and without this mapping, "Saturn mahadasha" is a fact
about the calendar rather than about the question.

Three ties, ranked, because they are not equal:

    OWNS       lordship. The strongest tie a period has to a house.
    OCCUPIES   presence. Strong, and the one people notice.
    ASPECTS    drishti. Real, and weaker than either.

Plus two that travel with the graha rather than with its placement: its natural
karaka houses, and any graha sitting in a nakshatra it lords.

Reads `ChartState` rather than the chart, so it inherits Phase 2's lordships and
functional verdicts instead of recomputing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from rishivan.chartstate.types import ChartState


class Strength(IntEnum):
    """Ordered: a house tied two ways is recorded at the stronger one."""

    ASPECTS = 1
    OCCUPIES = 2
    OWNS = 3


#: A graha's natural significations, as houses. Distinct from lordship: Jupiter's
#: period speaks to children whatever it owns in a given chart, because a karaka
#: travels with the graha.
KARAKA_HOUSES: dict[str, tuple[int, ...]] = {
    "graha.sun": (1, 9, 10),
    "graha.moon": (4,),
    "graha.mars": (3, 6),
    "graha.mercury": (4, 10),
    "graha.jupiter": (2, 5, 9, 11),
    "graha.venus": (7,),
    "graha.saturn": (6, 8, 10, 12),
    "graha.rahu": (12,),
    "graha.ketu": (12,),
}

#: Which houses a domain is read from. The subset of blueprint §12's evidence
#: hierarchies that is about *houses*; Phase 4 owns the full table.
DOMAIN_HOUSES: dict[str, tuple[int, ...]] = {
    "domain.career": (6, 7, 10, 11),
    "domain.wealth": (2, 5, 9, 11),
    "domain.relationship": (7,),
    "domain.progeny": (5,),
    "domain.property": (4,),
    "domain.education": (4, 5, 9),
    "domain.health": (1, 6, 8),
    "domain.longevity": (1, 3, 8),
    "domain.travel": (4, 9, 12),
    "domain.spiritual": (5, 9, 12),
    "domain.status": (1, 9, 10),
    "domain.temperament": (1,),
}


@dataclass(frozen=True, slots=True)
class Activation:
    graha: str
    houses: dict[int, Strength]
    karaka_houses: tuple[int, ...]
    nakshatra_dispositees: tuple[str, ...]
    reasons: tuple[str, ...] = field(default=())


def activates(state: ChartState, graha: str) -> Activation:
    """Everything this graha's period reaches."""
    planet = state.planet(graha)  # raises on an unknown graha
    houses: dict[int, Strength] = {}
    reasons: list[str] = []
    bare = graha.removeprefix("graha.")

    def tie(house: int, strength: Strength, why: str) -> None:
        # A house tied two ways keeps the stronger tie, rather than being
        # recorded twice or downgraded by whichever ran last.
        if houses.get(house, Strength.ASPECTS - 1) < strength:
            houses[house] = strength
            reasons.append(why)

    for house in planet.lordships:
        tie(house, Strength.OWNS, f"{bare} owns the {house}th")

    tie(planet.bhava, Strength.OCCUPIES, f"{bare} occupies the {planet.bhava}th")

    for target in planet.aspects_cast:
        if target.startswith("bhava."):
            house = int(target.removeprefix("bhava."))
            tie(house, Strength.ASPECTS, f"{bare} aspects the {house}th")

    dispositees = tuple(sorted(
        p.graha for p in state.planets
        if p.nakshatra_lord == graha and p.graha != graha
    ))
    if dispositees:
        names = ", ".join(d.removeprefix("graha.") for d in dispositees)
        reasons.append(f"{bare} lords the nakshatra of {names}")

    karakas = KARAKA_HOUSES.get(graha, ())
    if karakas:
        reasons.append(
            f"{bare} is the natural karaka for "
            f"{', '.join(f'the {h}th' for h in karakas)}"
        )

    return Activation(
        graha=graha,
        houses=dict(sorted(houses.items())),
        karaka_houses=karakas,
        nakshatra_dispositees=dispositees,
        reasons=tuple(reasons),
    )


def domain_overlap(state: ChartState, graha: str, domain: str) -> tuple[int, ...]:
    """The houses through which this graha reaches this domain."""
    wanted = set(DOMAIN_HOUSES.get(domain, ()))
    if not wanted:
        return ()
    act = activates(state, graha)
    return tuple(sorted(wanted & (set(act.houses) | set(act.karaka_houses))))


def activates_domain(state: ChartState, graha: str, domain: str) -> bool:
    """Does this graha's period speak to this domain at all?

    An unmapped domain returns False rather than True. A period that activates
    everything activates nothing, and defaulting to "yes" is how a timing engine
    ends up producing a window for any question asked of it.
    """
    return bool(domain_overlap(state, graha, domain))
