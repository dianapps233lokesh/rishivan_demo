"""Which upcoming periods can actually carry this question's event.

**The failure this exists to close.** A Scorpio-lagna chart was asked "when will
I get married". Venus rules its 7th house. The prompt printed, verbatim:

    - Venus: 2027-08-03 to 2028-01-23 [future]

the Venus pratyantardasha inside the running Saturn antardasha. The model walked
past it and named the Rahu/Venus ANTARDASHA in 2033 - the same lord, six years
further out, because it was the larger period. A competing product read the same
chart and answered "August 2027 to January 2028".

Nothing was miscomputed: the chart, the divisional chart and every dasha
boundary matched that product exactly. What the model was handed was a SEARCH,
across two levels and thirty-odd periods, with no rule for choosing between
them. So it is not a search any more.

**Nearest first, and that ordering is the whole fix.** Both windows above are
ruled by the 7th lord. A seeker asking "when" wants the next real opportunity,
not the largest one in the timeline. A reading that answers "2033" to a
twenty-two-year-old is defensible and useless.

**Classically, the levels divide the labour**: the mahadasha sets the era, the
antardasha sets the theme, and the pratyantardasha is when the thing actually
lands. An event timed only to an antardasha is timed to a three-year band.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_HORIZON_YEARS = 12
"""How far forward to look.

