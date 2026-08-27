"""The direct lane's prompt: classical method, not classical documents.

The retrieval lane answers from twenty topically-similar pages and whatever
rules fired. This one answers from the model's own reading of the classical
literature — which is wider than this corpus and better organised — and spends
the prompt on telling it *which* part of that knowledge to reach for.

`constitution.protocol` is what makes that possible. It already holds the
classical reading order per domain, taken from Eight Rishis §4-11, and until now
it only decided which rules counted as a Rishi's evidence. Here it becomes the
procedure the model works through.

**No persona.** The Rishi voice, the seven movements and the speech example are
deliberately absent: this lane is being graded on astrological accuracy against
three other platforms, and prose quality would confound that. The voice returns
as a narration step over this same material.

Everything in this module is a pure function of state. No client, no network, no
database — which is what makes the golden-snapshot test possible and what
`test_no_network` pins.
"""

from __future__ import annotations

import re

from rishivan.chart.facts import _ORDINAL
from rishivan.council.constitution import Constitution
from rishivan.council.prompts import _FRAMEWORK, _SUBJECT_HOUSE

"""`_FRAMEWORK` and `_SUBJECT_HOUSE` are imported from `prompts` rather than
copied, and the privacy is knowingly crossed. `_SUBJECT_HOUSE` encodes the
subject-versus-location distinction — "Sun is in Sagittarius in the 6th house"
is about the Sun, not about the 6th — and a second copy of that anchored regex
is a second thing that can drift away from the first. Same package, one
definition."""

DEFAULT_CONSTITUTION_KEY = "atma"
"""Where an unroutable question lands.

Atma's protocol is the whole-chart one (`chart framework → Lagna and Lagna lord
→ Sun and Moon → strength → Nakshatra → major combinations → relevant Vargas →
Jaimini → synthesis → uncertainty`), which is the correct reading order for a
question nobody could place. The alternative — no method block — is a prompt
that has given up the entire point of this lane.
"""


def constitution_for(koonji_domain: str) -> Constitution:
    """The constitution for a `domain.*` symbol.

    Two taxonomies meet here. `hierarchy_node` writes `koonji_domain` as a
    `domain.*` symbol because that is what the rule corpus is tagged with;
    `CONSTITUTIONS` is keyed by the client's eight life-domain keys because that
    is what Eight Rishis §21 names. `LIFE_DOMAIN_OF` is the existing bridge and
    is used rather than duplicated — a second mapping is a second thing to drift.

    First rather than all, matching `hierarchy_node`: a domain that maps to two
    life domains is primarily about the first.
    """
    from rishivan.council.constitution import CONSTITUTIONS
    from rishivan.council.hierarchy import LIFE_DOMAIN_OF

    keys = LIFE_DOMAIN_OF.get(koonji_domain or "", ())
    return CONSTITUTIONS[keys[0] if keys else DEFAULT_CONSTITUTION_KEY]


def framing_block(constitution: Constitution) -> str:
    """Who is answering, from what, and what they may not do.

    `source_families` is rendered rather than hardcoded so the framing tracks
    §4-11 the way the rest of the lane does.

    `unavailable_sources` and `blocked_concepts` are deliberately NOT rendered.
    They record what *this repo's corpus* lacks, which is meaningless to a model
    reading from its own knowledge — and naming them would talk it out of
    knowledge it actually has.
    """
    families = ", ".join(constitution.source_families)
    forbidden = ""
    if constitution.forbidden_claims:
        forbidden = (
            "\n\nYou may not claim any of the following, in any form:\n"
            + "\n".join(f"  - {claim}" for claim in constitution.forbidden_claims)
        )
    return f"""
You are an expert Vedic (Jyotish) astrologer working in the classical tradition.
Read the computed chart below and answer the question at the end.

Draw on the classical literature you know, from your own knowledge of it:
{families}.

DO NOT CITE. No page numbers, no chapter-and-verse references, no book titles in
your answer, no quoted verses, and no stock authority phrases ("the classical
texts say", "the old masters held"). You have not been given any text to quote
from, so a citation you produce cannot be checked by anyone — which makes it
worth less than no citation at all. State what the principle IS. Do not say
where you read it.

Never present a health diagnosis, a treatment, or death as a certainty. These
are traditional interpretations; keep their uncertainty intact.

Never state that an event WILL happen, and never guarantee anything. What you
produce is a calculated inference from planetary positions, not a schedule. A
dasha period is when a thing could ripen, never proof that it will, and a period
that happens to be running now is not evidence that anything is imminent. Write
"this is the period that would carry it" and not "you will receive it then". This
holds for every subject, not only the tender ones.{forbidden}
""".strip()


