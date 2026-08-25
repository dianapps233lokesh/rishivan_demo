"""Functional benefic and malefic, under a lagna framework that is named.

**Why this is code and not a Koonji rule.** The architecture spec argued that
functional nature is doctrine and should therefore be sourced `DERIVE_FACT`
rules, and in principle that is right - lineages disagree, so it wants a
citation and a version. But the ingested corpus holds only *lagna-specific*
commentary on the subject (Bhavartha Ratnakara ch1, on Mesha lagna's 10th/11th
lord), not a general statement of the kendra/trikona doctrine. Turning those
verses into a universal rule is exactly the scope inflation
`koonji.validate.check_scope_inflation` exists to catch, and a rule with an
invented locator is the one output this system must never produce.

So it is computed here, the framework is named and namespaced, and the Koonji
`functional_nature` predicate stays `derived=True` and unsatisfied until a
general doctrine verse is acquired. That is a corpus gap rather than an
engineering one, and it is recorded in the gap map.

**The doctrine, Parashari standard:**

  kendras 1/4/7/10 · trikonas 1/5/9 · dusthanas 6/8/12

  * a trikona lord is benefic for the chart
  * a lord of 3, 6 or 11 is malefic
  * a NATURAL benefic owning a kendra is blemished by it (kendradhipatya
    dosha); a natural malefic owning one is not. This asymmetry is the part
    people get wrong, and it is the part that changes readings.
  * a planet owning both a kendra and a trikona - two different houses, not the
    1st counted twice - is a yogakaraka, and the strongest benefic in the chart
  * Rahu and Ketu own no sign, so there is no lordship to judge them by. They
    take their dispositor's verdict.

Every verdict carries its reason. A functional malefic with no stated reason is
an assertion; with one it is an argument a reviewer can disagree with.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rishivan.chart.ephemeris import Chart

KENDRAS: tuple[int, ...] = (1, 4, 7, 10)
TRIKONAS: tuple[int, ...] = (1, 5, 9)
DUSTHANAS: tuple[int, ...] = (6, 8, 12)
MALEFIC_LORDSHIPS: tuple[int, ...] = (3, 6, 11)
"""The upachaya-and-dusthana set the doctrine calls malefic to own. The 8th and
12th are dusthanas but their lordship is treated separately in most readings -
kept out of this tuple deliberately, and folded in as a weakening note."""

NATURAL_BENEFICS: frozenset[str] = frozenset({"jupiter", "venus", "mercury", "moon"})
"""Mercury and the Moon are conditional in the full doctrine - Mercury takes the
colour of its associates, and a waning Moon is malefic. Treated as benefic here
because that is the standard simplification, and flagged as an approximation
rather than passed off as complete."""

NATURAL_MALEFICS: frozenset[str] = frozenset(
    {"sun", "mars", "saturn", "rahu", "ketu"}
)

NODES: frozenset[str] = frozenset({"rahu", "ketu"})

FRAMEWORKS: frozenset[str] = frozenset({"parashari"})
"""Named, and checked. A silent default would make two incompatible lineages
look like one disagreement about a chart."""


@dataclass(frozen=True, slots=True)
class FunctionalVerdict:
    graha: str
    nature: str
    reason: str
    lordships: tuple[int, ...]
    natural_nature: str
    yogakaraka: bool = False
    kendradhipatya_dosha: bool = False


_ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    """4 -> "4th", 3 -> "3rd". "the 3th house" in a reason a reviewer reads is
    a small thing that costs the rest of the sentence its credibility."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{_ORDINAL_SUFFIX.get(n % 10, 'th')}"


def _bare(graha: str) -> str:
    return graha.removeprefix("graha.").lower()


def natural_nature_of(graha: str) -> str:
    bare = _bare(graha)
    if bare in NATURAL_BENEFICS:
        return "benefic"
    if bare in NATURAL_MALEFICS:
        return "malefic"
    return "neutral"


def _lordships(chart: Chart, graha: str) -> tuple[int, ...]:
    bare = _bare(graha)
    return tuple(
        house for house, lord in sorted(chart.house_lords.items())
        if lord.lower() == bare
    )