Long enough that a chart whose significator does not rule anything soon still
gets an honest answer, short enough that the list stays readable. A window
beyond this is reported as "beyond the horizon" rather than omitted.
"""

MAX_WINDOWS = 12
"""Bounded, and the drop is reported rather than silent - `rendered` says how
many were left out. A truncated list that looks complete is how a reading comes
to believe it saw everything."""


@dataclass(frozen=True, slots=True)
class Candidate:
    """One upcoming period ruled by something that carries the question."""

    start: datetime
    end: datetime
    lord: str
    level: str
    """`antar` or `pratyantar`."""

    path: str
    """`Rahu/Saturn/Venus` — the full chain, so the reading can name it."""

    because: str
    """Why this graha carries this question: "7th lord", "karaka", or both."""

    tier: str = "primary"
    """`primary` or `supporting`.

    A period ruled by the lord of the house the matter SITS in is a stronger
    claim than one ruled by a house that merely bears on it. Both are offered
    because leaving the supporting ones out is what produced a 2028 answer to
    "when will I get a job" - `karma`'s primary house is the 10th, so only the
    10th lord was searched, and the 11th lord (gains) ruled a window fourteen
    months earlier."""

    running: bool = False


def significators_for(chart, koonji_domain: str) -> dict[str, tuple[str, str]]:
    """Graha -> (why it carries this question, `primary` or `supporting`).

    Three sources, and the third was missing for two commits.

    * **The primary house's lord**, from the chart. Which graha that is depends
      on the lagna and cannot be listed in advance.
    * **The constitution's named significators** - `prema` names Venus and
      Jupiter, `karma` names none.
    * **The SUPPORTING houses' lords.** `karma` already declares
      `supporting_houses = [1, 2, 6, 11]` and this function ignored them, so
      "when will I get a job" searched the 10th lord alone. In Vedic terms the
      6th house IS employment and the 11th is where income arrives; for a job
      question they carry at least as much as the 10th. Excluding them pushed
      an answer fourteen months later than the chart supported.

    Kept as two tiers rather than one flat set, because a period ruled by the
    lord of the house the matter sits in is a stronger claim than one ruled by a
    house that merely bears on it - and a reading should be able to say which it
    is leaning on.
    """
    from rishivan.council.direct_prompt import constitution_for

    constitution = constitution_for(koonji_domain)
    primary: dict[str, list[str]] = {}
    supporting: dict[str, list[str]] = {}

    for house in sorted(constitution.primary_houses):
        lord = (chart.house_lords or {}).get(house)
        if lord:
            primary.setdefault(lord, []).append(f"{_ordinal(house)} lord")
    for planet in constitution.planets:
        primary.setdefault(planet.capitalize(), []).append("natural significator")
    for house in sorted(constitution.supporting_houses):
        lord = (chart.house_lords or {}).get(house)
        if lord and lord not in primary:
            supporting.setdefault(lord, []).append(f"{_ordinal(house)} lord")

    out: dict[str, tuple[str, str]] = {
        lord: (" and ".join(why), "primary") for lord, why in primary.items()
    }
    out.update({
        lord: (" and ".join(why), "supporting")
        for lord, why in supporting.items()
    })
    return out


_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 21: "21st", 22: "22nd", 23: "23rd"}


def _ordinal(n: int) -> str:
    return _ORDINALS.get(n, f"{n}th")


def candidate_windows(
    chart, koonji_domain: str, when: datetime,
    years: int = DEFAULT_HORIZON_YEARS,
) -> tuple[Candidate, ...]:
    """Upcoming antardashas and pratyantardashas ruled by a significator.

    Nearest first. Both levels are offered together rather than the antardashas
    alone, because the level is exactly what the model got wrong: it is not
    obvious from a list of antardashas that a finer period inside the running
    one is the better answer, and it is obvious from this list.
    """
    from rishivan.chart.dasha import mahadasha_timeline, sub_periods

    significators = significators_for(chart, koonji_domain)
    if not significators or years <= 0:
        return ()

    horizon = when + timedelta(days=int(365.25 * years))
    found: list[Candidate] = []

    for maha in mahadasha_timeline(chart):
        if maha.end <= when or maha.start >= horizon:
            continue
        for antar in sub_periods(maha, "antar"):
            if antar.end <= when or antar.start >= horizon:
                continue
            if antar.lord in significators:
                why, tier = significators[antar.lord]
                found.append(Candidate(
                    start=antar.start, end=antar.end, lord=antar.lord,
                    level="antar", path=f"{maha.lord}/{antar.lord}",
                    because=why, tier=tier,
                    running=antar.start <= when < antar.end,
                ))
            for pratyantar in sub_periods(antar, "pratyantar"):
                if pratyantar.end <= when or pratyantar.start >= horizon:
                    continue
                if pratyantar.lord not in significators:
                    continue
                why, tier = significators[pratyantar.lord]
                found.append(Candidate(
                    start=pratyantar.start, end=pratyantar.end,
                    lord=pratyantar.lord, level="pratyantar",
                    path=f"{maha.lord}/{antar.lord}/{pratyantar.lord}",
                    because=why, tier=tier,
                    running=pratyantar.start <= when < pratyantar.end,
                ))

    # Nearest first. Ties break to the finer level, because a pratyantar names a
    # month and the antardasha containing it names a three-year band.
    found.sort(key=lambda c: (c.start, c.level != "pratyantar"))
    return tuple(found)


def rendered(chart, koonji_domain: str, when: datetime,
             years: int = DEFAULT_HORIZON_YEARS) -> str:
    """The candidate list as a prompt block, or empty when there is none."""
    candidates = candidate_windows(chart, koonji_domain, when, years)
    if not candidates:
        return ""

    shown = candidates[:MAX_WINDOWS]
    lines = [
        "WINDOWS THAT COULD CARRY THIS EVENT — computed, NEAREST FIRST.",
        "Each is a period ruled by a graha that carries this question: the lord of",
        "the house the matter sits in, or its natural significator. This is the",
        "search already done for you - do not go looking through the period lists",
        "above for a different one.",
        "",
        "**Prefer the nearest window that fits.** A later period ruled by the same",
        "graha is not a better answer for being longer: the mahadasha sets the era,",
        "the antardasha the theme, and the PRATYANTARDASHA is when a thing lands.",
        "Reach past a near window only if you can say what disqualifies it, and then",
        "say that out loud.",
        "",
        "Rows marked * are ruled by the lord of the house the matter SITS in, and",
        "are the stronger claim. Unmarked rows are ruled by a house that bears on",
        "it - for work, the 6th of service and the 11th of gains. An unmarked",
        "window nearer than a marked one is often the real answer: the thing",
        "arrives through the supporting house and is confirmed by the primary.",
        "",
    ]
    for candidate in shown:
        gap = (candidate.start - when).days / 365.25
        distance = ("running now" if candidate.running
                    else f"{gap:.1f} yr away" if gap > 0 else "under way")
        mark = "*" if candidate.tier == "primary" else " "
        lines.append(
            f" {mark}{candidate.start:%Y-%m-%d} to {candidate.end:%Y-%m-%d}  "
            f"{candidate.path:<24} {candidate.level:<11} "
            f"{candidate.lord} ({candidate.because}) [{distance}]"
        )
    if len(candidates) > len(shown):
        lines.append(
            f"  ...and {len(candidates) - len(shown)} more beyond these, further "
            f"out. Not hidden - just later than anything worth naming here."
        )
    return "\n".join(lines)
