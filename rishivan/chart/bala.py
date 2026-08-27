"""Tara bala and chandra bala — the Moon's strength for an undertaking.

`facts.py` has carried a comment noting these were absent since before the direct
lane existed, and the absence had a cost. Asked "Can I travel foreign tomorrow?",
a reading answered with dasha boundaries running to 2060 — because the question
was a muhurta question and not one muhurta fact had been computed, so the model
used the facts it had rather than the ones the question needed.

These are what such a question is actually judged on. Both are index arithmetic
over lists this repo already holds, which is the other reason their absence was
worth fixing: they cost nothing.

Nothing here interprets. `tara_bala` says which tara is running and whether the
tradition counts it favourable; it does not say whether to travel. That judgement
belongs to the reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

TARA_NAMES: tuple[str, ...] = (
    "Janma", "Sampat", "Vipat", "Kshema", "Pratyari",
    "Sadhaka", "Vadha", "Mitra", "Ati-Mitra",
)
"""The nine taras, counted from the birth nakshatra inclusive.

Inclusive matters: the janma nakshatra is the FIRST tara, not the zeroth. An
off-by-one here shifts every verdict by one nakshatra, which is a wrong answer
that looks entirely reasonable.
"""

_UNFAVOURABLE_TARAS = frozenset({"Janma", "Vipat", "Pratyari", "Vadha"})
"""Four of the nine. Getting this set wrong inverts the advice on more than a
third of all dates."""

_FAVOURABLE_HOUSES = frozenset({1, 3, 6, 7, 10, 11})
_UNFAVOURABLE_HOUSES = frozenset({4, 8, 12})
"""Chandra bala, by the transiting Moon's house from the natal Moon.

2, 5 and 9 are in neither set on purpose. They are read differently across
schools, and collapsing a genuine disagreement into "favourable" would state
something the tradition does not — so they come back `middling` and the reading
can say so.
"""


@dataclass(frozen=True, slots=True)
class TaraBala:
    number: int
    name: str
    is_favourable: bool
    natal_nakshatra: str
    transit_nakshatra: str

    def describe(self) -> str:
        verdict = "favourable" if self.is_favourable else "unfavourable"
        return (
            f"Tara bala: {self.name} tara ({self.number} of 9), {verdict} — the "
            f"Moon is in {self.transit_nakshatra}, counted from your birth "
            f"nakshatra {self.natal_nakshatra}"
        )


@dataclass(frozen=True, slots=True)
class ChandraBala:
    house: int
    verdict: str
    natal_rashi: str
    transit_rashi: str

    def describe(self) -> str:
        from rishivan.chart.facts import _ORDINAL

        return (
            f"Chandra bala: the Moon is transiting {self.transit_rashi}, the "
            f"{_ORDINAL.get(self.house, self.house)} sign from your natal Moon "
            f"in {self.natal_rashi} — {self.verdict}"
        )


def _nakshatra_index(name: str) -> Optional[int]:
    from rishivan.astro.constants import NAKSHATRAS

    for index, info in enumerate(NAKSHATRAS):
        if info.name == name:
            return index
    return None


def tara_bala(
    natal_nakshatra: str, transit_nakshatra: str
) -> Optional[TaraBala]:
    """Which of the nine taras the transiting Moon is running for this person.

    `None` on an unrecognised nakshatra rather than a guess: a tara computed from
    a name we could not place is a verdict about the wrong nine days, and it
    would be indistinguishable from a correct one.
    """
    natal = _nakshatra_index(natal_nakshatra)
    transit = _nakshatra_index(transit_nakshatra)
    if natal is None or transit is None:
        return None

    # Inclusive count from the janma nakshatra, then folded into the nine.
    count = ((transit - natal) % 27) + 1
    number = ((count - 1) % 9) + 1
    name = TARA_NAMES[number - 1]
    return TaraBala(
        number=number, name=name,
        is_favourable=name not in _UNFAVOURABLE_TARAS,
        natal_nakshatra=natal_nakshatra,
        transit_nakshatra=transit_nakshatra,
    )


def chandra_bala(natal_rashi: str, transit_rashi: str) -> Optional[ChandraBala]:
    """The transiting Moon's house from the natal Moon, and how it is read."""
    from rishivan.chart.ephemeris import RASHIS

    if natal_rashi not in RASHIS or transit_rashi not in RASHIS:
        return None

    house = ((RASHIS.index(transit_rashi) - RASHIS.index(natal_rashi)) % 12) + 1
    if house in _FAVOURABLE_HOUSES:
        verdict = "favourable"
    elif house in _UNFAVOURABLE_HOUSES:
        verdict = "unfavourable"
    else:
        verdict = "middling"
    return ChandraBala(
        house=house, verdict=verdict,
        natal_rashi=natal_rashi, transit_rashi=transit_rashi,
    )
