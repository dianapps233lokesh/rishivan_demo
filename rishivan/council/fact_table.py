"""Every planetary position in one table, with the frame as a column.

**This module exists because of a fabricated chart.** Asked "Can I travel foreign
tomorrow?", a reading named Saturn in Pisces, Venus in Virgo, Mercury in Leo, Moon
conjunct Rahu in Aquarius and Jupiter in Cancer — all five of them TRANSIT positions
for that date, not one natal placement among them. A natal chart agreeing with the
sky on five planets would mean the seeker was born that day. The natal condition
flags ("combust", "aspected by Mars and Saturn") were grafted onto the transiting
bodies.

The cause was shape, not disobedience. The prompt carried planetary positions in
five blocks and exactly one of them — the transit block — put planet, sign and
"which house of yours" on a single line. `PLANETARY CONDITION` carried dignity with
no sign and no house, so using it at all meant re-joining across blocks on planet
name. The most usable shape won, over an instruction four hundred characters away
saying the other block was authoritative.

So the fix is not another instruction. It is one table:

  * **The frame is a column, never a heading.** A heading makes a section, a section
    makes a block, and blocks are what fused.
  * **Every row is complete.** Sign, house, dignity, strength and flags together, so
    no join exists to get wrong.
  * **Relevance is a marker, not a location.** A `*` on the rows the question's
    domain owns. Demoting a fact must not mean moving it somewhere a reader can
    treat as a different chart.
  * **A transit row carries no dignity and no strength.** Those are natal
    judgements. Printing them beside a transit sign is the exact fusion this table
    removes — it is how "Venus debilitated in Virgo" came to be written about a
    chart whose natal Venus is exalted in Pisces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_SEQUENCE = (
    "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu",
)
"""The order an astrologer reads grahas in."""

_TRANSIT_GRAHAS = ("Jupiter", "Saturn", "Rahu", "Ketu")
"""Only the slow movers transit into this table.

The Moon changes sign every 2.25 days. A transiting Moon printed beside a natal
chart is what produced an invented "Moon conjunct Rahu in Aquarius" — two
transiting bodies read as a natal conjunction.
"""


@dataclass(frozen=True, slots=True)
class PlanetRow:
    """One planet, in one frame, complete enough to use on its own."""

    frame: str
    planet: str
    sign: str
    house: int
    nakshatra: str = ""
    dignity: str = ""
    strength: str = ""
    flags: tuple[str, ...] = field(default=())
    aspects: tuple[str, ...] = field(default=())


def _symbol(value) -> str:
    """`dignity.own_sign` -> `own_sign`, `graha.moon` -> `moon`.

    Registry symbols are namespaced so the rule engine can match them. A reading
    does not match anything, and asking a model to parse this repo's join keys
    spends its attention on our vocabulary instead of the chart.
    """
    if value is None:
        return ""
    return str(getattr(value, "value", value)).rsplit(".", 1)[-1]


def natal_rows(chart, chart_state, *, frame: str = "natal") -> list[PlanetRow]:
    """One chart's placements, with its judgements on the same lines.

    `frame` is a parameter and not the literal string "natal" because this lane
    does not always have a birth chart. A muhurta or prashna question with no
    birth data is answered from a chart cast at the moment of asking, and
    labelling those rows `natal` told the model they were the seeker's birth
    placements. They were then read as exactly that — and a reading of "can I
    travel tomorrow" described a debilitated natal Venus that was really Venus
    passing through Virgo that afternoon. The frame column exists to stop
    precisely that, so it has to be true.

    `chart_state` may be None — the placements still render and the judgement
    columns come back blank. A blank column is honest; a missing row is not.
    """
    diagnosis = {}
    if chart_state is not None:
        diagnosis = {
            _symbol(p.graha).capitalize(): p for p in chart_state.planets
        }

    rows = []
    for name in _SEQUENCE:
        position = chart.planets.get(name)
        if position is None:
            continue
        flags = ["retrograde"] if position.retrograde else []
        dignity = strength = ""
        aspects: tuple[str, ...] = ()

        found = diagnosis.get(name)
        if found is not None:
            dignity = _symbol(found.dignity)
            if found.strength is not None:
                strength = _symbol(found.strength.band)
            if found.combust:
                flags.append("combust")
            if found.vargottama:
                flags.append("vargottama")
            aspects = tuple(
                _symbol(a).capitalize()
                for a in (found.aspects_received or ())
                if str(a).startswith("graha.")
            )

        rows.append(PlanetRow(
            frame=frame, planet=name, sign=position.rashi,
            house=position.house, nakshatra=position.nakshatra,
            dignity=dignity, strength=strength,
            flags=tuple(flags), aspects=aspects,
        ))
    return rows


def transit_rows(chart, transiting) -> list[PlanetRow]:
    """Where the slow planets are now, in this chart's houses.

    Houses are counted from the NATAL lagna, because a transiting sign on its own
    says nothing — which of the seeker's houses it crosses is the whole content.
    """
    from rishivan.chart.ephemeris import RASHIS

    lagna = RASHIS.index(chart.lagna_rashi)
    rows = []
    for name in _TRANSIT_GRAHAS:
        position = transiting.planets.get(name)
        if position is None:
            continue
        rows.append(PlanetRow(
            frame="transit", planet=name, sign=position.rashi,
            house=((RASHIS.index(position.rashi) - lagna) % 12) + 1,
            nakshatra=position.nakshatra,
            flags=("retrograde",) if position.retrograde else (),
        ))
    return rows


_HEADER = (
    f"{'':1}{'FRAME':<8} {'PLANET':<8} {'SIGN':<12} {'HOUSE':<6} "
    f"{'DIGNITY':<11} {'STRENGTH':<11} NOTES"
)


def render_table(rows: list[PlanetRow], *, primary: set[str]) -> str:
    """The table, one row per planet per frame.

    `primary` marks the planets the question's own domain rests on. Marked rather
    than relocated: every §4-11 protocol ends in whole-chart synthesis, so the
    rest is demoted, not withheld — and moving it into a second block is what
    made blocks readable as separate charts.
    """
    if not rows:
        return ""

    frames = {row.frame for row in rows}
    if "natal" in frames:
        preamble = [
            "THE CHART — every position in one table. The FRAME column says which",
            "chart each row belongs to. A natal row is what the birth chart",
            "promises; a transit row is only where a planet is passing now. Never",
            "read a transit row as a placement in the birth chart, and never move",
            "a judgement from one frame to the other.",
        ]
    else:
        # No natal rows at all, so do not explain them. The preamble used to
        # describe "what the birth chart promises" above a table containing no
        # birth chart, which invited the reader to look for one.
        preamble = [
            "THE CHART — cast for the moment the question was asked. Every row is",
            "marked `prashna` in the FRAME column because that is what it is:",
            "there is no birth chart here, and no row below is a birth placement.",
        ]
    lines = preamble + [
        "Rows marked * bear directly on the question asked; the rest is real and is",
        "yours to synthesise, but do not lead from it.",
        "",
        _HEADER,
    ]
    for row in rows:
        notes = list(row.flags)
        if row.aspects:
            notes.append(f"aspected by {', '.join(row.aspects)}")
        if row.nakshatra:
            notes.append(row.nakshatra)
        lines.append(
            f"{'*' if row.planet in primary else ' '}"
            f"{row.frame:<8} {row.planet:<8} {row.sign:<12} "
            f"{row.house:<6} {row.dignity or '-':<11} {row.strength or '-':<11} "
            f"{'; '.join(notes)}"
        )
    return "\n".join(lines)
