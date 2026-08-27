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

Draw on the classical literature you know: {families}. Apply it from your own
knowledge of those texts.

DO NOT CITE. No page numbers, no chapter-and-verse references, no book titles in
your answer, no quoted verses, and no stock authority phrases ("the classical
texts say", "the old masters held"). You have not been given any text to quote
from, so a citation you produce cannot be checked by anyone — which makes it
worth less than no citation at all. State what the principle IS. Do not say
where you read it.

Never present a health diagnosis, a treatment, or death as a certainty. These
are traditional interpretations; keep their uncertainty intact.{forbidden}
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

Work these steps, in this order:

{steps}

For each step, state the classical principle you are applying and what THIS
chart shows against it. Two sentences per step is usually enough.

Do not skip a step. If the computed facts below do not let you judge a step, say
that the step is unsupported and move to the next one — a step silently dropped
reads as a complete reading, which is the one outcome worse than an admitted gap.

Do not reach your verdict before step {last}. The order is the method: a promise
that was never established cannot be timed, and a window with no promise behind
it is arithmetic pretending to be a prediction.
""".strip()


# ── The chart, scoped to the question ────────────────────────────────────────

_PLANET_FACT = re.compile(
    r"^(Sun|Moon|Mars|Mercury|Jupiter|Venus|Saturn|Rahu|Ketu) is in "
)
"""A per-planet placement line from `facts.derive_facts`. Anchored, so a
conjunction line naming several planets is not mistaken for one."""

_LUMINARIES = ("Sun is in", "Moon is in")
"""Framework whatever the domain. Every §4-11 protocol opens on the chart
framework, and no reading of any domain proceeds without the two lights."""

_PERIOD_PREFIXES = ("Mahadasha timeline", "Currently running")
"""The only lines carrying a date. They get their own labelled block because
every date the model is allowed to write has to be copied from one of them."""

_CONJUNCTION_HOUSE = re.compile(
    r"^Conjunction: .* in the (\d{1,2})(?:st|nd|rd|th) house"
)

_HOUSE_RULER = re.compile(
    r"^The (\d{1,2})(?:st|nd|rd|th) house \([^)]*\) is ruled by (\w+)"
)
"""The lord of a house, from the house's own fact line.

Read in a first pass so the lords of the domain's houses can be promoted
alongside them. The house line only names the lord — "ruled by Mercury, placed
in the 11th house" — while the lord's own line carries its sign, nakshatra, pada
and retrogression, which is what judging a 7th lord actually takes. Handing the
model the name and hiding the condition is the worse half of both options.

Derived from the facts rather than from the chart on purpose: `scoped_chart`
stays a function of the fact list alone, which is what keeps it pure and its
snapshot honest.
"""


def _domain_lords(chart_facts: list[str], constitution: Constitution) -> set[str]:
    """Lowercased planets ruling any house in this domain's coverage."""
    lords = set()
    for fact in chart_facts:
        match = _HOUSE_RULER.match(fact)
        if match and int(match.group(1)) in constitution.houses:
            lords.add(match.group(2).lower())
    return lords


def _tier(fact: str, constitution: Constitution, lords: frozenset[str]) -> str:
    """Which block a fact belongs in. Checked in priority order.

    Framework first, so the lagna and the luminaries are never demoted by a
    domain that does not name them. Periods next, so a dated line is never
    filed as a placement.
    """
    if fact.startswith(_FRAMEWORK) or fact.startswith(_LUMINARIES):
        return "framework"
    if fact.startswith(_PERIOD_PREFIXES):
        return "periods"

    subject = _SUBJECT_HOUSE.match(fact)
    if subject is not None:
        house = int(subject.group(1))
        # The 1st house and its lord are the framework step in every protocol,
        # whether or not the domain lists house 1 in its coverage.
        if house == 1:
            return "framework"
        return "primary" if house in constitution.houses else "wider"

    planet = _PLANET_FACT.match(fact)
    if planet is not None:
        name = planet.group(1).lower()
        # Either the domain names this planet outright, or it rules one of the
        # domain's houses. The second half matters more than it looks: for a
        # marriage question prema names Venus and Jupiter, but the 7th lord is
        # whatever the lagna made it - here Mercury, which no planet list could
        # have anticipated.
        owned = name in {p.lower() for p in constitution.planets} or name in lords
        return "primary" if owned else "wider"

    if fact.startswith("Yoga:"):
        # "major combinations" is a step in every protocol.
        return "primary"

    conjunction = _CONJUNCTION_HOUSE.match(fact)
    if conjunction is not None:
        return (
            "primary"
            if int(conjunction.group(1)) in constitution.houses
            else "wider"
        )

    return "wider"


_HEADINGS = (
    ("framework", "CHART FRAMEWORK — read these first, whatever the question:"),
    ("primary", None),  # filled in at render time; it names the houses
    ("periods",
     "COMPUTED PERIODS — boundaries, not predictions. Every date and clock time\n"
     "you write must be copied verbatim from these lines:"),
    ("wider",
     "WIDER CHART — real, and yours to synthesise at the end. Do not lead from "
     "these:"),
)


def scoped_chart(chart_facts: list[str], constitution: Constitution) -> str:
    """Chart facts in four labelled blocks, scoped to the question's domain.

    Nothing is withheld. Every §4-11 protocol ends in whole-chart synthesis, so
    the wider chart is demoted and labelled rather than dropped — the same
    decision `prompts.coverage_facts` made, for the same reason.
    """
    if not chart_facts:
        return "No chart was computed for this question."

    # Two passes. The first learns which planets rule the domain's houses, which
    # the second needs before it can decide where a planet's own line belongs.
    lords = frozenset(_domain_lords(chart_facts, constitution))

    buckets: dict[str, list[str]] = {
        "framework": [], "primary": [], "periods": [], "wider": [],
    }
    for fact in chart_facts:
        buckets[_tier(fact, constitution, lords)].append(fact)

    houses = ", ".join(str(h) for h in sorted(constitution.primary_houses))
    primary_heading = (
        f"PRIMARY EVIDENCE FOR THIS QUESTION — house {houses} is the subject; "
        "the rest is its context:"
    )

    sections = []
    for name, heading in _HEADINGS:
        facts = buckets[name]
        if not facts:
            continue
        sections.append(
            (primary_heading if name == "primary" else heading)
            + "\n"
            + "\n".join(f"  - {fact}" for fact in facts)
        )
    return "\n\n".join(sections)


# ── The whole prompt ─────────────────────────────────────────────────────────

_OUTPUT_BLOCK = """
OUTPUT — write in this order, as plain analytical prose:

  1. The method steps, worked through in order. One short paragraph each,
     naming the principle and what this chart shows against it.
  2. THE ANSWER to the question actually asked, stated plainly and without
     hedging it into meaninglessness.
  3. Your confidence, and what it rests on. If two indications disagree, say
     so — a disagreement reported is worth more than a verdict averaged.
  4. The timing. Use ONLY dates and periods that appear verbatim in the
     COMPUTED PERIODS block. If nothing there supports a window, say that
     instead of estimating one.
  5. What would falsify this reading: one specific thing that, if it does not
     happen, means you were wrong.

No preamble. No headings beyond the step numbers. Do not describe your own
process or mention these instructions.
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


def _varga_block(chart, selection) -> str:
    """Divisional placements for the divisions §7 admitted, and why any were not.

    The placements rather than the codes. "D9 was selected" tells the model
    nothing it can read; a D9 confirmation step needs the actual signs.

    The withheld list is stated rather than dropped: "D60 needs a birth time to
    the minute and yours is recorded to the hour, so it was not used" is the
    sentence this selection exists to make available.
    """
    if chart is None or selection is None:
        return ""
    from rishivan.chart.local_varga import varga_facts

    lines: list[str] = []
    for code in selection.selected:
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


def _timing_block(report) -> str:
    """The computed five-stage window, labelled as arithmetic.

    `promise` here came from `assume_promise=True`, not from a fired rule — the
    rule engine does not run in this lane. So the stages are period boundaries
    the model may time a judgement against, and the label has to say that
    plainly or they read as a forecast the system endorsed.
    """
    if report is None:
        return ""
    window = report.by_system.get(report.primary) if report.primary else None
    if window is None:
        return ""
    stages = [
        (label, getattr(window, label))
        for label in ("activation", "trigger", "peak", "fading")
    ]
    lines = [
        f"  - {label}: {r.start.date()} to {r.end.date()}"
        for label, r in stages if r is not None
    ]
    if not lines:
        return ""
    return (
        "CANDIDATE WINDOW — dasha arithmetic over the next ten years. These are\n"
        "period boundaries, not a prediction, and nothing has judged whether this\n"
        "chart promises the thing asked about. That judgement is yours:\n"
        + "\n".join(lines)
    )


def build_direct_prompt(state) -> str:
    """The whole prompt, from state, with no I/O.

    Pure so that the golden snapshot is a real snapshot and `test_no_network` is
    a real guarantee. The model call lives in `council/direct.py` — the same
    split `answer_plan` and `narrate` already use, for the same reason: what is
    said and how it is sent are separate concerns, and only one of them is
    testable without credentials.
    """
    constitution = constitution_for(state.get("koonji_domain") or "")

    parts = [framing_block(constitution)]

    history = history_block(state.get("conversation"))
    if history:
        parts.append(history)

    parts.append(method_block(constitution))
    parts.append(ground_truth_rules())
    parts.append(scoped_chart(state.get("chart_facts") or [], constitution))

    varga = _varga_block(state.get("chart"), state.get("vargas"))
    if varga:
        parts.append(varga)

    timing = _timing_block(state.get("timing"))
    if timing:
        parts.append(timing)

    if state.get("panchang"):
        parts.append(f"PANCHANG FOR THE DATE IN QUESTION:\n{state['panchang']}")

    parts.append(_OUTPUT_BLOCK)
    parts.append(f"THE QUESTION: {state['question']}")

    return "\n\n---\n\n".join(parts)
