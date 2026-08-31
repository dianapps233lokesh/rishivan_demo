"""Which facts a question needs. A table, not a model call.

**The gap this closes.** Nothing in the pipeline mapped question type to required
computations. `constitution` maps a life domain to HOUSES, which answers "which
houses matter for marriage" and says nothing about "what must be computed to rule
on tomorrow". So every question received the same sixty-odd facts, and asked "Can
I travel foreign tomorrow?" the reading answered "late 2026 or early 2027" —
because it had a ten-year dasha forecast and no panchang, and a model with the
wrong facts answers the question its facts fit.

**Deterministic, and deliberately model-free**, on the argument `hierarchy_node`
already makes: "A classifier call here would be one more thing to be
irreproducible about." Three of the four decisions were already keyword tables in
this repo — `panchang.relative_day_offset`, `panchang.mentions_panchang`,
`koonji.router.parse` — and the fourth is a table too. Same question, same facts,
every time, which is what makes an accuracy comparison mean anything.

**The floor cannot be dropped.** Whatever the question, the placements, the house
lords, their condition and the running period are always sent. A reading cannot be
right without them, and a missing fact is invisible in fluent prose — nothing
downstream can tell that the 7th lord was never considered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QuestionKind(str, Enum):
    WHEN_WILL = "when_will"
    OK_ON_DATE = "ok_on_date"
    WHAT_IS_IT_LIKE = "what_is_it_like"
    WHICH_OPTION = "which_option"


"""The fact menu, the floor and the per-kind table all moved to
`council/requirements/`. They are not duplicated here, and that is the point:
two tables deciding which facts a question gets is two tables that will
disagree, and the disagreement is invisible in fluent prose. What stays in this
module is the one thing the registry cannot do - reading a question and deciding
what KIND it is."""


_TIMING_PHRASES = (
    "when will", "when do", "when can", "when am i", "how soon",
    "kab hoga", "kab hogi", "kab tak", "kab ", "how long until",
    # Promise questions belong here too, and a sanity check is what showed it:
    # "will I be wealthy?" was landing in WHAT_IS_IT_LIKE and so came back with
    # no forward periods at all. Someone asking "will I" wants the yes AND the
    # when, and WHEN_WILL's bundle set is exactly promise-plus-timing.
    "will i ", "will my ", "am i going to", "do i have any chance",
    "hoga kya", "hogi kya",
    # "How is my health going forward?" was landing in WHAT_IS_IT_LIKE and so
    # got neither transits nor forward periods - a question with "going forward"
    # in it, treated as a question about character.
    "going forward", "in the future", "ahead of me", "coming years",
)
"""Longest and most specific first. Trailing spaces are load-bearing: `kab ` and
`will i ` must not fire inside another word."""

_DATE_PHRASES = (
    "can i", "should i", "is it good", "is it ok", "is it safe",
    "shubh", "auspicious", "muhurat", "muhurta", "good day", "good time",
)

_CHOICE_MARKERS = (" or ", " ya ", " athava ")


def _kind(question: str, day_offset: int) -> QuestionKind:
    """Which kind of question this is.

    Order matters. A choice is checked before a date because "should I go Tuesday
    or Wednesday" is a choice question that also names days. A date question is
    checked before timing because "can I travel tomorrow" contains neither a
    timing phrase nor, importantly, any need for one.
    """
    from rishivan.chart.panchang import mentions_panchang

    lowered = f" {question.lower().strip()} "

    if any(marker in lowered for marker in _CHOICE_MARKERS):
        return QuestionKind.WHICH_OPTION
    # A question that names a daily window IS a date question, whatever else it
    # looks like. "What is the Rahu Kaal today?" was landing in WHAT_IS_IT_LIKE
    # and so received no panchang at all - the purest panchang question there is,
    # answered without one, because "what is the" matches no date phrase.
    # `mentions_panchang` already existed and was simply never consulted here.
    if mentions_panchang(question):
        return QuestionKind.OK_ON_DATE
    if any(phrase in lowered for phrase in _TIMING_PHRASES):
        return QuestionKind.WHEN_WILL
    if day_offset != 0 or any(phrase in lowered for phrase in _DATE_PHRASES):
        return QuestionKind.OK_ON_DATE
    # The least committal default, deliberately. An unplaceable question treated
    # as a timing question is how a vague query acquires a date it never asked
    # for.
    return QuestionKind.WHAT_IS_IT_LIKE


_NEEDS_A_NATIVITY = (
    "block.dasha.current", "block.dasha.forward", "block.dasha.pratyantar",
    "block.tara_bala", "block.chandra_bala", "block.sade_sati",
)

_NEEDS_A_NATIVITY_PREFIXES = ("karaka.", "from_arudha_lagna.")
"""Techniques that describe a NATIVE, and so describe nobody on a prashna chart.

