"""The diagnosis a chart becomes, before anything reasons over it.

This sits beside `koonji/facts.py`, not inside it, and the split is deliberate:

    facts.py     flat, interned, superset-safe    -> retrieval
    chartstate   structured, navigable, explained -> reasoning

A `FactSet` answers "does this chart satisfy this predicate" in constant time and
is useless to a human. A `ChartState` answers "what is going on with Saturn" and
carries the *reasons*, which is what a Rishi has to argue from and a reviewer has
to check. Both derive from the same `Chart`, and a test asserts they never
disagree.

Everything here is frozen. `ChartState` is computed once and read by all eight
Rishis (spec C1) - a Rishi that can mutate it can make its colleagues disagree
about a fact rather than about an interpretation, and that argument has no
resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Band(str, Enum):
    """Bucketed strength.

    The values are `registry.BANDS` verbatim, because that is the vocabulary
    rules are written against - a band spelled differently here is a band no
    rule can ever match. A contract test pins the two together.
    """

    VERY_WEAK = "very_weak"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"

    @property
    def _rank(self) -> int:
        return _BAND_ORDER.index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Band):
            return NotImplemented
        return self._rank < other._rank

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Band):
            return NotImplemented
        return self._rank <= other._rank

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Band):
            return NotImplemented
        return self._rank > other._rank

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Band):
            return NotImplemented
        return self._rank >= other._rank


_BAND_ORDER = (
    Band.VERY_WEAK, Band.WEAK, Band.MODERATE, Band.STRONG, Band.VERY_STRONG,
)


@dataclass(frozen=True, slots=True)
class StrengthReading:
    """A strength, and an honest account of where it came from.

    `system` is mandatory. "The selected strength system" is a configuration
    decision the blueprint asks to be stated, and a reading that does not say
    which system produced it cannot be audited or compared across releases.
    """

    value: float
    band: Band
    system: str
    is_estimated: bool
    components: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.system:
            raise ValueError(
                "a strength reading must name the system that produced it - "
                "an unlabelled number cannot be audited or compared"
            )

    @property
    def claimable_value(self) -> Optional[float]:
        """The scalar, but only once the system is validated.

        An estimated Shadbala presented to three decimal places is false
        precision, and everything downstream weights by it. The band survives
        estimation; the number does not.
        """
        return None if self.is_estimated else self.value

    @property
    def claimable_band(self) -> Band:
        """Always safe. Bucketing is what estimation is good enough for."""
        return self.band


@dataclass(frozen=True, slots=True)
class PlanetDiagnosis:
    """Blueprint §6's planet-level list, one graha's worth."""

    graha: str
    natural_nature: str
    functional_nature: str
    functional_reason: str
    """Which lordships produced the verdict. A functional malefic with no
    stated reason is an assertion; with one it is an argument."""

    rashi: str
    dignity: str
    dispositor: str
    dispositor_chain: tuple[str, ...]
    dispositor_cycle: bool
    bhava: int
    lordships: tuple[int, ...]
    conjunctions: tuple[str, ...]
    aspects_cast: tuple[str, ...]
    aspects_received: tuple[str, ...]
    combust: bool
    retrograde: bool
    vargottama: bool
    strength: StrengthReading
    varga_dignity: dict[str, str]
    varga_confirms: dict[str, bool]
    """Per varga: does it corroborate the D1 reading, or contradict it?"""

    nakshatra: str
    nakshatra_lord: str
    nakshatra_lord_chain: tuple[str, ...]
    yogas: tuple[str, ...] = ()
    """Empty in Phase 2, and declared rather than omitted.

    A yoga in this system IS a fired rule, and the engine that fires rules runs
    after this node. Filling it belongs with the evidence layer in Phase 4;
    declaring it now means that phase adds a value, not a type migration."""


@dataclass(frozen=True, slots=True)
class HouseDiagnosis:
    """Blueprint §6's house-level list, one bhava's worth."""

    bhava: int
    rashi: str
    lord: str
    lord_placement: int
    lord_strength: StrengthReading
    lord_dispositor: str
    occupants: tuple[str, ...]
    aspects_received: tuple[str, ...]
    karakas: tuple[str, ...]
    benefic_influence: float
    """Signed, -1..1. Zero means genuinely balanced, not unexamined -
    `influence_reason` is what tells those apart."""

    influence_reason: tuple[str, ...]
    yogas: tuple[str, ...] = ()
    varga_confirms: dict[str, bool] = field(default_factory=dict)
    dasha_active: bool = False
    transit_active: tuple[str, ...] = ()
    """Empty in Phase 2. Needs the transit windows Phase 3 builds."""


@dataclass(frozen=True, slots=True)
class ChartState:
    """The canonical diagnosis. Computed once, read by everything."""

    lagna: str
    planets: tuple[PlanetDiagnosis, ...]
    houses: tuple[HouseDiagnosis, ...]
    framework: str
    """Which lagna framework decided functional nature. Namespaced, because
    Lal Kitab and some lineages differ and a silent default would make two
    incompatible readings look like one disagreement."""

    strength_system: str
    chart_digest: str
    when: Optional[datetime]

    def planet(self, graha: str) -> PlanetDiagnosis:
        """Raises rather than returning None.

        A None here surfaces as an AttributeError three frames away, inside a
        Rishi, with nothing pointing back at the missing graha.
        """
        for p in self.planets:
            if p.graha == graha:
                return p
        raise KeyError(f"no diagnosis for {graha!r}")

    def house(self, bhava: int) -> HouseDiagnosis:
        for h in self.houses:
            if h.bhava == bhava:
                return h
        raise KeyError(f"no diagnosis for bhava {bhava!r}")
