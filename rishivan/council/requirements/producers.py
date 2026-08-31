"""One requirement key -> one block of prompt text, or nothing.

**Returning `None` is a first-class outcome, not an error.** A producer that
cannot compute its fact says so by returning nothing, and if the requirement was
mandatory the prompt DECLARES it missing. That is the mechanism the whole
registry exists for: a marriage reading that never got the 7th lord's strength
currently reads exactly as fluently as one that did, and nothing downstream can
tell them apart.

**Nothing is reimplemented here.** The blocks `direct_prompt.py` already builds —
the fact table, the condition block, the transits, the panchang — are called, not
copied. What is new in this module is only what was computed and never sent
(`ChartState.houses`, `varga_confirms`, pratyantardasha) or never computed at all
(the Phase 2 doshas and karakas). The import is deferred inside each producer
because `direct_prompt` imports this module back, and the repo defers imports at
call sites everywhere for exactly this reason.

**Order matters in `_PATTERNS`.** They are tried in sequence and the first match
wins, so `d9.house.7.lord.house` must be tested before the unscoped
`house.7.lord.house` pattern or the scope is silently dropped and the D9
requirement is answered with the D1's lord.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_ORDINAL_NAMES = {
    1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th",
    7: "7th", 8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th",
}


@dataclass
class Context:
    """Everything a producer may read, computed once per turn.

    Assembled by `direct_prompt` rather than by each producer, because a transit
    chart costs an ephemeris call and eleven producers wanting one is eleven
    calls for one answer.
    """

    state: dict
    chart: Any = None
    chart_state: Any = None
    when: Any = None
    transiting: Any = None
    moon_on_the_day: Any = None
    facts: dict | None = None
    day_offset: int = 0
    is_natal: bool = True

    @property
    def lat(self) -> float:
        return self.state.get("lat") or 28.6139

    @property
    def lon(self) -> float:
        return self.state.get("lon") or 77.2090

    @property
    def tz(self) -> float:
        return self.state.get("tz_offset") or 5.5


def _symbol(value) -> str:
    if value is None:
        return ""
    return str(getattr(value, "value", value)).rsplit(".", 1)[-1]


# ── blocks that already existed, wired to a key ──────────────────────────────

def _chart_table(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _question_planets, constitution_for
    from rishivan.council.fact_table import natal_rows, render_table, transit_rows

    if ctx.chart is None:
        return None
    frame = "natal" if ctx.is_natal else "prashna"
    rows = natal_rows(ctx.chart, ctx.chart_state, frame=frame)
    if ctx.transiting is not None and ctx.is_natal:
        rows += transit_rows(ctx.chart, ctx.transiting)
    constitution = constitution_for(ctx.state.get("koonji_domain") or "")
    return render_table(
        rows, primary=_question_planets(ctx.chart, constitution)
    ) or None


def _house_lords(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _house_lord_lines, _listed

    lines = _house_lord_lines(ctx.chart)
    if not lines:
        return None
    return _listed(
        "THE HOUSES AND WHO RULES THEM — a house is judged through its lord, "
        "and\nwhere that lord sits:", lines,
    )


def _planet_condition(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _condition_block

    return _condition_block(ctx.chart_state) or None


def _periods(ctx: Context) -> Optional[str]:
    if not (ctx.facts or {}).get("periods"):
        return None
    return (
        "COMPUTED PERIODS — boundaries, not predictions. Every date you write\n"
        "must trace to one of these lines:\n"
        + "\n".join(f"  - {fact}" for fact in ctx.facts["periods"])
    )


def _dasha_forward(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _sub_period_block

    return _sub_period_block(ctx.chart, ctx.when) or None


def _transits(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import transit_block

    return transit_block(
        ctx.chart, ctx.when, lat=ctx.state.get("lat"),
        lon=ctx.state.get("lon"), tz_offset=ctx.state.get("tz_offset"),
    ) or None


def _sade_sati(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import sade_sati_line

    return sade_sati_line(ctx.chart, ctx.transiting) or None


def _panchang(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _panchang_block

    return _panchang_block(ctx.state, ctx.day_offset) or None


def _tara_bala(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _bala_block

    return _bala_block(ctx.chart, ctx.moon_on_the_day,
                       want_tara=True, want_chandra=False) or None


def _chandra_bala(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _bala_block

    return _bala_block(ctx.chart, ctx.moon_on_the_day,
                       want_tara=False, want_chandra=True) or None


def _yogas(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _listed

    items = (ctx.facts or {}).get("yogas")
    return _listed("COMBINATIONS DETECTED:", items) if items else None


def _conjunctions(ctx: Context) -> Optional[str]:
    from rishivan.council.direct_prompt import _listed

    items = (ctx.facts or {}).get("conjunctions")
    return _listed("CONJUNCTIONS (natal):", items) if items else None


# ── computed all along, never sent ───────────────────────────────────────────

def _house_diagnosis(ctx: Context, house: int) -> Optional[str]:
    """Blueprint §6's HOUSE-level diagnosis, for one bhava.

    `ChartState.houses` has held every line of this since Phase 2 and no prompt
    has ever carried it. For a "when will I marry" question the 7th house's lord,
    that lord's strength band, its occupants, what aspects it and the signed
    benefic influence WITH the reasons behind it are the most relevant facts the
    system computes, and the model was being asked to infer them from a
    placements table.
    """
    if ctx.chart_state is None:
        return None
    diagnosis = next(
        (h for h in (ctx.chart_state.houses or ()) if h.bhava == house), None
    )
    if diagnosis is None:
        return None

    ordinal = _ORDINAL_NAMES.get(house, f"{house}th")
    lord = _symbol(diagnosis.lord).capitalize()
    lines = [
        f"THE {ordinal.upper()} HOUSE — computed diagnosis, authoritative. Do not "
        f"re-derive\nany of it from the table above:",
        f"  sign: {_symbol(diagnosis.rashi).capitalize()}",
        f"  lord: {lord}, placed in the "
        f"{_ORDINAL_NAMES.get(diagnosis.lord_placement, '?')} house",
    ]
    if diagnosis.lord_strength is not None:
        lines.append(f"  lord's strength: {_symbol(diagnosis.lord_strength.band)}")
    if diagnosis.lord_dispositor:
        lines.append(
            f"  lord's dispositor: {_symbol(diagnosis.lord_dispositor).capitalize()}"
        )
    occupants = [_symbol(o).capitalize() for o in (diagnosis.occupants or ())]
    lines.append(f"  occupants: {', '.join(occupants) if occupants else 'none'}")
    aspects = [_symbol(a).capitalize() for a in (diagnosis.aspects_received or ())
               if str(a).startswith("graha.")]
    if aspects:
        lines.append(f"  aspected by: {', '.join(aspects)}")
    karakas = [_symbol(k).capitalize() for k in (diagnosis.karakas or ())]
    if karakas:
        lines.append(f"  natural significators: {', '.join(karakas)}")

    influence = diagnosis.benefic_influence
    verdict = ("well supported" if influence > 0.2 else
               "afflicted" if influence < -0.2 else "mixed")
    lines.append(f"  benefic influence: {influence:+.2f} ({verdict})")
    for reason in (diagnosis.influence_reason or ()):
        lines.append(f"    - {reason}")
    if diagnosis.dasha_active:
        lines.append("  a period ruling this house is RUNNING NOW")
    return "\n".join(lines)


def _varga_confirms(ctx: Context, scope: str) -> Optional[str]:
    """Does this division corroborate the D1, planet by planet?

    `PlanetDiagnosis.varga_confirms` has computed this since Phase 2 and never
    reached a prompt. It is the difference between "D9 confirmation" as a
    protocol step and a raw dump of D9 placements the model has to compare by
    itself — and comparing by itself is where it starts asserting agreement that
    is not there.
    """
    code = scope.upper()
    if ctx.chart_state is None or not _admitted(ctx, code):
        return None
    lines = []
    for planet in (ctx.chart_state.planets or ()):
        confirms = (planet.varga_confirms or {})
        if code not in confirms:
            continue
        name = _symbol(planet.graha).capitalize()
        lines.append(
            f"  {name}: the {code} "
            + ("CONFIRMS the birth chart" if confirms[code]
               else "CONTRADICTS the birth chart")
        )
    if not lines:
        return None
    return (
        f"DOES THE {code} CONFIRM THE BIRTH CHART? — computed, per graha. A "
        f"contradiction\nis evidence, not noise: say so rather than averaging it "
        f"away.\n" + "\n".join(lines)
    )


def _admitted(ctx: Context, code: str) -> bool:
    """Did §7's policy admit this division for THIS chart?

    Every varga producer gates on it, and the gate is not cosmetic.
    `varga.select` withholds a division whose arc the recorded birth time cannot
    support - a D9 is a 3.33 degree slice and an hour of uncertainty moves the
    ascendant 7.5 degrees. A producer that computed it anyway would assert a
    placement the selection had just declined to claim, and the prompt would
    contradict its own "DIVISIONS NOT USED" note two blocks later.

    This was live for one commit: the D9 lord producers read the varga engine
    directly, so a chart whose D9 was withheld still got "the 7th house is
    Taurus, ruled by Venus" stated as fact.
    """
    selection = ctx.state.get("vargas")
    return selection is not None and code.upper() in selection.selected


def _varga_placements(ctx: Context, scope: str) -> Optional[str]:
    """One division's placements, if §7's policy admitted it.

    Gated on the selection rather than computed on demand: `varga.select`
    withholds a division whose arc the birth time cannot support, and a producer
    that recomputed it anyway would hand back precision the selection had just
    declined to claim.
    """
    from rishivan.chart.local_varga import varga_facts

    code = scope.upper()
    if ctx.chart is None or not _admitted(ctx, code):
        return None
    facts = varga_facts(ctx.chart, code)
    if not facts:
        return None
    return (
        f"THE {code} — computed placements:\n"
        + "\n".join(f"  - {fact}" for fact in facts)
    )


def _pratyantar(ctx: Context) -> Optional[str]:
    """The running period to the third level.

    `dasha.current_periods` walks down to pratyantar and always has; the direct
    prompt only ever printed maha and antar. An antardasha is roughly eighteen
    months wide, so a client asking "when" was being handed a window nobody
    would plan around when the level below it was already computed.
    """
    if ctx.chart is None or ctx.when is None:
        return None
    from rishivan.chart.dasha import current_periods

    try:
        running = current_periods(ctx.chart, ctx.when)
    except Exception:  # noqa: BLE001
        logger.warning("could not compute the running periods", exc_info=True)
        return None

    labels = (("maha", "Mahadasha"), ("antar", "Antardasha"),
              ("pratyantar", "Pratyantardasha"))
    lines = []
    lords = []
    for level, label in labels:
        period = running.get(level)
        if period is None:
            continue
        lords.append(period.lord)
        lines.append(
            f"  {label} {'/'.join(lords)}: "
            f"{period.start:%Y-%m-%d} to {period.end:%Y-%m-%d}"
        )
    if len(lines) < 3:
        # Two levels is what the prompt already had. Returning it again under a
        # heading promising three would overstate the precision on offer.
        return None
    return (
        "THE PERIOD RUNNING NOW, TO THE THIRD LEVEL — computed boundaries, not\n"
        "predictions. The third level narrows the second; it does not license a\n"
        "sharper claim than the chart supports:\n" + "\n".join(lines)
    )


def _ashtakavarga_house(ctx: Context, house: int) -> Optional[str]:
    """Sarvashtakavarga bindus for one house, with the benchmark to read them against.

    A bindu count is meaningless without the average. 28 is the mean across
    twelve signs (337 total bindus), and a house at 22 means something a house
    at 34 does not — but only if the reader knows where the middle is.
    """
    if ctx.chart is None:
        return None
    from rishivan.chart.vendor.ashtakavarga import compute_ashtakavarga

    try:
        signs = {
            name.lower(): position.rashi_index
            for name, position in ctx.chart.planets.items()
        }
        result = compute_ashtakavarga(signs, ctx.chart.lagna_rashi_index)
    except Exception:  # noqa: BLE001
        logger.warning("could not compute ashtakavarga", exc_info=True)
        return None

    sign_index = (ctx.chart.lagna_rashi_index + house - 1) % 12
    bindus = result.sav[sign_index]
    ordinal = _ORDINAL_NAMES.get(house, f"{house}th")
    standing = ("strong" if bindus >= 30 else
                "weak" if bindus <= 25 else "about average")
    return (
        f"ASHTAKAVARGA FOR THE {ordinal.upper()} HOUSE — computed:\n"
        f"  Sarvashtakavarga bindus: {bindus} ({standing}; 28 is the average "
        f"across the twelve signs)"
    )


def _timing_candidates(ctx: Context) -> Optional[str]:
    """The upcoming periods that could carry this question's event, nearest first.

    This is the block whose absence produced the worst answer this lane has
    given. Every period was printed - two levels, thirty-odd rows - and the model
    was left to search them. It found the Venus ANTARDASHA six years out and
    missed the Venus PRATYANTARDASHA one year out, inside the antardasha already
    running, which was on the same page.
    """
    from rishivan.chart.timing_windows import rendered

    if ctx.chart is None or ctx.when is None or not ctx.is_natal:
        # Vimshottari is counted from the birth Moon. A prashna chart has none,
        # and `question_profile` has already dropped the dasha requirements -
        # this guard is for a hand-edited Mongo row.
        return None
    return rendered(
        ctx.chart, ctx.state.get("koonji_domain") or "", ctx.when
    ) or None


def _muhurta_windows(ctx: Context) -> Optional[str]:
    """The day's Choghadiya and Abhijit, crossed against the bad windows.

    This is what a muhurta question was answered without. `QueryDomain.MUHURTA`
    cast a chart and computed Rahu Kaal, and the model then decided whether
    tomorrow was good - a judgement standing where a table belongs. The tables
    exist classically; nobody had crossed them.
    """
    from rishivan.chart.muhurta import ABHIJIT_METHOD, CHOGHADIYA_METHOD, assess_day
    from rishivan.chart.panchang import compute_panchang

    when = ctx.when
    if when is None:
        return None
    from datetime import timedelta

    day = (when + timedelta(days=ctx.day_offset)).date()
    try:
        panchang = compute_panchang(
            day, lat=ctx.lat, lon=ctx.lon, tz_offset=ctx.tz,
            place=ctx.state.get("place") or "",
        )
        report = assess_day(panchang, panchang.limbs)
    except Exception:  # noqa: BLE001
        logger.warning("could not assess the day's muhurta", exc_info=True)
        return None
    if not report.windows:
        return None

    lines = [
        f"MUHURTA FOR {day.isoformat()} — computed, and exact to the minute. "
        f"These are\narithmetic on sunrise for a stated date, not a claim about "
        f"anyone's life: quote\nthe clock times character for character.",
        f"  choghadiya method: {CHOGHADIYA_METHOD}",
        f"  abhijit method: {ABHIJIT_METHOD}",
    ]
    if report.day_notes:
        lines.append("  QUALIFYING THE WHOLE DAY:")
        lines += [f"    - {note}" for note in report.day_notes]

    best = report.best()
    if best:
        lines.append("  BEST WINDOWS — good choghadiya, no collision:")
        for slot in best:
            lines.append(f"    {slot.start}-{slot.end}  {slot.name} ({slot.lord})")
    else:
        lines.append(
            "  NO CLEAN WINDOW in daylight: every good part collides with an "
            "inauspicious one."
        )

    lines.append("  EVERY PART OF THE DAY, in order:")
    for slot in report.windows:
        if slot.period == "night":
            continue
        collided = (f"  [collides: {', '.join(slot.collisions)}]"
                    if slot.collisions else "")
        lines.append(
            f"    {slot.start}-{slot.end}  {slot.name:<6} "
            f"{slot.quality:<7}{collided}"
        )
    return "\n".join(lines)


def _kuja_dosha(ctx: Context) -> Optional[str]:
    """Mangal dosha, from all three reference points.

    Reported whichever way it comes out. "No dosha" is a real finding in a
    marriage reading and one the seeker will want stated — a block that appears
    only on afflicted charts teaches a reader that its absence means nothing was
    checked.
    """
    if ctx.chart is None:
        return None
    from rishivan.chart.dosha import kuja_dosha

    result = kuja_dosha(ctx.chart)
    if result is None:
        return None

    verdict = ("PRESENT" if result["present"] else "not present")
    lines = [
        f"MANGAL (KUJA) DOSHA — computed: {verdict}.",
        f"  convention used: {result['convention']}",
    ]
    for reference, entry in result["from"].items():
        label_for = {"lagna": "from the Lagna", "moon": "from the Moon",
                     "venus": "from Venus"}[reference]
        state = "RAISES the dosha" if entry["afflicted"] else "clear"
        lines.append(
            f"  {label_for}: Mars sits in the "
            f"{_ORDINAL_NAMES.get(entry['house'], '?')} — {state}"
        )
    if result["present"]:
        lines.append(
            "  A dosha is a qualification, not a prohibition. Classical practice "
            "cancels\n  or reduces it on several grounds; say what it does to the "
            "timing and the\n  match rather than treating it as a verdict on its "
            "own."
        )
    return "\n".join(lines)


def _karaka(ctx: Context, which: str) -> Optional[str]:
    """One Jaimini chara karaka, and where that graha sits.

    `prema`'s protocol step 5 is "Jaimini indicators" and `blocked_concepts` has
    listed Darakaraka since the constitutions were written. This is the step
    every marriage reading has correctly declared unavailable and skipped.
    """
    if ctx.chart is None or not ctx.is_natal:
        # A prashna chart is not a nativity, and a chara karaka computed from
        # one names the significators of a moment. `question_profile` already
        # drops these before they are requested; this is the backstop, because
        # the requirement table is hand-editable in Mongo and a row added there
        # must not be able to resurrect a fabricated spouse.
        return None
    from rishivan.chart.jaimini import KARAKA_NAMES, METHOD, chara_karakas

    if which not in KARAKA_NAMES:
        return None
    karakas = chara_karakas(ctx.chart)
    graha = karakas.get(which)
    position = ctx.chart.planets.get(graha or "")
    if position is None:
        return None
    return (
        f"{KARAKA_NAMES[which].upper()} — computed: {graha}, in "
        f"{position.rashi}, in the {_ORDINAL_NAMES.get(position.house, '?')} "
        f"house at {position.degree_in_rashi:.2f}°.\n"
        f"  method: {METHOD}"
    )


def _arudha_house(ctx: Context, house: int) -> Optional[str]:
    """An arudha pada. House 12 is the Upapada, the Jaimini marriage indicator."""
    if ctx.chart is None or not ctx.is_natal:
        # An arudha is counted from the BIRTH lagna. See `_karaka` above.
        return None
    from rishivan.chart.jaimini import _pada

    pada = _pada(ctx.chart, house)
    if pada is None:
        return None
    name = ("UPAPADA LAGNA (UL)" if house == 12
            else "ARUDHA LAGNA (AL)" if house == 1
            else f"ARUDHA OF THE {_ORDINAL_NAMES.get(house, house).upper()}")
    return (
        f"{name} — computed: {pada['sign']}, the "
        f"{_ORDINAL_NAMES.get(pada['house_from_lagna'], '?')} house from the "
        f"lagna, ruled by {pada['lord']}.\n"
        f"  derived from the {_ORDINAL_NAMES.get(house, house)} lord "
        f"{pada['derived_from_lord']}, counted the same distance again."
    )


_JUPITER_ASPECTS = (5, 7, 9)
_SATURN_ASPECTS = (3, 7, 10)


def _double_transit(ctx: Context, house: int) -> Optional[str]:
    """Are Jupiter and Saturn both touching this house and its lord right now?

    The classical timing check for a house's activation: an event is held to need
    both the expansive and the constraining transit before it lands. Reported as
    the four separate conditions rather than as a yes or no, because a partial
    double transit is the ordinary case and collapsing it to a boolean hides
    which half is missing — and which half is missing is what decides whether the
    answer is "now" or "when Saturn arrives".
    """
    if ctx.chart is None or ctx.transiting is None:
        return None
    lord = ctx.chart.house_lords.get(house)
    lord_position = ctx.chart.planets.get(lord or "")
    if lord_position is None:
        return None

    lagna = ctx.chart.lagna_rashi_index
    target_sign = (lagna + house - 1) % 12
    lord_sign = lord_position.rashi_index

    lines = []
    touching = 0
    for graha, aspects in (("Jupiter", _JUPITER_ASPECTS), ("Saturn", _SATURN_ASPECTS)):
        moving = ctx.transiting.planets.get(graha)
        if moving is None:
            continue
        for label_for, sign in (("the house", target_sign),
                                (f"its lord {lord}", lord_sign)):
            distance = (sign - moving.rashi_index) % 12 + 1
            if distance == 1:
                lines.append(f"  {graha} is transiting {label_for} — yes")
                touching += 1
            elif distance in aspects:
                lines.append(
                    f"  {graha} aspects {label_for} "
                    f"({_ORDINAL_NAMES.get(distance, distance)} aspect) — yes"
                )
                touching += 1
            else:
                lines.append(f"  {graha} does not touch {label_for} — no")

    ordinal = _ORDINAL_NAMES.get(house, house)
    verdict = ("FULL — both grahas touch both points" if touching == 4 else
               "PARTIAL" if touching else "ABSENT")
    return (
        f"DOUBLE TRANSIT OVER THE {ordinal.upper()} HOUSE — computed for today: "
        f"{verdict}.\n"
        f"Jupiter and Saturn are read together for the activation of a house; a\n"
        f"partial touch times differently from a full one, so say which half is\n"
        f"missing rather than reporting a yes or a no:\n" + "\n".join(lines)
    )


# ── token producers ──────────────────────────────────────────────────────────

def _lord_of_house(ctx: Context, house: int) -> Optional[str]:
    if ctx.chart is None:
        return None
    lord = ctx.chart.house_lords.get(house)
    position = ctx.chart.planets.get(lord) if lord else None
    if lord is None or position is None:
        return None
    return (
        f"  the {_ORDINAL_NAMES.get(house, house)} lord is {lord}, in "
        f"{position.rashi}, in the {_ORDINAL_NAMES.get(position.house, '?')} house"
    )


def _varga_lord_of_house(ctx: Context, scope: str, house: int) -> Optional[str]:
    """The lord of a house within a division, and where it sits there.

    Read from the division's own lagna, not the D1's. A D9 seventh counted from
    the birth ascendant is not the D9 seventh, and getting that wrong produces a
    confident sentence about the wrong sign.
    """
    if ctx.chart is None or not _admitted(ctx, scope):
        return None
    from rishivan.chart.ephemeris import RASHI_LORDS, RASHIS
    from rishivan.chart.local_varga import _varga_positions

    computed = _varga_positions(ctx.chart, scope.upper())
    if computed is None:
        return None
    lagna_sign, positions = computed
    sign_index = (lagna_sign + house - 1) % 12
    lord = RASHI_LORDS[sign_index]
    placed = positions.get(lord)
    where = (f"in the {_ORDINAL_NAMES.get(placed[1], '?')} house of the "
             f"{scope.upper()}" if placed else "position unknown")
    return (
        f"  {scope.upper()}: the {_ORDINAL_NAMES.get(house, house)} house is "
        f"{RASHIS[sign_index]}, ruled by {lord}, {where}"
    )


def _from_moon_lord(ctx: Context, house: int) -> Optional[str]:
    """A house counted from the Moon rather than the ascendant.

    Chandra lagna. The classical texts read the 7th from the Moon alongside the
    7th from the lagna, and a reading that consults only one has done half the
    step whatever it says about the other half.
    """
    if ctx.chart is None:
        return None
    from rishivan.chart.ephemeris import RASHI_LORDS, RASHIS

    moon = ctx.chart.planets.get("Moon")
    if moon is None:
        return None
    sign_index = (moon.rashi_index + house - 1) % 12
    lord = RASHI_LORDS[sign_index]
    placed = ctx.chart.planets.get(lord)
    ordinal = _ORDINAL_NAMES.get(house, house)
    if placed is None:
        return f"  from the Moon: the {ordinal} is {RASHIS[sign_index]}, ruled by {lord}"
    from_moon_house = (placed.rashi_index - moon.rashi_index) % 12 + 1
    return (
        f"  from the Moon (Chandra lagna): the {ordinal} is {RASHIS[sign_index]}, "
        f"ruled by {lord}, who sits in the "
        f"{_ORDINAL_NAMES.get(from_moon_house, '?')} from the Moon"
    )


def _planet_dignity(ctx: Context, planet: str) -> Optional[str]:
    if ctx.chart_state is None:
        return None
    for diagnosis in (ctx.chart_state.planets or ()):
        if _symbol(diagnosis.graha).lower() != planet.lower():
            continue
        parts = [f"dignity {_symbol(diagnosis.dignity)}"]
        if diagnosis.strength is not None:
            parts.append(f"strength {_symbol(diagnosis.strength.band)}")
        if diagnosis.functional_nature:
            parts.append(f"functionally {diagnosis.functional_nature}")
        return f"  {planet.capitalize()}: {'; '.join(parts)}"
    return None


# ── the registry ─────────────────────────────────────────────────────────────

_EXACT: dict[str, Callable[[Context], Optional[str]]] = {
    "block.chart_table": _chart_table,
    "block.house_lords": _house_lords,
    "block.planet_condition": _planet_condition,
    "block.dasha.current": _periods,
    "block.dasha.forward": _dasha_forward,
    "block.dasha.pratyantar": _pratyantar,
    "block.transits_slow": _transits,
    "block.sade_sati": _sade_sati,
    "block.panchang": _panchang,
    "block.tara_bala": _tara_bala,
    "block.chandra_bala": _chandra_bala,
    "block.yogas": _yogas,
    "block.conjunctions": _conjunctions,
    "block.kuja_dosha": _kuja_dosha,
    "block.muhurta": _muhurta_windows,
    "block.timing.candidates": _timing_candidates,
}

_PATTERNS: tuple[tuple[re.Pattern, Callable], ...] = (
    (re.compile(r"^block\.house\.(\d{1,2})$"),
     lambda ctx, m: _house_diagnosis(ctx, int(m.group(1)))),
    (re.compile(r"^block\.varga\.(d\d{1,2})$"),
     lambda ctx, m: _varga_placements(ctx, m.group(1))),
    (re.compile(r"^block\.varga_confirms\.(d\d{1,2})$"),
     lambda ctx, m: _varga_confirms(ctx, m.group(1))),
    (re.compile(r"^block\.ashtakavarga\.house\.(\d{1,2})$"),
     lambda ctx, m: _ashtakavarga_house(ctx, int(m.group(1)))),
    # Scoped BEFORE unscoped, or `d9.house.7.lord.house` matches the plain
    # pattern and the D9 requirement is answered with the D1's lord.
    (re.compile(r"^(d\d{1,2})\.house\.(\d{1,2})\.lord\.house$"),
     lambda ctx, m: _varga_lord_of_house(ctx, m.group(1), int(m.group(2)))),
    (re.compile(r"^from_moon\.house\.(\d{1,2})\.lord\.house$"),
     lambda ctx, m: _from_moon_lord(ctx, int(m.group(1)))),
    (re.compile(r"^house\.(\d{1,2})\.lord\.house$"),
     lambda ctx, m: _lord_of_house(ctx, int(m.group(1)))),
    (re.compile(r"^planet\.([a-z]+)\.dignity$"),
     lambda ctx, m: _planet_dignity(ctx, m.group(1))),
    (re.compile(r"^block\.transit\.double\.(\d{1,2})$"),
     lambda ctx, m: _double_transit(ctx, int(m.group(1)))),
    (re.compile(r"^karaka\.([a-z]+)$"),
     lambda ctx, m: _karaka(ctx, m.group(1))),
    (re.compile(r"^from_arudha_lagna\.house\.(\d{1,2})$"),
     lambda ctx, m: _arudha_house(ctx, int(m.group(1)))),
)


def produce(key: str, ctx: Context) -> Optional[str]:
    """The text for one requirement, or None if it cannot be computed.

    Never raises. A producer that falls over costs the reading one fact and
    declares it missing, which is strictly better than costing them the answer.
    """
    try:
        exact = _EXACT.get(key)
        if exact is not None:
            return exact(ctx)
        for pattern, handler in _PATTERNS:
            match = pattern.match(key)
            if match is not None:
                return handler(ctx, match)
    except Exception:  # noqa: BLE001
        logger.warning("the producer for %r failed", key, exc_info=True)
        return None
    return None


def known(key: str) -> bool:
    """Whether anything at all can produce this key.

    An unknown key and a key whose producer returned None are different facts
    about a reading — "nothing computes this" versus "this chart does not have
    one" — and the unavailable block says which.
    """
    if key in _EXACT:
        return True
    return any(pattern.match(key) for pattern, _ in _PATTERNS)


LABELS: dict[str, str] = {
    "karaka.dara": "Darakaraka — the Jaimini chara karaka for the spouse",
    "karaka.putra": "Putrakaraka — the Jaimini chara karaka for children",
    "from_arudha_lagna.house.12": "Upapada Lagna — the 12th from the Arudha Lagna",
    "block.kuja_dosha": "Mangal (Kuja) dosha",
    "block.dasha.pratyantar": "the pratyantardasha, the third period level",
    "block.muhurta": "the Choghadiya and Abhijit windows for the day",
    "block.timing.candidates": "the upcoming periods ruled by this question's "
                               "own significators",
    "block.panchang": "the panchang — tithi, nakshatra, yoga, karana and the "
                      "day's inauspicious windows",
}
"""Plain English for the keys a reading is most likely to be told it lacks.

The key itself is a fallback, not a failure: `house.7.lord.house` reads well
enough in a missing-facts list, and inventing a phrasing for all seventy-nine
would be seventy-nine more things to keep true.
"""


_VARGA_KEY = re.compile(r"^(?:block\.)?(?:varga(?:_confirms)?\.)?(d\d{1,2})\.?")


def label(key: str) -> str:
    """Plain English for a key, for the missing-facts list.

    Varga keys are named rather than printed raw, because they are the ones a
    reader is most likely to be told about: §7's policy withholds a division
    whenever the birth time cannot support its arc, and "block.varga.d9" does
    not explain that the marriage chart was declined."""
    known_label = LABELS.get(key)
    if known_label:
        return known_label
    match = _VARGA_KEY.match(key)
    if match:
        code = match.group(1).upper()
        if key.startswith("block.varga_confirms."):
            return f"whether the {code} confirms the birth chart"
        if key.startswith("block.varga."):
            return f"the {code}'s placements"
        return f"{key} (in the {code})"
    return key