The chara karakas rank the native's own grahas by degree to name their karmic
significators; an arudha pada is derived from the birth lagna. Computed off the
moment a question was asked they still produce a graha and a sign, and the
answer is about 2:32 that afternoon rather than about the seeker.

That is not hypothetical. A prashna marriage reading returned "Darakaraka Sun in
the 6th house - the specific indicator for the spouse is also caught in a house
of disputes", weighted it `moderate`, and used it to support a verdict that the
chart carried no promise. Same defect as the tara bala failure recorded in
`NO_BIRTH_CHART_UNAVAILABLE`: a birth-relative technique fed something that is
not a birth, returning a confident answer to a question nobody asked.
"""
"""Requirements that degenerate without a birth chart rather than failing.

Every one of these failed silently before. Tara bala came back Janma every time
- the moment chart's Moon measured against itself - and a reading built real
advice on it. Dropped rather than left to return None, because a mandatory
requirement that returns None is DECLARED missing, and declaring "the dasha
could not be computed" on a prashna reading is noise: it was never available and
`NO_BIRTH_CHART_UNAVAILABLE` already says so, once, in plain words.
"""


@dataclass(frozen=True, slots=True)
class QuestionProfile:
    kind: QuestionKind
    day_offset: int
    requirements: Any
    """The `RequirementSet` for this (domain, kind), from Mongo or the built-in
    catalogue. Carries its own `source`, so whatever renders it can say which."""

    unavailable: tuple[str, ...] = field(default=())
    reason: str = ""

    def needs(self, key: str) -> bool:
        return any(r.key == key for r in self.requirements.requires)


NO_BIRTH_CHART_UNAVAILABLE = (
    "the birth chart itself — no birth details were given, so this reading is "
    "cast for the moment the question was asked (prashna), not from a nativity",
    "Vimshottari dasha — it is counted from the birth Moon, which is not known",
    "tara bala and chandra bala — both compare the transiting Moon against the "
    "BIRTH Moon, and there is no birth Moon here",
    "the Jaimini chara karakas and the arudha padas — Darakaraka ranks the "
    "NATIVE'S grahas by degree and an arudha is counted from the BIRTH lagna, "
    "so computed from the moment of asking they describe this afternoon rather "
    "than the seeker. Do not name a spouse significator in this reading",
)
"""What a reading with no birth data cannot have, and must say so.

Every one of these failed silently before. The prompt asked for a Dasha step and
printed no periods; it printed a tara bala computed by comparing the moment
chart's Moon against itself, which is always Janma and always unfavourable, and a
reading built real advice on it.
"""


def profile_for(
    question: str, *, koonji_domain: str = "", has_birth_chart: bool = True
) -> QuestionProfile:
    """The fact set this question requires, and what it cannot have.

    `koonji_domain` is now load-bearing. It was accepted here for two commits and
    used only to build the `reason` string, so a marriage timing question and a
    career timing question received byte-identical facts - which is why a
    marriage reading leant on general dasha strength and never named the 7th
    lord's condition. `hierarchy_node` settles the domain from `koonji.router`'s
    table and it is taken rather than re-derived, on the same argument as before.
    """
    from rishivan.chart.panchang import relative_day_offset
    from rishivan.council.requirements.store import requirements_for
    from rishivan.council.requirements.types import Requirement, RequirementSet

    day_offset = relative_day_offset(question)
    kind = _kind(question, day_offset)
    requirements = requirements_for(koonji_domain, kind.value)
    unavailable: tuple[str, ...] = ()

    if not has_birth_chart:
        requirements = RequirementSet(
            domain=requirements.domain, kind=requirements.kind,
            constitution=requirements.constitution,
            requires=tuple(
                r for r in requirements.requires
                if r.key not in _NEEDS_A_NATIVITY
                and not r.key.startswith(_NEEDS_A_NATIVITY_PREFIXES)
            ),
            source=requirements.source, notes=requirements.notes,
        )
        unavailable = NO_BIRTH_CHART_UNAVAILABLE

    when = {0: "today", 1: "tomorrow", 2: "the day after tomorrow"}.get(
        day_offset, f"{day_offset} days from now"
    )
    reason = (
        f"{kind.value}: routed to {koonji_domain or 'no domain'}, about {when}. "
        f"{len(requirements.requires)} requirements from "
        f"{requirements.source.value}."
    )
    return QuestionProfile(
        kind=kind, day_offset=day_offset, requirements=requirements,
        unavailable=unavailable, reason=reason,
    )