def method_block(constitution: Constitution) -> str:
    """The classical reading order, as an instruction.

    The steps are `constitution.protocol` verbatim, numbered. Verbatim matters:
    they are §4-11's own words, and paraphrasing them here would make the
    instruction and the coverage gate two different methods with one name.
    """
    steps = "\n".join(
        f"  {index}. {step}"
        for index, step in enumerate(constitution.protocol, start=1)
    )
    last = len(constitution.protocol)
    return f"""
READING METHOD — {constitution.dimension}
{constitution.mission}

Work these steps, in this order, BEFORE you write anything:

{steps}

THESE STEPS ARE YOUR WORKING, NOT YOUR ANSWER. They do not appear in the reply
and the seeker must never be able to tell they exist. Do not number them, do not
name them, do not write a paragraph per step. You think in this order; you write
in the order the reply section below asks for.

Work every step. Where the computed facts cannot settle one, note it for yourself
and let it lower your confidence — but do not announce the gap unless it changes
what the seeker should do, and announce at most two such gaps in a reply. Three
of ten steps reporting themselves unsupported reads as a broken machine, not as
an honest one, and past the second caveat a reader stops reading caveats and
starts discounting the whole reading.

Do not settle your verdict before step {last}. The order is the method: a promise
that was never established cannot be timed, and a window with no promise behind
it is arithmetic pretending to be a prediction.
""".strip()


# ── Sorting the fact list into what each bundle needs ────────────────────────

_PERIOD_PREFIXES = ("Mahadasha timeline", "Currently running")
"""The dated lines. They belong to the period bundles, never to a placement."""

_HOUSE_RULER = re.compile(
    r"^The (\d{1,2})(?:st|nd|rd|th) house \([^)]*\) is ruled by (\w+)"
)
"""A house and its lord. Read to decide which planets the question rests on:
prema names Venus and Jupiter, but the 7th lord is whatever the lagna made it."""

_TRANSITING_MOON = "Transiting Moon on"
"""The one transit fact `derive_facts` mixes into the natal list.

It used to land in the natal block, and a reading duly conjoined it with the
transiting node to invent "Moon conjunct Rahu in Aquarius, house 2" - two
transiting bodies presented as a natal conjunction. It now goes only to questions
about a specific day, where it is the actual subject.
"""


_VARGA_LINE = re.compile(r"\((D\d{1,2})\)")
"""A divisional placement line, dropped here because `_varga_block` renders the
same divisions from the chart. Both printed every placement twice."""

_PLANET_LINE = re.compile(
    r"^(Sun|Moon|Mars|Mercury|Jupiter|Venus|Saturn|Rahu|Ketu) is in "
)
"""A per-planet placement line. Matched only so it can be DROPPED: `fact_table`
renders the same information with dignity and strength attached, and two
renderings in two shapes is the fusion this replaced."""


def _partition(chart_facts: list[str]) -> dict[str, list[str]]:
    """Fact lines by the bundle that owns them.

    Per-planet placement lines are deliberately dropped: `fact_table` renders
    every one of them with its dignity and strength attached, and a second
    rendering in a different shape is exactly what the table exists to remove.
    """
    out: dict[str, list[str]] = {
        "framework": [], "lords": [], "conjunctions": [], "yogas": [],
        "periods": [], "transiting_moon": [], "other": [],
    }
    for fact in chart_facts:
        if fact.startswith(_FRAMEWORK):
            out["framework"].append(fact)
        elif fact.startswith(_PERIOD_PREFIXES):
            out["periods"].append(fact)
        elif fact.startswith(_TRANSITING_MOON):
            out["transiting_moon"].append(fact)
        elif _HOUSE_RULER.match(fact):
            out["lords"].append(fact)
        elif fact.startswith("Conjunction:"):
            out["conjunctions"].append(fact)
        elif fact.startswith("Yoga:"):
            out["yogas"].append(fact)
        elif _SUBJECT_HOUSE.match(fact) or _PLANET_LINE.match(fact):
            pass  # the table has these, complete
        elif _VARGA_LINE.search(fact):
            # `chart_natal_node` appends varga facts to this list and
            # `_varga_block` renders the same divisions from the chart, so
            # keeping both printed every divisional placement twice.
            pass
        else:
            out["other"].append(fact)
    return out


def _question_planets(chart_facts: list[str], constitution: Constitution) -> set[str]:
    """Which planets this question rests on: the domain's own, plus the lords of
    its houses.

    The second half is what a planet list cannot anticipate. For a marriage
    question prema names Venus and Jupiter, and the 7th lord is whichever graha
    the lagna assigned - Mercury on the test chart, in neither list.
    """
    planets = {p.capitalize() for p in constitution.planets}
    for fact in chart_facts:
        match = _HOUSE_RULER.match(fact)
        if match and int(match.group(1)) in constitution.houses:
            planets.add(match.group(2).capitalize())
    return planets


# ── The whole prompt ─────────────────────────────────────────────────────────

