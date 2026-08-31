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


def _house_lord_lines(chart) -> list[str]:
    """The twelve houses, their lords, and where those lords sit.

    Built from `chart.house_lords` rather than fished out of the fact list.
    `derive_facts` emits these lines and `derive_muhurta_facts` does not, so a
    prompt built on the moment-chart path had no lords at all - a FLOOR bundle
    silently unsatisfied, which is precisely what a floor exists to prevent.
    """
    if chart is None:
        return []
    from rishivan.chart.facts import _HOUSE_TOPIC, _ORDINAL

    lines = []
    for house in range(1, 13):
        lord = chart.house_lords[house]
        position = chart.planets.get(lord)
        where = (
            f"placed in the {_ORDINAL[position.house]} house"
            if position is not None else "position unknown"
        )
        lines.append(
            f"The {_ORDINAL[house]} house ({_HOUSE_TOPIC[house]}) is ruled by "
            f"{lord}, {where}."
        )
    return lines


def _question_planets(chart, constitution: Constitution) -> set[str]:
    """Which planets this question rests on: the domain's own, plus the lords of
    its houses.

    The second half is what a planet list cannot anticipate. For a marriage
    question prema names Venus and Jupiter, and the 7th lord is whichever graha
    the lagna assigned. Read off the chart rather than off the fact strings, so
    it works whichever fact builder ran - a travel reading left Venus in the 9th
    unmarked because the lord lines it parsed were not there.
    """
    planets = {p.capitalize() for p in constitution.planets}
    if chart is not None:
        for house in constitution.houses:
            planets.add(chart.house_lords[house].capitalize())
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

Two exceptions. A question about a named day - "can I travel tomorrow" - is
answered for that day, so name it: the date is the question's own, not a
prediction you narrowed to it.

And a question asking for a computed clock window.
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


