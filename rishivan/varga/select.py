"""Which vargas a question gets, and what was withheld and why.

Two gates, in order.

**Usage.** A varga scoped to another domain is not reached for at all - "do not
use every Varga merely because it exists" - and `VALIDATED_ONLY` divisions are
not served until that validation exists.

**Birth-time confidence.** Each policy carries a floor derived from its own arc.
Below the floor the varga is withheld, and the withholding is a *first-class
output*: "D60 needs a birth time to the minute; yours is recorded to the hour,
so I have not used it" is a sentence no astrology app says, and it cannot be
said by a pipeline that silently drops the varga.

**The rescue, and why it exists.** A blunt floor is wrong in the other
direction. A navamsa division is 3 degrees 20 minutes; quarter-hour uncertainty
is 3.75 degrees; so the coarse gate withholds D9 - a *mandatory* cross-check -
from anyone who says "half past four", which is most people. But the uncertainty
only bites when a body sits near a division boundary. A chart whose grahas are
all comfortably mid-division is genuinely readable at coarser precision, and
refusing it is conservative to the point of being wrong.

So: one step below the floor, check this specific chart. If every body clears
the boundary by more than the uncertainty, admit the varga and *say on what
basis*. More than one step below, never - a rescue is for the margin, not for an
unknown birth time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rishivan.chart.ephemeris import Chart
from rishivan.varga.confidence import BirthConfidence, arc_uncertainty_degrees
from rishivan.varga.policy import Usage, arc_of, policies_for_domain, policy_for

ALWAYS: tuple[str, ...] = ("D1",)


@dataclass(frozen=True, slots=True)
class WithheldVarga:
    code: str
    required: BirthConfidence
    actual: BirthConfidence
    reason: str
    """User-facing, and it names the shortfall. A withholding the user cannot
    act on is indistinguishable from the feature not existing."""


@dataclass(frozen=True, slots=True)
class VargaSelection:
    selected: tuple[str, ...]
    withheld: tuple[WithheldVarga, ...]
    confidence: BirthConfidence
    notes: tuple[str, ...] = field(default=())
    """Why a varga below its floor was admitted anyway. A rescue that is not
    stated is a rescue nobody can audit."""

    def floor_for(self, code: str) -> BirthConfidence:
        return policy_for(code).min_birth_confidence


def _boundary_margin(chart: Chart, code: str) -> float:
    """How close the nearest body sits to a division edge, in degrees.

    The ascendant is included and weighted the same. Every varga's house frame
    hangs off it, so an ascendant near an edge moves the whole chart even when
    no graha does.
    """
    arc = arc_of(code)
    longitudes = [p.longitude for p in chart.planets.values()]
    longitudes.append(chart.ascendant_longitude)

    margins = []
    for longitude in longitudes:
        offset = longitude % arc
        margins.append(min(offset, arc - offset))
    return min(margins)


def _rescued(chart: Chart, code: str, confidence: BirthConfidence) -> bool:
    """Can this specific chart carry this varga one step below its floor?"""
    floor = policy_for(code).min_birth_confidence
    if confidence >= floor:
        return False
    if floor - confidence > 1:
        # A rescue is for the margin. Two steps down is a different birth time.
        return False
    return _boundary_margin(chart, code) > arc_uncertainty_degrees(confidence)


def select_vargas(
    chart: Chart,
    domain: str,
    confidence: BirthConfidence,
) -> VargaSelection:
    """The divisions this question may read from, and the ones it may not."""
    selected: list[str] = list(ALWAYS)
    withheld: list[WithheldVarga] = []
    notes: list[str] = []

    for policy in policies_for_domain(domain):
        if policy.usage is Usage.VALIDATED_ONLY:
            withheld.append(WithheldVarga(
                code=policy.code,
                required=policy.min_birth_confidence,
                actual=confidence,
                reason=(
                    f"{policy.code} ({policy.name}) is only used against a "
                    f"validated methodology, and that validation does not exist "
                    f"here yet."
                ),
            ))
            continue

        if confidence >= policy.min_birth_confidence:
            selected.append(policy.code)
            continue

        if _rescued(chart, policy.code, confidence):
            selected.append(policy.code)
            margin = _boundary_margin(chart, policy.code)
            notes.append(
                f"{policy.code} normally needs a birth time to the "
                f"{policy.min_birth_confidence.name.lower()}; yours is to the "
                f"{confidence.name.lower()}, but every body in this chart clears "
                f"a {policy.code} boundary by {margin:.2f}°, more than the "
                f"{arc_uncertainty_degrees(confidence):.2f}° the time could be "
                f"out — so the division is stable here."
            )
            continue

        withheld.append(WithheldVarga(
            code=policy.code,
            required=policy.min_birth_confidence,
            actual=confidence,
            reason=(
                f"{policy.code} ({policy.name}) needs a birth time known to the "
                f"{policy.min_birth_confidence.name.lower()}; yours is recorded "
                f"to the {confidence.name.lower()}, which could move it by "
                f"{arc_uncertainty_degrees(confidence):.1f}° against a "
                f"{arc_of(policy.code):.2f}° division. I have not used it."
            ),
        ))

    selected.sort(key=lambda c: (policy_for(c).evidence_tier, policy_for(c).divisor))
    return VargaSelection(
        selected=tuple(selected),
        withheld=tuple(withheld),
        confidence=confidence,
        notes=tuple(notes),
    )