_OUTPUT_BLOCK = """
OUTPUT

**The answer goes in the first sentence.** Not the third paragraph, not after
your reasoning — first. Name the window, and say what will NOT happen so the
seeker can tell your forecast apart from a horoscope: "The promotion comes
between November 2026 and September 2027, not before. Nothing lands in the next
three months." If the honest answer is that the chart does not carry the thing
asked about, that sentence says so instead, and the rest explains why.

Then two or three short paragraphs of mechanism. Every placement you mention
must arrive already translated into a CONSEQUENCE the seeker could check against
their own life — what it does to them, not what it is.

  Write:       "Saturn sits in your sixth house, so one senior person keeps
                slowing your file. They are not going to become your supporter,
                and you do not need them to be."
  NEVER write: "Marital harmony is evaluated through the interaction between the
                Lagna and 7th house occupants." That is the method describing
                itself. The seeker did not ask how astrology works.

Never write "the principle is", "X is evaluated through", "this indicates that",
or any sentence whose subject is a technique rather than the seeker.

Register: second person, short sentences, present tense. Use their name if you
have it. Divisional charts get plain names in the prose — the D10 is the "career
chart", the D9 the "marriage chart", the D1 the "birth chart" — and D-codes
appear only in the reference block. Any Sanskrit term you use, gloss it in the
same breath in plain English, or leave it for the reference block.

Timing rules, which bind whatever you write. Settle the promise before any date
exists: if the chart does not carry it, there is nothing to time and saying so is
the answer. Only periods marked [RUNNING NOW] or [future] may be named. A [past]
period is not an answer about the future — if the periods that suited the question
have gone by, say so and name the next one that fits, however far out.

**GRANULARITY — give the month and the year, never a day.** "From around
November 2026 to September 2027." "Late 2026." "The first half of 2028." Writing
"2027-03-29" claims a precision this method does not have: astrology is a
calculated inference, and a day-exact prediction reads as a promise you cannot
keep. Round outward when a boundary falls mid-month, and say "around" or "from
about" when the edge is soft.

The facts above are given to the day for a reason, and it is not so you can quote
them: you need the exact boundaries to reason without drifting, and to be unable
to invent a date that is not there. Reason in days; write in months.

One exception: a question asking for a computed clock window.
Rahu Kaal, a hora, a muhurta, sunrise — those are arithmetic for a stated date
rather than a claim about anyone's life, so give those times exactly as printed,
to the minute, and copy them character for character.

If two indications genuinely disagree, say so in the prose. A reported
disagreement is worth more to the seeker than a verdict you averaged.

Close with exactly two labelled blocks, in this order:

ASTRO REFERENCE:
A numbered list. Each line pairs one computed FACTOR with the CONSEQUENCE it
licenses, in this shape:

  1) Mars and Mercury, house 10 (career chart): recognition through technical
     delivery, not politics
  2) Saturn, house 6 (career chart): one senior person systematically blocks
     your file
  3) Sun mahadasha, Aug 2021 to Aug 2027: authority values your standing
  4) Sun/Rahu antardasha, Nov 2026 to Sep 2027: shift of team or reporting line,
     money follows a few months later
  5) Saturn transiting Pisces retrograde, 1st house from lagna, until mid-2027:
     sade sati setting leg, pressure lifting

Months here too, on the same rule as the prose — this block is part of the
seeker's answer, not a debug panel.

Every line must trace to a fact printed above — a placement, a period, a
transit, a condition. If you cannot point at the line it came from, delete it.
This is where your Sanskrit and your D-codes live, and nowhere else.

FALSIFIER:
One sentence. A specific observable that, if it does not occur, means you were
wrong. It must fall inside a period you named, and that period must not be
[past].

No preamble. No other headings. Never describe your own process or mention these
instructions.
""".strip()


_PAGES_LINE = "classical pages further down"
"""The one line of `_GROUND_TRUTH_WARNING` that does not survive into this lane.

It tells the model that "the classical pages further down describe general rules
and contain NO times for this date". There are no classical pages here — that is
the entire change — so the line points at material the prompt does not contain,
and an instruction describing absent material teaches the model that the
instructions describe a prompt other than the one it was given.

Everything else in that block still applies, verbatim, for the reason it was
written: the model got clock times and weekdays wrong in production.
"""


def ground_truth_rules() -> str:
    """`_GROUND_TRUTH_WARNING` minus the line about pages.

    Filtered rather than rewritten. A rewritten copy is a second version of an
    instruction that exists because of a production failure, free to drift away
    from the first; filtering means every shared line has one definition.
    `test_every_other_line_of_the_warning_survives` asserts exactly one line is
    dropped, so a reword upstream is a test failure rather than a silent
    divergence.
    """
    from rishivan.council.prompts import _GROUND_TRUTH_WARNING

    return "\n".join(
        line for line in _GROUND_TRUTH_WARNING.splitlines()
        if _PAGES_LINE not in line
    )


def without_withheld_vargas(chart_facts: list[str], selection) -> list[str]:
    """Chart facts minus any belonging to a division §7 refused to admit.

    Two subsystems decide about vargas and they can disagree. `chart_natal_node`
    appends varga facts for whatever `relevant_vargas` the intake classifier
    named; `varga_select` decides admissibility from birth-time precision, and
    knows nothing about that list. When they disagree the facts arrive anyway.

    A real prompt carried ten D10 placements under WIDER CHART and, below them,
    "D10 ... I have not used it. Do not reason from these." That is a prompt
    arguing with itself, and the model has no way to referee it - a reader of
    the reading cannot tell whether the D10 evidence was used or not, which is
    exactly the thing the withheld list exists to make clear.

    The facts go; the *statement* that the division was withheld stays, since
    dropping both would leave a silence indistinguishable from a division that
    was never relevant.
    """
    if selection is None or not selection.withheld:
        return chart_facts
    # Varga fact lines from `local_varga.varga_facts` all carry the code
    # parenthesised - "Dashamsha chart (D10): ..." and "In your Dashamsha chart
    # (D10): Ascendant is ...". Matching on that rather than on the varga name
    # keeps this working if the display names are ever reworded.
    codes = tuple(f"({w.code})" for w in selection.withheld)
    return [fact for fact in chart_facts if not any(c in fact for c in codes)]


