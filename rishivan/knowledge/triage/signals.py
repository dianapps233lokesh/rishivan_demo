"""Deterministic signals that decide where a verse goes — no LLM, no cost.

Grounded in measurement rather than intuition. Across the 23-book corpus 44.3% of
English prose carries an explicit conditional marker; within BPHS it is 63.5%, and
~15% is definitional, computational or enumerative. So a keyword pass is not a
rough first draft here — it settles the majority of units correctly and for free,
which is the whole point of triaging before spending on extraction.

Two ordering decisions matter and are deliberate:

* **Arithmetic outranks conditionals.** BPHS 20.5 reads "...and *if* this is
  deducted from 8, the remainder is called Ashubha Rashmi". It carries an `if` and
  is not a rule — it is a formula. Checking arithmetic first stops formulae being
  mined for predictions they never made.
* **Conditionals outrank remedies.** BPHS 54.63-64 states a condition, its
  consequence, *and* a remedy in one breath. That verse owes a rule with the remedy
  attached, so it must route to extraction rather than being filed as a remedy and
  losing the prediction.
"""

import re
from enum import StrEnum

_W = r"(?:^|[^a-z])"  # word-ish boundary that tolerates OCR punctuation
_E = r"(?:[^a-z]|$)"


def _any(*alternatives: str) -> re.Pattern[str]:
    return re.compile(_W + "(?:" + "|".join(alternatives) + ")" + _E, re.I)


CONDITIONAL = _any(
    "if", "should", "when", "whenever", "in case", "provided", "were",
    "in the event", "supposing", "given that",
)
"""Explicit conditional markers."""

CONDITIONAL_IMPLICIT = _any(
    "born (?:in|with|under|during)", "natives? of", "one who has",
    "those (?:born|having)", "posited in", "placed in", "occupying",
    "situated in", "stationed in", "aspected by", "conjunct",
)
"""Classical translations often state a condition with no `if` at all — "Planets
situated in the visible half give explicit results" (BPHS 24.8) is a complete rule.
Requiring the word `if` would discard these."""

EFFECT = _any(
    "the native", "he (?:will|becomes|gets|is)", "she (?:will|becomes)",
    "one (?:will|becomes|gets)", "gives?", "causes?", "confers?", "bestows?",
    "indicates?", "denotes?", "results? in", "brings?", "produces?", "yields?",
    "destroys?", "afflicts?", "there (?:will be|is danger)",
    # Outcome stated as a noun phrase rather than a verb -- "danger of death is
    # there" (BPHS 54.63) is a consequent, and the earlier verb-only pattern missed
    # it, sending a perfectly good rule to the paid ambiguous lane.
    "(?:danger|risk|fear|loss|gain|destruction|death) of",
    "(?:evil|good|auspicious|inauspicious|benefic|malefic) (?:effects?|results?)",
    "suffers?", "enjoys?", "obtains?", "acquires?", "attains?", "possess(?:es)?",
    "will be", "shall be", "becomes?", "endowed with", "devoid of", "bereft of",
    "blessed with", "deprived of",
)
"""A consequent. A condition with no consequent is usually a definition."""

ARITHMETIC = _any(
    "multipl(?:y|ied)", "divid(?:e|ed) by", "deduct(?:ed)?", "subtract(?:ed)?",
    "remainder", "product of", "added to", "sum of", "one half of", "quotient",
    "square of", "cube of",
)
"""Computation, not prediction — destination B, `kind=formula`."""

DEFINITION = _any(
    "is called", "are called", "is known as", "are known as", "is termed",
    "are termed", "is named", "are named", "is designated", "is styled",
    "goes by the name", "is said to be",
)

CLASSIFICATION = _any(
    "the (?:natures?|kinds?|types?|classes?|categories) of",
    "(?:is|are) (?:classified|grouped|divided) (?:as|into)",
    "belongs? to the", "(?:benefics?|malefics?) are",
)

ENUMERATION = _any(
    "respectively", "as follows", "in (?:the same )?order", "following are",
    "these are the", "in succession", "seriatim",
)

