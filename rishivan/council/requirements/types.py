"""What a question requires, and where the answer came from.

Plain frozen data. No Mongo, no chart, no I/O — so the catalogue can be
validated, and the validation tested, without a cluster or an ephemeris.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Source(str, Enum):
    """Which carrier supplied the requirements this turn.

    Recorded on every set and shown in the UI. A demo silently running on the
    built-in copy while somebody edits Mongo and sees nothing change is a
    confusing afternoon; naming the source turns it into one glance.
    """

    MONGO = "mongo"
    BUILTIN = "builtin"


BANDS: dict[int, str] = {
    1: "RULE ON THIS",
    2: "CORROBORATE",
    3: "CONTEXT",
}
"""priority -> what the band means to the model.

Three, not five. The distinction that matters is between what the verdict rests
on and what merely surrounds it; a finer scale invites the author to agonise
over whether something is a 3 or a 4 and tells the model nothing extra.
"""


@dataclass(frozen=True, slots=True)
class Requirement:
    """One fact a question needs, and how much it needs it."""

    key: str
    """Either a `rishivan.astro.vocab` token — `house.7.lord.house`,
    `d9.planet.venus.house` — or a `block.*` id naming a rendered block.

    Token keys are validated against `vocab.is_valid_fact_key` when the
    catalogue loads, so a typo fails at seed time rather than silently
    requesting a fact that does not exist. That failure mode is the whole
    reason this is validated at all: a requirement nobody can satisfy and
    nobody notices is worse than no requirement."""

    step: int = 0
    """Which step of the constitution's protocol this fact serves.

    `CONSTITUTIONS['prema'].protocol` is already the classical reading order for
    a marriage question — promise, spouse indicators, quality, D9, Jaimini,
    affliction, dasha, transit, cross-school, confidence. Pointing at it means
    the prompt's ordering is the tradition's, not one invented here, and a fact
    that serves no step is a fact somebody should justify."""

    mandatory: bool = False
    """A mandatory fact that cannot be computed is DECLARED to the model as
    unavailable rather than quietly omitted. That declaration is most of the
    value in this table: a reading missing the 7th lord's strength currently
    reads exactly as fluently as one that has it."""

    priority: int = 2

    @property
    def band(self) -> str:
        return BANDS.get(self.priority, BANDS[3])

    @property
    def is_block(self) -> bool:
        return self.key.startswith("block.")


@dataclass(frozen=True, slots=True)
class RequirementSet:
    """Everything one (domain, kind) pair asks for."""

    domain: str
    kind: str
    constitution: str = ""
    requires: tuple[Requirement, ...] = ()
    source: Source = Source.BUILTIN
    notes: str = ""

    @property
    def doc_id(self) -> str:
        return f"{self.domain}:{self.kind}"

    def by_band(self) -> dict[int, tuple[Requirement, ...]]:
        """Requirements grouped by priority, each group in protocol order.

        Sorted by `step` inside a band rather than left in authoring order, so
        the prompt walks a marriage question's band 1 as promise → spouse
        indicators → affliction, which is how the protocol reads it.
        """
        bands: dict[int, list[Requirement]] = {}
        for requirement in self.requires:
            bands.setdefault(requirement.priority, []).append(requirement)
        return {
            priority: tuple(sorted(group, key=lambda r: (r.step, r.key)))
            for priority, group in sorted(bands.items())
        }

    def mandatory_keys(self) -> tuple[str, ...]:
        return tuple(r.key for r in self.requires if r.mandatory)