def history_block(conversation) -> str:
    """The transcript, with none of the voice instructions around it.

    `conversation.continuity_instruction` is the retrieval lane's version and is
    deliberately not reused: it tells the model not to greet the seeker again and
    to end on a new hook, which are persona instructions for a lane that has a
    persona. This one has neither, and inheriting them would put voice rules back
    into a prompt built to be graded on accuracy.

    The history itself is kept, though. Without it a follow-up answers as though
    asked cold, and a comparison would read that as a grounding failure rather
    than a memory one.
    """
    if conversation is None or conversation.is_empty:
        return ""
    return (
        "EARLIER IN THIS CONVERSATION — already established, do not contradict "
        "it and do not repeat it back:\n\n" + conversation.render()
    )


def _symbol(value) -> str:
    """`dignity.neutral` -> `neutral`, `graha.moon` -> `Moon`.

    Registry symbols are namespaced because the rule engine matches on them. A
    reading prompt does not, and asking the model to interpret this repo's join
    keys spends its attention on our vocabulary instead of the chart.
    """
    if value is None:
        return ""
    text = str(getattr(value, "value", value))
    return text.rsplit(".", 1)[-1]


def _condition_line(planet) -> str:
    """One graha's computed condition, in the order a reading needs it.

    Dignity and strength first because every §4-11 protocol has a strength step;
    the flags next because each one is a discount the tradition applies and none
    of them is visible in a sign-and-house line; received aspects last because
    they are the context for the rest.
    """
    name = _symbol(planet.graha).capitalize()
    parts = [f"dignity {_symbol(planet.dignity)}"]

    if planet.strength is not None:
        # The `is_estimated` caveat is stated once in the header rather than on
        # every line: nine identical parentheticals cost 300 characters to say
        # one thing, and a caveat repeated nine times is a caveat nobody reads.
        parts.append(f"strength {_symbol(planet.strength.band)}")

    if planet.functional_nature:
        parts.append(f"functionally {planet.functional_nature}")
    for flag, label in (
        (planet.combust, "COMBUST"),
        (planet.retrograde, "retrograde"),
        (planet.vargottama, "vargottama"),
    ):
        if flag:
            parts.append(label)

    # Grahas only. `aspects_received` also carries karaka.* and lord.bhava.*
    # symbols, which are join keys rather than aspecting bodies.
    aspects = [
        _symbol(a).capitalize()
        for a in (planet.aspects_received or ())
        if str(a).startswith("graha.")
    ]
    if aspects:
        parts.append(f"aspected by {', '.join(aspects)}")

    return f"  - {name}: {'; '.join(parts)}"


def _condition_block(chart_state) -> str:
    """Blueprint §6's diagnosis, sent rather than left to be re-derived.

    Everything here is computed, and until now none of it reached the prompt.
    The cost was measurable in a real reading: the model re-derived exaltation
    from raw signs, then wrote "there are no conflicting malefic afflictions to
    the 10th house or its ruler" about a chart whose Sun and Moon shared a
    nakshatra pada. It had no combustion flag and no aspect list to check, so
    that sentence was a guess wearing the clothes of a judgement.
    """
    if chart_state is None or not chart_state.planets:
        return ""

    # Conventional order, matching the placement lines above, so a reader
    # cross-referencing the two blocks is not re-sorting in their head. The
    # `planets` tuple arrives alphabetical, which no astrologer reads in.
    order = {name: index for index, name in enumerate(_PLANET_SEQUENCE)}
    planets = sorted(
        chart_state.planets,
        key=lambda p: order.get(_symbol(p.graha).capitalize(), 99),
    )

    estimated = any(
        p.strength is not None and p.strength.is_estimated for p in planets
    )
    caveat = (
        f"\nStrength bands come from `{chart_state.strength_system}`"
        + (", running partial - treat them as estimates, not measurements."
           if estimated else ".")
    )
    return (
        "PLANETARY CONDITION - computed, and authoritative. Do not re-derive any\n"
        "of it from the signs and houses above; where your own reading of the "
        "chart\ndisagrees with a line here, this is what the calculation says:"
        + caveat + "\n"
        + "\n".join(_condition_line(p) for p in planets)
    )