REMEDY = _any(
    "worship", "propitiat(?:e|ion)", "oblation", "charity", "donate", "donation",
    "remedial", "remedy", "hymns?", "japa", "mantra", "recitation",
    "should be (?:given|offered|performed)", "pacif(?:y|ication)",
)

INVOCATION = _any(
    "maitreya", "o brahmin", "o sage", "parasara (?:said|replied|spoke)",
    "salutations?", "obeisance", "i (?:bow|salute)", "may (?:the|lord)",
    "thus (?:ends|said)", "having (?:heard|been asked)",
)

NARRATIVE = _any(
    "in ancient times", "there lived", "the story", "once upon",
    "it is (?:said|related) that", "legend",
)

TIMING = _any(
    "dasha", "dasa", "antara", "bhukti", "period of", "during the (?:period|dasha)",
    "transit", "gochara", "at the age of", "years? of age",
)

TIMING_CONDITION = _any(
    "(?:maha|antar|pratyantar|sookshmantar|sookshma|prana)[- ]?dasa?a?",
    "in the (?:dasa|dasha|antardasa|bhukti|period) of",
    "during the (?:dasa|dasha|antardasa|bhukti|sub-?period|period) of",
    "transits? (?:through|over|the)",
)
"""A dasha or transit *acting as the antecedent*, not merely mentioned.

BPHS vol 2 devotes whole chapters (54, 61, 63, 64, 66) to dasha results -- "in the
antardasa of Saturn in the mahadasa of Jupiter, the native suffers losses". The
condition there **is** the period, so requiring a natal placement filed 150+ genuine
rules as ambiguous and would have sent them to a paid classifier for no reason.

These route to extraction like any rule. What makes them safe is downstream, not
here: S6 finds no natal atom for `formation`, so the rule compiles as `timing_only`
and structurally cannot assert a promise -- which is exactly the client's rule that
timing cannot manufacture one."""

ASTRO_ENTITY = re.compile(
    r"(sun|moon|mars|mercury|jupiter|venus|saturn|rahu|ketu|lagna|ascendant"
    r"|planets?|zodiac|houses?|signs?|lords?|benefics?|malefics?|luminar"
    r"|\d{1,2}(?:st|nd|rd|th)\s+(?:house|lord|bhava)"
    r"|aries|taurus|gemini|cancer|leo|virgo"
    r"|libra|scorpio|sagittarius|capricorn|aquarius|pisces|nakshatra|navamsa"
    r"|rashi|bhava|varga|karaka|yoga|drekkana|amsa|graha|exalt|debilitat"
    r"|retrograde|combust|moolatrikona|aspect)",
    re.I,
)
"""A statement with no astrological entity in it is almost never a rule."""


class Signal(StrEnum):
    conditional = "conditional"
    conditional_implicit = "conditional_implicit"
    effect = "effect"
    arithmetic = "arithmetic"
    definition = "definition"
    classification = "classification"
    enumeration = "enumeration"
    remedy = "remedy"
    invocation = "invocation"
    narrative = "narrative"
    timing = "timing"
    timing_condition = "timing_condition"
    astro_entity = "astro_entity"


_PATTERNS: dict[Signal, re.Pattern[str]] = {
    Signal.conditional: CONDITIONAL,
    Signal.conditional_implicit: CONDITIONAL_IMPLICIT,
    Signal.effect: EFFECT,
    Signal.arithmetic: ARITHMETIC,
    Signal.definition: DEFINITION,
    Signal.classification: CLASSIFICATION,
    Signal.enumeration: ENUMERATION,
    Signal.remedy: REMEDY,
    Signal.invocation: INVOCATION,
    Signal.narrative: NARRATIVE,
    Signal.timing: TIMING,
    Signal.timing_condition: TIMING_CONDITION,
    Signal.astro_entity: ASTRO_ENTITY,
}


def detect(text: str) -> frozenset[Signal]:
    """Every signal present in `text`. Cheap, pure, and order-independent."""
    if not text:
        return frozenset()
    return frozenset(sig for sig, pat in _PATTERNS.items() if pat.search(text))