_ANALYSIS_OUTPUT_BLOCK = """
OUTPUT

You are the reasoning half of a two-step reading. **You do not write to the
seeker.** A second model turns what you return into prose for them, and it will
see your output and nothing else - not this chart, not these periods, not this
method. Anything you leave out is unavailable to it, permanently. Anything you
put in, it will say.

Return the structured verdict, and nothing besides it. No prose, no preamble, no
commentary on your own process.

How to fill it, field by field.

**promise** comes first and governs everything after it. Settle whether the
chart carries the thing asked about AT ALL before you look at a single date. If
it does not, say `absent` - and then there is nothing to time, every window you
might have listed is void, and the honest reading is that the chart does not
speak to this. `contested` is for a chart that carries it and argues with
itself; use it rather than picking a side quietly.

**headline** is the answer in one sentence, written as a finding rather than as
a summary. "The promotion lands between November 2026 and September 2027, not
before." Under an absent promise it says so instead. The narrator leads with
this, so a headline that describes your reasoning becomes a reading that opens
by clearing its throat.

**not_happening** is what will NOT occur. This is what separates a forecast from
a horoscope, and it is the line a seeker uses to tell whether you committed to
anything. Leave it empty only when the question genuinely does not admit one.

**factors** is where the chart enters. One entry per computed factor that
actually bears on the answer, each already translated:

    fact:        "Saturn, house 6 (career chart)"
    consequence: "one senior person keeps slowing your file, and they are not
                  going to become your supporter"

The `fact` half must trace to a line printed above - a placement, a period, a
transit, a condition. If you cannot point at the line it came from, leave the
entry out. The `consequence` half must be something the seeker could check
against their own life. Never "marital harmony is evaluated through the 7th
house": that is the method describing itself, the seeker did not ask how
astrology works, and the narrator has no way to repair it because it cannot see
what you were looking at. Sanskrit and D-codes belong in `fact`, never in
`consequence`.

Order them by how much they carry, heaviest first, and set `weight` honestly. A
weak factor marked strong is worse than one you omitted.

**windows** — and before the dates, the LEVEL, because getting that wrong is how
this reading goes wrong. A mahadasha sets the era, an antardasha sets the theme,
and a PRATYANTARDASHA is when a thing actually lands. Timing an event to an
antardasha alone times it to a three-year band, which is not an answer to "when".

**Take the nearest window that fits.** The block headed "WINDOWS THAT COULD CARRY
THIS EVENT" has already done the search, across both levels, nearest first — use
it rather than hunting through the period lists for something else. A later
period ruled by the same graha is not the better answer for being longer. If you
reach past a near window, say what disqualifies it, in the reading.

windows carry ISO dates, copied character for character from the computed
periods above. **Do not derive a boundary, ever** - not by adding a dasha
fraction, not by rounding, not by reasoning about what must come next. A date
that does not appear verbatim above is discarded before the narrator sees it,
so deriving one costs you the window rather than gaining you a prediction. Mark
`status` from the labels printed above: `past`, `running`, `future`. A past
window is not an answer about the future; list it only if the answer genuinely
turns on something already over, and expect it to be dropped.

You reason in days because you need exact boundaries not to drift. The seeker
is told months - the narrator does that conversion, and it needs the exact
dates to do it from.

**exact_times** is the one exception to all of the above: Rahu Kaal, a hora, a
muhurta, sunrise. Arithmetic for a stated date rather than a claim about
anyone's life. Copy the value exactly as printed, to the minute, character for
character. These reach the seeker at full precision.

**disagreements** is for indications that genuinely point different ways. Report
the disagreement; do not average it. A reported disagreement is worth more to
the seeker than a verdict you smoothed, and averaging tells them something false
with more confidence than either indication had.

**unsupported** is for steps of the method you could not run, and why. Declaring
a step unsupported is a correct outcome. Padding it from general knowledge is
not.

**Write these for the seeker, not for us.** They are printed in the answer, so
copy nothing from the EVIDENCE NOT AVAILABLE block above - that block is
addressed to you and is written in this system's own words. "step 4 (D9
confirmation): the D9's placements - required for this question, and this chart
does not yield it" reached a reader verbatim and read as a fault report.
Write "the marriage chart could not be cast from a birth time recorded only to
the hour" instead: name the step in plain English, say what it cost, and stop.

**falsifier** is one specific observable that, if it does not occur, means you
were wrong. It must fall inside a window you listed.
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
    # `fact_table._SEQUENCE` is the order an astrologer reads grahas in, and is
    # imported rather than restated. This line referred to a `_PLANET_SEQUENCE`
    # that was never defined in this module - the block was written, never
    # called, and would have raised NameError the first time anything asked for
    # it. The requirement registry asks for it, which is how it came to light.
    from rishivan.council.fact_table import _SEQUENCE

    order = {name: index for index, name in enumerate(_SEQUENCE)}
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


def _varga_block(chart, selection, *, notes_only: bool = False) -> str:
    """Divisional placements for the divisions §7 admitted, and why any were not.

    The placements rather than the codes. "D9 was selected" tells the model
    nothing it can read; a D9 confirmation step needs the actual signs.

    The withheld list is stated rather than dropped: "D60 needs a birth time to
    the minute and yours is recorded to the hour, so it was not used" is the
    sentence this selection exists to make available.

    `notes_only` returns just that withheld list. The placements themselves are
    now a requirement (`block.varga.d9`) so they land in the band the table gave
    them, but a division DECLINED is not a fact any requirement asked for - it is
    a fact about the reading, and it is reported whatever was asked.

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
    if not notes_only:
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


_BAND_HEADERS: dict[int, str] = {
    1: (
        "════════ RULE ON THIS ════════\n"
        "The classical method for this question says the verdict rests on the "
        "facts in\nthis section. Ground your answer in them. Nothing after this "
        "section may carry\nthe verdict on its own."
    ),
    2: (
        "════════ CORROBORATE ════════\n"
        "Use these to confirm, qualify or contradict the section above. A "
        "contradiction\nhere is evidence: report it rather than resolving it "
        "quietly."
    ),
    3: (
        "════════ CONTEXT ════════\n"
        "Background. Real, and yours to synthesise, but do not lead from it."
    ),
}
"""What each priority band tells the model.

The ordering used to be fixed in this file regardless of what was asked: the
same block sequence for a marriage question and a muhurta. Now the requirement
table chooses the order and these headers say what the order MEANS - which is
the half that a reordering alone would not have bought. A model handed twelve
undifferentiated blocks treats them as twelve equal facts, and the whole
complaint about the first two-call output was that it weighted general strength
the same as the seventh house.
"""