def _varga_block(chart, selection) -> str:
    """Divisional placements for the divisions §7 admitted, and why any were not.

    The placements rather than the codes. "D9 was selected" tells the model
    nothing it can read; a D9 confirmation step needs the actual signs.

    The withheld list is stated rather than dropped: "D60 needs a birth time to
    the minute and yours is recorded to the hour, so it was not used" is the
    sentence this selection exists to make available.

    D1 is skipped. It is not a division of the chart, it *is* the chart, and the
    framework and primary blocks already carry every one of its placements.
    Emitting it here restated all nine grahas in a second wording ("Rashi chart
    (D1): Sun is in Sagittarius in the house 10" beside "Sun is in Sagittarius
    in the 10th house"), which spends prompt on making the model work out
    whether the two are the same fact.
    """
    if chart is None or selection is None:
        return ""
    from rishivan.chart.local_varga import varga_facts

    lines: list[str] = []
    for code in selection.selected:
        if code == "D1":
            continue
        facts = varga_facts(chart, code)
        if facts:
            lines.extend(f"  - {fact}" for fact in facts)
    blocks = []
    if lines:
        blocks.append(
            "DIVISIONAL CHARTS admitted for this question:\n" + "\n".join(lines)
        )
    if selection.withheld:
        blocks.append(
            "DIVISIONS NOT USED, and why — do not reason from these:\n"
            + "\n".join(f"  - {w.code}: {w.reason}" for w in selection.withheld)
        )
    return "\n\n".join(blocks)


_SLOW_MOVERS = ("Jupiter", "Saturn", "Rahu", "Ketu")
"""Which transits can time a life event.

The fast planets change sign every few weeks and the Moon every 2¼ days, so a
reading that reaches for them is reaching for noise. Leaving them out is not an
omission - `facts.derive_facts` still reports the transiting Moon's nakshatra,
which is the literal answer to "which nakshatra is running for me", and that is
the only question it answers.
"""

_SADE_SATI_LEGS = {12: "rising", 1: "peak", 2: "setting"}
"""Saturn's position counted from the natal Moon sign.

The single most asked-about transit in the tradition. A reading that misses it
while the seeker's family is discussing it looks blind, and it costs two index
subtractions to know.
"""

_SCAN_COARSE_DAYS = 4
_SCAN_LIMIT_DAYS = 1200
"""How far to look for a sign change, and at what resolution.

Saturn holds a sign for about two and a half years and Rahu for eighteen months,
so 1200 days brackets any of them. A full chart costs 0.08 ms, which is what
makes a day-resolution scan cheaper than being clever about it.
"""


def _sign_change(graha: str, start, direction: int, lat, lon, tz_offset):
    """The first date `graha` is in a different sign than it is at `start`.

    Scanned rather than solved. A retrograde planet near a boundary crosses it
    more than once, so there is no single "exit" to compute - the honest answer
    is the NEXT change, in whichever direction was asked for, and a scan gives
    exactly that. Coarse steps to bracket it, then day steps to pin it.
    """
    from datetime import timedelta

    from rishivan.chart.transit import chart_for_moment

    def sign_at(offset_days: int) -> str:
        moment = start + timedelta(days=offset_days * direction)
        chart = chart_for_moment(moment, lat=lat, lon=lon, tz_offset=tz_offset)
        return chart.planets[graha].rashi

    origin = sign_at(0)
    offset = 0
    while offset < _SCAN_LIMIT_DAYS:
        offset += _SCAN_COARSE_DAYS
        if sign_at(offset) != origin:
            # Walk back to the first day that still differs.
            for day in range(offset - _SCAN_COARSE_DAYS + 1, offset + 1):
                if sign_at(day) != origin:
                    return start + timedelta(days=day * direction)
            return start + timedelta(days=offset * direction)
    return None


def transit_block(natal, when, *, lat=None, lon=None, tz_offset=None) -> str:
    """Where the slow planets are now, which of THIS chart's houses they cross,
    and when they move.

    Added after a competitor's answer timed a promotion entirely off a transit
    exit - "Jupiter transiting Cancer, house 7 from ascendant, until 31 Oct 2026
    … Nov 2026 door opens after this transit ends" - and ours could not, because
    the prompt had no transit data. Every protocol has a transit step; without
    this it was padded with the transiting Moon or declared unsupported.

    A transiting sign on its own says nothing. The house it crosses in this chart
    is the content, which is why the lagna is what everything is counted from.
    """
    if natal is None or when is None:
        return ""
    from rishivan.chart.ephemeris import RASHIS
    from rishivan.chart.transit import chart_for_moment

    # Defaults match `chart.transit`'s own, which are New Delhi. A transit's
    # SIGN barely moves with the observer - only the ascendant does, and nothing
    # here reads a transit ascendant.
    lat = 28.6139 if lat is None else lat
    lon = 77.2090 if lon is None else lon
    tz = 5.5 if tz_offset is None else tz_offset

    transiting = chart_for_moment(when, lat=lat, lon=lon, tz_offset=tz)
    lagna = RASHIS.index(natal.lagna_rashi)

    lines = []
    for graha in _SLOW_MOVERS:
        position = transiting.planets.get(graha)
        if position is None:
            continue
        sign = RASHIS.index(position.rashi)
        house = ((sign - lagna) % 12) + 1
        retro = " retrograde" if position.retrograde else ""
        entered = _sign_change(graha, when, -1, lat, lon, tz)
        leaves = _sign_change(graha, when, +1, lat, lon, tz)
        span = []
        if entered is not None:
            span.append(f"in this sign since {entered.date()}")
        if leaves is not None:
            span.append(f"leaves it {leaves.date()}")
        lines.append(
            f"  - {graha} transiting {position.rashi}{retro}, crossing your "
            f"{_ORDINAL.get(house, house)} house from your lagna"
            + (f" ({'; '.join(span)})" if span else "")
        )

    if not lines:
        return ""
    return (
        "TRANSITS NOW - the slow planets, and which of YOUR houses they are\n"
        "crossing. Dates are the sign changes; for a retrograde planet that is "
        "the\nnext crossing rather than a permanent exit:\n" + "\n".join(lines)
    )


