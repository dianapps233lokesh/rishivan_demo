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


class QuestionKind(str, Enum):
    WHEN_WILL = "when_will"
    OK_ON_DATE = "ok_on_date"
    WHAT_IS_IT_LIKE = "what_is_it_like"
    WHICH_OPTION = "which_option"


class Bundle(str, Enum):
    """The closed menu. Nothing may be requested that is not here."""

    NATAL_PLACEMENTS = "natal_placements"
    HOUSE_LORDS = "house_lords"
    CONJUNCTIONS = "conjunctions"
    YOGAS = "yogas"
    PLANET_CONDITION = "planet_condition"
    DASHA_CURRENT = "dasha_current"
    DASHA_FORWARD = "dasha_forward"
    TRANSITS_SLOW = "transits_slow"
    SADE_SATI = "sade_sati"
    PANCHANG_FOR_DATE = "panchang_for_date"
    TARA_BALA = "tara_bala"
    CHANDRA_BALA = "chandra_bala"
    VARGAS = "vargas"
    ASHTAKAVARGA = "ashtakavarga"
    NUMEROLOGY = "numerology"


FLOOR: frozenset[Bundle] = frozenset({
    Bundle.NATAL_PLACEMENTS,
    Bundle.HOUSE_LORDS,
    Bundle.PLANET_CONDITION,
    Bundle.DASHA_CURRENT,
})
"""Present for every question, and not negotiable.

The placements say what the chart is, the lords say who governs what, the
condition says how strong any of it is, and the running period says what is live.
A reading missing any of the four is wrong in a way that reads as fluent.
"""

_PER_KIND: dict[QuestionKind, frozenset[Bundle]] = {
    QuestionKind.WHEN_WILL: frozenset({
        Bundle.DASHA_FORWARD, Bundle.TRANSITS_SLOW, Bundle.SADE_SATI,
        Bundle.YOGAS, Bundle.VARGAS,
    }),
    # No DASHA_FORWARD. A ten-year forecast is not an answer about tomorrow, and
    # sending one is how a question about tomorrow got answered with 2027.
    QuestionKind.OK_ON_DATE: frozenset({
        Bundle.PANCHANG_FOR_DATE, Bundle.TARA_BALA, Bundle.CHANDRA_BALA,
        Bundle.TRANSITS_SLOW,
    }),
    # No transits, no forward periods. A temperament reading timed against a
    # transit becomes a forecast nobody asked for.
    QuestionKind.WHAT_IS_IT_LIKE: frozenset({
        Bundle.YOGAS, Bundle.CONJUNCTIONS, Bundle.VARGAS,
    }),
    QuestionKind.WHICH_OPTION: frozenset({
        Bundle.PANCHANG_FOR_DATE, Bundle.TRANSITS_SLOW, Bundle.VARGAS,
    }),
}

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


_ALWAYS_UNAVAILABLE = (
    "Jaimini karakas and Upapada — the fact vocabulary does not express them",
)
"""What no question can have, whatever it asks.

Declared rather than left silent: `graph/README.md` records that the corpus holds
no yoga-typed claims and `constitution.blocked_concepts` lists Atmakaraka and
Karakamsha. A reading asked for a Jaimini step will otherwise pad it, which is
what happened - "interlocking dispositor dynamics validate institutional
elevation" is filler in the shape of an answer.
"""


@dataclass(frozen=True, slots=True)
class QuestionProfile:
    kind: QuestionKind
    day_offset: int
    bundles: frozenset[Bundle]
    unavailable: tuple[str, ...] = field(default=())
    reason: str = ""

    def wants(self, bundle: Bundle) -> bool:
        return bundle in self.bundles


NO_BIRTH_CHART_UNAVAILABLE = (
    "the birth chart itself — no birth details were given, so this reading is "
    "cast for the moment the question was asked (prashna), not from a nativity",
    "Vimshottari dasha — it is counted from the birth Moon, which is not known",
    "tara bala and chandra bala — both compare the transiting Moon against the "
    "BIRTH Moon, and there is no birth Moon here",
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

    `koonji_domain` is taken rather than re-derived: `hierarchy_node` already
    settled it from `koonji.router`'s table, and two modules deciding the domain
    separately is how `varga_select` and `dasha_windows` spent a phase reading a
    key nothing wrote.
    """
    from rishivan.chart.panchang import relative_day_offset

    day_offset = relative_day_offset(question)
    kind = _kind(question, day_offset)
    bundles = FLOOR | _PER_KIND[kind]
    unavailable = _ALWAYS_UNAVAILABLE

    if not has_birth_chart:
        # Everything that compares a birth placement against a moving one
        # degenerates without a nativity. Tara bala came back Janma every single
        # time - the Moon measured against itself - and the dasha bundles asked
        # for periods nobody could compute.
        bundles -= {
            Bundle.DASHA_CURRENT, Bundle.DASHA_FORWARD,
            Bundle.TARA_BALA, Bundle.CHANDRA_BALA, Bundle.SADE_SATI,
        }
        unavailable = unavailable + NO_BIRTH_CHART_UNAVAILABLE

    when = {0: "today", 1: "tomorrow", 2: "the day after tomorrow"}.get(
        day_offset, f"{day_offset} days from now"
    )
    reason = (
        f"{kind.value}: routed to {koonji_domain or 'no domain'}, about {when}. "
        f"{len(bundles)} of {len(Bundle)} fact bundles."
    )
    return QuestionProfile(
        kind=kind, day_offset=day_offset, bundles=bundles,
        unavailable=unavailable, reason=reason,
    )
