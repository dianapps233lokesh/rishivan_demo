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
from rishivan.varga.confidence import (
    BirthConfidence, arc_uncertainty_degrees, drift_degrees,
)
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


VARGA_LAGNA_IS_READ = False
"""Whether anything downstream reads a varga *house*, rather than a graha's
sign within the division.

Nothing does. Every varga predicate in the registry is sign-based -
`varga_occupies(varga, subject, rashi)`, `varga_dignity(varga, subject,
dignity)`, `vargottama(subject)` - and 403 rule conditions in the corpus use
them. Not one names a bhava.

This matters because the two halves of a division have wildly different
sensitivity to a rough birth time. A graha's division depends on the graha's own
motion, which is slow. The division's *ascendant* depends on the ascendant's,
which is 15 degrees an hour, and is therefore hopeless at any precision a real
user offers. Gating sign evidence on an ascendant nothing consults is what
withheld D9 and D10 from every quarter-hour birth time.

`test_no_rule_in_the_corpus_reads_a_varga_house` asserts the premise. Add a
varga-house predicate and that test fails, which is the signal to set this True
and let `_rescued` test the ascendant again.
"""


def _body_margins(chart: Chart, code: str, confidence: BirthConfidence):
    """Each body's distance from a division edge, against its own drift.

    Yields `(name, margin, drift)` in degrees. The pairing is the point: a
    single threshold for every body is what broke this. Fifteen minutes of clock
    error moves the Moon 0.13 degrees and Saturn 0.001, so one figure either
    trusts the Moon too far or withholds the division over Saturn sitting
    somewhere it cannot meaningfully have moved from.
    """
    arc = arc_of(code)

    for name, planet in chart.planets.items():
        offset = planet.longitude % arc
        yield (
            name,
            min(offset, arc - offset),
            drift_degrees(confidence, planet.speed_deg_per_day),
        )

    if VARGA_LAGNA_IS_READ:
        offset = chart.ascendant_longitude % arc
        yield (
            "Ascendant",
            min(offset, arc - offset),
            arc_uncertainty_degrees(confidence),
        )


def _boundary_margin(chart: Chart, code: str) -> float:
    """How close the nearest body sits to a division edge, in degrees.

    Reported, not compared - `_rescued` weighs each body against its own drift
    and this is only the sentence the note prints. Kept because "every body
    clears a D9 boundary by at least X" is what makes a rescue auditable.
    """
    arc = arc_of(code)
    margins = []
    for planet in chart.planets.values():
        offset = planet.longitude % arc
        margins.append(min(offset, arc - offset))
    return min(margins) if margins else 0.0


def _rescued(chart: Chart, code: str, confidence: BirthConfidence) -> bool:
    """Can this specific chart carry this varga one step below its floor?

    It never could, for any chart, any division, any precision. The test was
    `_boundary_margin(...) > arc_uncertainty_degrees(...)`: every body's margin
    against the *ascendant's* uncertainty. A margin cannot exceed half a
    division by construction, and the ascendant's uncertainty one step below a
    floor exceeds a whole division for every varga that has one - so the
    comparison was unsatisfiable, and the branch simply never ran.

    It failed silently, which is why it lasted: no exception, no withholding
    that looked wrong, just the coarse gate the rescue existed to soften,
    applying to everybody.
    """
    floor = policy_for(code).min_birth_confidence
    if confidence >= floor:
        return False
    if floor - confidence > 1:
        # A rescue is for the margin. Two steps down is a different birth time.
        return False
    return all(
        margin > drift for _, margin, drift in _body_margins(chart, code, confidence)
    )


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
            # The tightest body, named. "Every body clears its own drift" is
            # true but unauditable; the one that came closest to not clearing is
            # the fact a reader can check, and it is the one that would flip
            # this decision if the birth time were rounded any harder.
            name, margin, drift = min(
                _body_margins(chart, policy.code, confidence),
                key=lambda row: row[1] - row[2],
            )
            notes.append(
                f"{policy.code} normally needs a birth time to the "
                f"{policy.min_birth_confidence.name.lower()}; yours is to the "
                f"{confidence.name.lower()}. Every graha still sits clear of a "
                f"{policy.code} boundary by more than {confidence.name.lower()} "
                f"precision could move it — {name} is the closest, {margin:.3f}° "
                f"from an edge against {drift:.3f}° of drift — so the division "
                f"is stable here."
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