def _protocol_step(constitution_key: str, step: int) -> str:
    """The classical step a requirement serves, named.

    Missing facts read very differently with it: "step 5 (Jaimini indicators):
    Darakaraka" says which part of the reading was skipped, where the bare key
    says only that something was.
    """
    if not constitution_key or step < 1:
        return ""
    from rishivan.council.constitution import CONSTITUTIONS

    constitution = CONSTITUTIONS.get(constitution_key)
    if constitution is None or step > len(constitution.protocol):
        return ""
    return f"step {step} ({constitution.protocol[step - 1]})"


def _requirement_blocks(profile, ctx) -> tuple[list[str], list[str]]:
    """Render what this question requires, and report what it could not get.

    Two kinds of absence, kept apart because they mean different things to a
    reader and to whoever is fixing the system:

      * **No producer at all.** Nothing in this codebase computes it, for any
        chart. Always declared, mandatory or not - `prema`'s protocol step 5 is
        "Jaimini indicators" and `blocked_concepts` has said Darakaraka is
        unavailable since the constitutions were written. Stating it is the
        honest half of a reading that skips the step.
      * **A producer that returned nothing.** The capability exists; this chart
        or this moment did not yield it. Declared only when mandatory, because
        "no sade sati" on a chart with no Saturn transit is not news.
    """
    from rishivan.council.requirements.producers import known, label, produce

    rendered: list[str] = []
    missing: list[str] = []
    constitution_key = getattr(profile.requirements, "constitution", "")

    for priority, group in profile.requirements.by_band().items():
        blocks: list[str] = []
        for requirement in group:
            text = produce(requirement.key, ctx)
            if text:
                blocks.append(text)
                continue
            step = _protocol_step(constitution_key, requirement.step)
            where = f"{step}: " if step else ""
            if not known(requirement.key):
                missing.append(
                    f"{where}{label(requirement.key)} - this system does not "
                    f"compute it at all"
                )
            elif requirement.mandatory:
                missing.append(
                    f"{where}{label(requirement.key)} - required for this "
                    f"question, and this chart does not yield it"
                )
        if blocks:
            header = _BAND_HEADERS.get(priority, _BAND_HEADERS[3])
            rendered.append(header + "\n\n" + "\n\n".join(blocks))
    return rendered, missing


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


def build_direct_prompt(state, *, for_analysis: bool = False) -> str:
    """The prompt alone. See `build_with_report` for the prompt and its audit.

    Kept as the one-value function because every existing caller wants a string
    and the golden snapshot asserts one. The report is additive."""
    return build_with_report(state, for_analysis=for_analysis)[0]