def functional_natures(
    chart: Optional[Chart], framework: str = "parashari"
) -> dict[str, FunctionalVerdict]:
    """Every graha in the chart, judged."""
    if framework not in FRAMEWORKS:
        raise KeyError(
            f"unknown lagna framework {framework!r} - known: {sorted(FRAMEWORKS)}. "
            f"Defaulting silently would make two lineages look like one "
            f"disagreement about a chart."
        )
    return {
        f"graha.{name.lower()}": functional_nature_of(
            chart, f"graha.{name.lower()}", framework=framework
        )
        for name in chart.planets
    }


def functional_nature_of(
    chart: Chart, graha: str, framework: str = "parashari"
) -> FunctionalVerdict:
    if framework not in FRAMEWORKS:
        raise KeyError(f"unknown lagna framework {framework!r}")

    bare = _bare(graha)
    natural = natural_nature_of(graha)

    if bare in NODES:
        return _node_verdict(chart, graha, natural)

    owned = _lordships(chart, graha)
    if not owned:
        return FunctionalVerdict(
            graha=graha, nature="neutral", lordships=(), natural_nature=natural,
            reason="owns no house in this chart",
        )

    # The 1st is both a kendra and a trikona, so counting it on both sides would
    # make every lagna lord a yogakaraka. The doctrine means two different
    # houses.
    kendras = tuple(h for h in owned if h in KENDRAS and h != 1)
    trikonas = tuple(h for h in owned if h in TRIKONAS and h != 1)
    malefic_houses = tuple(h for h in owned if h in MALEFIC_LORDSHIPS)

    if kendras and trikonas:
        return FunctionalVerdict(
            graha=graha, nature="benefic", lordships=owned, natural_nature=natural,
            yogakaraka=True,
            reason=(
                f"yogakaraka: owns kendra {kendras[0]} and trikona {trikonas[0]}"
            ),
        )

    if 1 in owned:
        return FunctionalVerdict(
            graha=graha, nature="benefic", lordships=owned, natural_nature=natural,
            reason="lagna lord",
        )

    if trikonas:
        return FunctionalVerdict(
            graha=graha, nature="benefic", lordships=owned, natural_nature=natural,
            reason=f"lord of the {_ordinal(trikonas[0])} (trikona)",
        )

    if malefic_houses:
        return FunctionalVerdict(
            graha=graha, nature="malefic", lordships=owned, natural_nature=natural,
            reason=f"lord of the {_ordinal(malefic_houses[0])}",
        )

    if kendras and natural == "benefic":
        # Kendradhipatya dosha. The asymmetry is the doctrine's point: a kendra
        # blemishes a natural benefic and does nothing to a natural malefic.
        return FunctionalVerdict(
            graha=graha, nature="neutral", lordships=owned, natural_nature=natural,
            kendradhipatya_dosha=True,
            reason=(
                f"kendradhipatya dosha: a natural benefic owning kendra "
                f"{kendras[0]} loses its benefic force"
            ),
        )

    if kendras:
        return FunctionalVerdict(
            graha=graha, nature="neutral", lordships=owned, natural_nature=natural,
            reason=(
                f"natural malefic owning kendra {kendras[0]} - a kendra does "
                f"not blemish a malefic"
            ),
        )

    dusthanas = tuple(h for h in owned if h in DUSTHANAS)
    if dusthanas:
        return FunctionalVerdict(
            graha=graha, nature="malefic", lordships=owned, natural_nature=natural,
            reason=f"lord of the {_ordinal(dusthanas[0])} (dusthana)",
        )

    return FunctionalVerdict(
        graha=graha, nature="neutral", lordships=owned, natural_nature=natural,
        reason=f"lord of the {_ordinal(owned[0])}, neither trikona nor kendra",
    )


def _node_verdict(chart: Chart, graha: str, natural: str) -> FunctionalVerdict:
    """Rahu and Ketu own no sign, so there is no lordship to judge them by.

    The classical answer is that they act for their dispositor - and for the
    house they occupy - so the dispositor's verdict is inherited, and the reason
    says exactly that rather than leaving the inheritance implicit.
    """
    from rishivan.chartstate.dispositor import dispositor_of

    dispositor = dispositor_of(chart, graha)
    inherited = functional_nature_of(chart, dispositor)
    return FunctionalVerdict(
        graha=graha, nature=inherited.nature, lordships=(),
        natural_nature=natural,
        reason=(
            f"owns no sign; takes the verdict of its dispositor "
            f"{dispositor.removeprefix('graha.')} ({inherited.reason})"
        ),
    )