def sade_sati_line(natal, transiting) -> str:
    """Saturn against the natal Moon.

    Split out of `transit_block` so a question profile can ask for it without
    asking for the whole transit table - a marriage question wants it, a
    temperament question wants neither.

    Reported either way. "Not running" is an answer a seeker who has been told
    otherwise by a relative deserves to hear, and it is the single most
    asked-about transit in the tradition.
    """
    if natal is None or transiting is None:
        return ""
    from rishivan.chart.ephemeris import RASHIS

    moon = natal.planets.get("Moon")
    saturn = transiting.planets.get("Saturn")
    if moon is None or saturn is None:
        return ""

    offset = ((RASHIS.index(saturn.rashi) - RASHIS.index(moon.rashi)) % 12) + 1
    where = (
        f"Saturn is in the {_ORDINAL.get(offset, offset)} sign from your natal "
        f"Moon in {moon.rashi}"
    )
    leg = _SADE_SATI_LEGS.get(offset)
    if leg:
        return f"Sade sati: RUNNING, {leg} leg ({where})."
    return (
        f"Sade sati: not running ({where}; it runs only from the 12th, 1st "
        "and 2nd)."
    )


def today_block(when) -> str:
    """The moment the reading is being made.

    Omitted from the first version of this prompt, and the omission was not
    cosmetic: the period block named the running dasha without ever saying what
    the date was, so nothing distinguished a window that had closed from one
    still ahead. A reading of "when will I get married?" duly offered an
    antardasha that had ended sixteen months before the question was asked, as
    "an earlier period of potential activation".

    The weekday is spelled out because `ground_truth_rules` tells the model to
    copy the weekday from the Date line rather than work it out - which requires
    there to be a Date line.

    No fallback to `datetime.now()`. A fabricated date is worse than none, and
    it would make the golden snapshot unpinnable as a side effect.
    """
    if when is None:
        return ""
    return (
        f"TODAY, the date this reading is being made: "
        f"{when.strftime('%A %Y-%m-%d')}.\n"
        "Every period below is marked against this date. A period that ended "
        "before\ntoday is past and cannot carry an event that has not happened "
        "yet - do not\noffer one as an answer to a question about the future, "
        "however well it fits."
    )


def _period_marker(period, when) -> str:
    """`[past]`, `[RUNNING NOW]` or `[future]`, against the reading date.

    Computed rather than left implicit. The model has the boundaries and the
    date and could in principle compare them, but "in principle" is what
    produced a closed window presented as a forecast.
    """
    if when is None:
        return ""
    if period.end <= when:
        return " [past]"
    if period.start <= when:
        return " [RUNNING NOW]"
    return " [future]"


def _sub_period_block(chart, when) -> str:
    """Antardasha and pratyantardasha boundaries for the periods running now.

    This replaces a five-stage `EventWindow` block, and the reason is worth
    keeping. That block was copied straight out of a real prompt as a dated
    forecast - "You will receive your major career promotion during 2026-08-27
    to 2027-08-07" - and its `activation` and `trigger` ranges were *identical*,
    both beginning on the query date, because `windows_between` anchors to
    `start=now`. It contained no event. It was the horizon restated, and a range
    that begins today reads as imminent whatever label sits above it. The
    `promise` flag it rested on was fabricated by `assume_promise=True` rather
    than established by anything.

    Sub-period boundaries carry no such implication. They are the granularity a
    timing answer needs - a mahadasha runs six to twenty years, which cannot
    time anything - and they say only when a period runs, never what it means.
    Deriving them here from the chart also means this lane no longer depends on
    the timing node or on a promise nobody made.
    """
    if chart is None:
        return ""
    from rishivan.chart.dasha import (
        current_periods, mahadasha_timeline, sub_periods,
    )

    running = current_periods(chart, when)
    maha, antar = running.get("maha"), running.get("antar")
    if maha is None:
        return ""

    def rows(periods) -> str:
        return "\n".join(
            f"  - {p.lord}: {p.start.date()} to {p.end.date()}"
            f"{_period_marker(p, when)}"
            for p in periods
        )

    blocks = [
        f"Antardashas within the running {maha.lord} mahadasha "
        f"({maha.start.date()} to {maha.end.date()}):\n"
        + rows(sub_periods(maha, "antar"))
    ]

    # The mahadasha after this one, broken down too. Without it a "when"
    # question whose answer falls past the current mahadasha has nowhere to
    # land: a reading named the next mahadasha correctly and then could not
    # time anything inside it, because only the current one was supplied. One
    # further mahadasha is 6-20 years of forward horizon for nine more lines.
    timeline = mahadasha_timeline(chart)
    following = next(
        (p for p in timeline if p.start >= maha.end), None
    )
    if following is not None:
        blocks.append(
            f"Antardashas within the following {following.lord} mahadasha "
            f"({following.start.date()} to {following.end.date()}):\n"
            + rows(sub_periods(following, "antar"))
        )

    if antar is not None:
        blocks.append(
            f"Pratyantardashas within the running {antar.lord} antardasha "
            f"({antar.start.date()} to {antar.end.date()}):\n"
            + rows(sub_periods(antar, "pratyantar"))
        )
    return "\n\n".join(blocks)