def build_with_report(state, *, for_analysis: bool = False) -> tuple[str, dict]:
    """The whole prompt, from state, with no I/O.

    `for_analysis` swaps the closing OUTPUT block and changes nothing else. Both
    lanes reason over exactly the same chart, the same method and the same facts;
    what differs is only who the answer is being written for. Keeping one builder
    rather than two is what stops a fix to the fact selection landing in one lane
    and missing the other - the same argument `build_graph` makes for holding two
    topologies over one node set.

    Two things govern what goes in. `constitution` says which houses and planets
    the domain rests on; `QuestionProfile` says which KINDS of fact the question
    needs. The second was missing, and its absence is why every question - a
    marriage timing, a character reading, a "can I fly tomorrow" - received the
    same sixty facts, and why a question about tomorrow was answered with a
    ten-year dasha forecast.

    Pure, so the golden snapshot is a real snapshot and `test_no_network` is a
    real guarantee. The model call lives in `council/direct.py`.
    """
    from rishivan.council.question_profile import profile_for
    from rishivan.council.requirements.producers import Context

    constitution = constitution_for(state.get("koonji_domain") or "")

    # Which chart is in hand. `chart_moment_node` casts for the moment of asking
    # and discards birth_data entirely, so a MUHURTA or PRASHNA classification
    # leaves no nativity at all - and labelling those rows `natal` told the model
    # they were the seeker's birth placements.
    is_natal = state.get("chart_kind", "natal") == "natal"

    profile = profile_for(
        state["question"],
        koonji_domain=state.get("koonji_domain") or "",
        has_birth_chart=is_natal and state.get("chart") is not None,
    )
    needs = {r.key for r in profile.requirements.requires}

    chart = state.get("chart")
    when = state.get("query_time")
    facts = _partition(
        without_withheld_vargas(
            state.get("chart_facts") or [], state.get("vargas")
        )
    )

    # Computed once and handed to every producer. Eleven producers each casting
    # their own transit chart is eleven ephemeris calls for one answer.
    transiting = None
    moon_on_the_day = None
    if chart is not None and when is not None:
        from datetime import timedelta

        from rishivan.chart.transit import chart_for_moment

        lat = state.get("lat") or 28.6139
        lon = state.get("lon") or 77.2090
        tz = state.get("tz_offset") or 5.5

        if needs & {"block.transits_slow", "block.sade_sati"} or any(
            key.startswith("block.transit.") for key in needs
        ):
            transiting = chart_for_moment(when, lat=lat, lon=lon, tz_offset=tz)
        if needs & {"block.tara_bala", "block.chandra_bala"}:
            # Cast for the DATE ASKED ABOUT, not for today. Tara and chandra bala
            # are entirely about the Moon, and the Moon changes sign every 2.25
            # days - computing them for today to answer a question about
            # tomorrow gets the answer wrong roughly a third of the time.
            moon_on_the_day = chart_for_moment(
                when + timedelta(days=profile.day_offset),
                lat=lat, lon=lon, tz_offset=tz,
            )

    ctx = Context(
        state=state, chart=chart, chart_state=state.get("chart_state"),
        when=when, transiting=transiting, moon_on_the_day=moon_on_the_day,
        facts=facts, day_offset=profile.day_offset, is_natal=is_natal,
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

    if not is_natal:
        parts.append(
            "THIS IS A PRASHNA READING. No birth details were given, so the chart "
            "below\nis cast for the moment the question was asked - it is not a "
            "nativity. Read the\nlagna, the lagna lord and the Moon of THIS "
            "moment, and the house of the matter\nasked about. Do not describe "
            "any placement below as something the seeker was\nborn with, and do "
            "not speak of lifelong tendencies: this chart answers one\nquestion "
            "asked at one moment, and nothing more.\n\n"
            "Where a step in the reading method says NATAL, there is no nativity "
            "to read\nit from - take the lagna and lagna lord of THIS moment as "
            "what carries the\nmatter instead. Where a step names a dasha, skip "
            "it: Vimshottari is counted\nfrom the birth Moon, and that is not "
            "known here."
        )

    if facts["framework"]:
        parts.append(_listed("THE FRAME OF THE CHART:", facts["framework"]))

    if chart is None:
        parts.append(
            "No chart was computed for this question - no birth details were "
            "given. Say\nso plainly rather than reading a chart you were not shown."
        )

    # Everything from here is chosen by the requirement table, ordered by the
    # band it was assigned and, inside a band, by the protocol step it serves.
    # The vargas the §7 policy withheld are still reported: a division declined
    # for low birth confidence is a fact about the reading, not an omission.
    rendered, missing = _requirement_blocks(profile, ctx)
    parts.extend(rendered)

    varga_notes = _varga_block(chart, state.get("vargas"), notes_only=True)
    if varga_notes:
        parts.append(varga_notes)

    unavailable = _unavailable_block(tuple(missing) + profile.unavailable)
    if unavailable:
        parts.append(unavailable)

    parts.append(_ANALYSIS_OUTPUT_BLOCK if for_analysis else _OUTPUT_BLOCK)
    parts.append(f"THE QUESTION: {state['question']}")

    # The audit half. Which requirements were asked for, which could not be met,
    # and whether the table came from Mongo or the built-in copy - all three are
    # facts about the reading rather than about the chart, so they travel beside
    # the prompt instead of inside it.
    report = {
        "domain": profile.requirements.domain,
        "kind": profile.kind.value,
        "constitution": profile.requirements.constitution,
        "source": profile.requirements.source.value,
        "required": len(profile.requirements.requires),
        "satisfied": len(profile.requirements.requires) - len(missing),
        "missing": list(missing),
    }
    return "\n\n---\n\n".join(parts), report