# ── Blocks a profile may ask for ─────────────────────────────────────────────

def _listed(heading: str, facts: list[str]) -> str:
    if not facts:
        return ""
    return heading + "\n" + "\n".join(f"  - {fact}" for fact in facts)


def _panchang_block(state, day_offset: int) -> str:
    """The daily windows for the date the question is about.

    This is the block whose absence produced the worst failure in the lane. Asked
    "Can I travel foreign tomorrow?" the reading answered "late 2026 or early
    2027" - because it had a decade of dasha boundaries and nothing at all about
    tomorrow, and a model with the wrong facts answers the question its facts fit.

    `compute_panchang` already took an arbitrary date and `relative_day_offset`
    already parsed "tomorrow"; neither had ever been called from this lane.

    Clock times stay exact. The granularity rule rounds PREDICTIONS to months;
    these are arithmetic for a stated date and the rule exempts them by name.
    """
    from datetime import timedelta

    from rishivan.chart.panchang import compute_panchang

    when = state.get("query_time")
    if when is None:
        return ""
    day = (when + timedelta(days=day_offset)).date()
    panchang = compute_panchang(
        day,
        lat=state.get("lat") or 28.6139,
        lon=state.get("lon") or 77.2090,
        tz_offset=state.get("tz_offset") or 5.5,
        place=state.get("place") or "",
    )
    label = {0: "TODAY", 1: "TOMORROW"}.get(day_offset, f"DAY +{day_offset}")
    return (
        f"DAILY WINDOWS FOR {label} — computed for this date and place. These are\n"
        "clock times, not predictions: copy them to the minute, exactly as "
        "printed:\n" + panchang.summary()
    )


def _bala_block(natal, transiting, *, want_tara: bool, want_chandra: bool) -> str:
    """The Moon's strength for an undertaking on the date in question.

    What a "should I do this on Tuesday" question is actually judged on, and what
    the lane had never computed - see `chart/bala.py`.
    """
    if natal is None or transiting is None:
        return ""
    from rishivan.chart.bala import chandra_bala, tara_bala

    natal_moon = natal.planets.get("Moon")
    transit_moon = transiting.planets.get("Moon")
    if natal_moon is None or transit_moon is None:
        return ""

    lines = []
    if want_tara:
        tara = tara_bala(natal_moon.nakshatra, transit_moon.nakshatra)
        if tara is not None:
            lines.append(f"  - {tara.describe()}")
    if want_chandra:
        chandra = chandra_bala(natal_moon.rashi, transit_moon.rashi)
        if chandra is not None:
            lines.append(f"  - {chandra.describe()}")
    if not lines:
        return ""
    return (
        "THE MOON'S STRENGTH FOR THIS UNDERTAKING — computed. A favourable tara "
        "or\nchandra bala is permission, never a promise; an unfavourable one is "
        "friction,\nnever a prohibition:\n" + "\n".join(lines)
    )


def _unavailable_block(unavailable: tuple[str, ...]) -> str:
    """What this reading cannot draw on, said once.

    Declared up front rather than discovered per step. A reading told nothing
    about its own gaps pads the step it cannot support - "interlocking dispositor
    dynamics validate institutional elevation" is filler in the shape of an
    answer, and it appeared because a Jaimini step was asked for and no Jaimini
    fact existed.
    """
    if not unavailable:
        return ""
    return (
        "EVIDENCE NOT AVAILABLE for this reading. Do not reason from these, do "
        "not\ninfer them, and do not pad a step with them. Work the step from "
        "what you\nhave, or let it lower your confidence in silence:\n"
        + "\n".join(f"  - {item}" for item in unavailable)
    )


def build_direct_prompt(state) -> str:
    """The whole prompt, from state, with no I/O.

    Two things govern what goes in. `constitution` says which houses and planets
    the domain rests on; `QuestionProfile` says which KINDS of fact the question
    needs. The second was missing, and its absence is why every question - a
    marriage timing, a character reading, a "can I fly tomorrow" - received the
    same sixty facts, and why a question about tomorrow was answered with a
    ten-year dasha forecast.

    Pure, so the golden snapshot is a real snapshot and `test_no_network` is a
    real guarantee. The model call lives in `council/direct.py`.
    """
    from rishivan.council.fact_table import (
        natal_rows, render_table, transit_rows,
    )
    from rishivan.council.question_profile import Bundle, profile_for

    constitution = constitution_for(state.get("koonji_domain") or "")
    profile = profile_for(
        state["question"], koonji_domain=state.get("koonji_domain") or ""
    )
    wants = profile.wants

    chart = state.get("chart")
    when = state.get("query_time")
    facts = _partition(
        without_withheld_vargas(
            state.get("chart_facts") or [], state.get("vargas")
        )
    )

    transiting = None
    moon_on_the_day = None
    if chart is not None and when is not None:
        from datetime import timedelta

        from rishivan.chart.transit import chart_for_moment

        lat = state.get("lat") or 28.6139
        lon = state.get("lon") or 77.2090
        tz = state.get("tz_offset") or 5.5

        if wants(Bundle.TRANSITS_SLOW) or wants(Bundle.SADE_SATI):
            transiting = chart_for_moment(when, lat=lat, lon=lon, tz_offset=tz)
        if wants(Bundle.TARA_BALA) or wants(Bundle.CHANDRA_BALA):
            # Cast for the DATE ASKED ABOUT, not for today. Tara and chandra bala
            # are entirely about the Moon, and the Moon changes sign every 2.25
            # days - computing them for today to answer a question about
            # tomorrow gets the answer wrong roughly a third of the time.
            moon_on_the_day = chart_for_moment(
                when + timedelta(days=profile.day_offset),
                lat=lat, lon=lon, tz_offset=tz,
            )

    parts = [framing_block(constitution)]

    history = history_block(state.get("conversation"))
    if history:
        parts.append(history)

    parts.append(method_block(constitution))
    parts.append(ground_truth_rules())

    today = today_block(when)
    if today:
        parts.append(today)

    if facts["framework"]:
        parts.append(_listed("THE FRAME OF THE CHART:", facts["framework"]))

    # One table, both frames. Transit rows join it only if the question needs
    # them - a temperament reading timed against a transit becomes a forecast
    # nobody asked for.
    rows = []
    if chart is not None:
        rows += natal_rows(chart, state.get("chart_state"))
        if transiting is not None and wants(Bundle.TRANSITS_SLOW):
            rows += transit_rows(chart, transiting)
    table = render_table(
        rows,
        primary=_question_planets(
            state.get("chart_facts") or [], constitution
        ),
    )
    parts.append(table if table else (
        "No chart was computed for this question - no birth details were given. "
        "Say\nso plainly rather than reading a chart you were not shown."
    ))

    if wants(Bundle.HOUSE_LORDS) and facts["lords"]:
        parts.append(_listed(
            "THE HOUSES AND WHO RULES THEM — a house is judged through its lord, "
            "and\nwhere that lord sits:", facts["lords"],
        ))

    if wants(Bundle.YOGAS) and facts["yogas"]:
        parts.append(_listed("COMBINATIONS DETECTED:", facts["yogas"]))

    if wants(Bundle.CONJUNCTIONS) and facts["conjunctions"]:
        parts.append(_listed("CONJUNCTIONS (natal):", facts["conjunctions"]))

    if wants(Bundle.VARGAS):
        varga = _varga_block(chart, state.get("vargas"))
        if varga:
            parts.append(varga)

    if wants(Bundle.SADE_SATI):
        sade = sade_sati_line(chart, transiting)
        if sade:
            parts.append(sade)

    if wants(Bundle.TRANSITS_SLOW):
        transits = transit_block(
            chart, when,
            lat=state.get("lat"), lon=state.get("lon"),
            tz_offset=state.get("tz_offset"),
        )
        if transits:
            parts.append(transits)

    if wants(Bundle.DASHA_CURRENT) and facts["periods"]:
        parts.append(
            "COMPUTED PERIODS — boundaries, not predictions. Every date you write\n"
            "must trace to one of these lines:\n"
            + "\n".join(f"  - {fact}" for fact in facts["periods"])
        )

    if wants(Bundle.DASHA_FORWARD):
        sub_periods = _sub_period_block(chart, when)
        if sub_periods:
            parts.append(sub_periods)

    if wants(Bundle.PANCHANG_FOR_DATE):
        panchang = _panchang_block(state, profile.day_offset)
        if panchang:
            parts.append(panchang)
        # `facts["transiting_moon"]` is deliberately not printed here. The bala
        # block below names the Moon's nakshatra and sign for the date asked
        # about, and the fact line is cast for `query_time` - so printing both
        # put two different Moons in one prompt, each labelled as current.

    bala = _bala_block(
        chart, moon_on_the_day,
        want_tara=wants(Bundle.TARA_BALA),
        want_chandra=wants(Bundle.CHANDRA_BALA),
    )
    if bala:
        parts.append(bala)

    unavailable = _unavailable_block(profile.unavailable)
    if unavailable:
        parts.append(unavailable)

    parts.append(_OUTPUT_BLOCK)
    parts.append(f"THE QUESTION: {state['question']}")

    return "\n\n---\n\n".join(parts)
