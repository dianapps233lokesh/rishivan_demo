"""The S5 extraction prompt — the invariant prefix every extraction call carries.

Three properties this module exists to guarantee:

**Derived, never restated.** The fact vocabulary is generated from
`rishivan.astro.vocab`, which warns in its own docstring that a second copy is a second
thing to drift, "and drift here means every affected rule silently matches nothing".
So `fact_vocabulary()` reads `CONDITION_TOKEN_TEMPLATES` and `EMITTED_SCOPES` rather
than listing tokens by hand. In particular it emits planet **names** (`saturn`), not
the two-letter codes the books use (`Sa`) -- `planet.Sa.house` looks perfectly
reasonable and matches nothing, ever.

**Byte-identical across calls.** Everything here is a pure function of frozen module
constants, with no timestamps, no per-verse interpolation and no dict ordering that
can shift. That is what makes the prefix cacheable, and caching is a 3.5x cost swing
on the pilot ($3.42 vs $11.98), so it is a correctness property rather than a
nicety.

**Above the cache floor.** Explicit context caching requires a minimum prefix, and a
prefix that drops below it silently stops being cached -- no error, just triple the
bill. `CACHE_FLOOR_TOKENS` records that floor and a test asserts the prefix clears
it. Measured on `gemini-3.5-flash-lite`: 19,112 tokens, of which 19,113 were served
from cache on a live call.

The prefix is deliberately *not* minimised. An earlier draft compressed the
vocabulary to a grammar and landed at 4,054 tokens -- 42 below the floor -- which
would have cost roughly twice as much as the larger cached version. Tokens spent
here are amortised across ~1,300 calls at the cached rate, so the right thing to
spend them on is extraction quality: the worked examples below earn their place.
"""

import json

from rishivan.astro.vocab import (
    CONDITION_TOKEN_TEMPLATES,
    EMITTED_SCOPES,
    OUT_OF_SCOPE_CONDITION_TYPES,
    PLANET_TOKEN_NAME,
    UNEMITTED_REFERENCE_SCOPES,
    UNEMITTED_VARGA_SCOPES,
)

CACHE_FLOOR_TOKENS = 4096
"""Minimum prefix size for explicit context caching to apply.

Verified empirically against `gemini-3.5-flash-lite`: a 19,112-token prefix cached
successfully and a subsequent call reported `cached_content_token_count=19113` out of
`prompt_token_count=19133`. Below this floor the cache is silently not used.
"""

SCHEMA_LEAF_BUDGET = 160
"""Maximum leaf field definitions a `response_schema` may contain.

Measured, because the API does not say: identical requests differing only in schema
size succeeded at 156 leaf fields and failed at 180 with a bare
`400 INVALID_ARGUMENT` that names nothing. A leave-one-out pass over the rule
properties found no single culprit -- the limit is cumulative.

This matters because `_ATOM` carries 12 fields and is duplicated once per condition
slot. An earlier draft had seven condition slots at three atom lists each: 21 copies,
252 leaf fields, and every extraction call failing with an error that pointed nowhere.
A test asserts the schema stays under this budget so the failure surfaces at test time
rather than as an opaque 400 mid-run.
"""

MODEL = "gemini-3.5-flash-lite"
"""Chosen on measured quality, not price. Graded 21/21 on the correctness invariants
(formation free of timing atoms, commentary routed to `exceptions` rather than
becoming the rule, polarity correct) -- matching `gemini-3.1-pro-preview` at a sixth
of the latency. The only variance was effect granularity, which is a prompt
specification issue rather than a model capability one."""


ARGUMENT_SEMANTICS: dict[str, str] = {
    "aspected_by": (
        "`planet` is the planet CASTING the aspect; `target` is what receives it "
        "(a house number 1-12, or a planet name). 'the 4th aspected by Jupiter' is "
        "planet=jupiter, target=4 -- NOT target=jupiter."
    ),
    "planet_in_house": (
        "Use this for ANY positional statement, including relative frames: 'the Moon "
        "in the 1st, 4th, 7th or 10th from the Sun' is planet=moon, "
        "houses=[1,4,7,10], scope='from_sun.' -- it is NOT an aspect."
    ),
    "conjunct": (
        "`planet` and `other` are BOTH planet names. A house is never a value here; "
        "for a planet in a house use planet_in_house."
    ),
    "house_is_empty": (
        "`house` is a specific number 1-12. If the verse states a principle about "
        "'a house' in general with no number, see rule 9."
    ),
    "lord_of_house_in_house": (
        "`lord_of` is WHOSE lord (the 8th lord -> lord_of=8); `house` is where that "
        "lord sits. Both are required -- omitting `house` says nothing."
    ),
    "dasha_of": "`level` is which period: maha, antar, pratyantar, sookshma, prana.",
}
"""Per-type argument semantics, because the field names alone were not enough.

Every entry here corresponds to a mistake observed in a real run: the model emitted
`aspected_by{target: jupiter}` with no `planet` (inverting the relationship),
`conjunct{planet: "house"}` (a house in a planet slot), and `house_is_empty{}` and
`lord_of_house_in_house{house: 4}` with the required subject missing. Naming a field
does not tell the model which side of a relationship it holds."""


def fact_vocabulary() -> str:
    """The token space, generated from the vocabulary lock."""
    planets = sorted(PLANET_TOKEN_NAME.values())
    lines = [
        "FACT TOKEN VOCABULARY (the only atoms you may propose).",
        "",
        "A token is <scope><base>. Emitted scopes:",
    ]
    for scope in EMITTED_SCOPES:
        label = "D1, counted from the Ascendant" if scope == "" else scope
        lines.append(f"  {scope or '(none)':14s} {label}")
    lines += [
        "",
        "Varga and reference scopes are NEVER combined: `d9.from_moon.` is not emitted.",
        "",
        f"Planet names (use these, NOT the two-letter codes the text uses): "
        f"{', '.join(planets)}",
        "",
        "CONDITION TYPES and the token each constrains:",
    ]
    for condition_type, templates in CONDITION_TOKEN_TEMPLATES.items():
        lines.append(f"  {condition_type:24s} -> {', '.join(templates)}")
    lines += [
        "",
        "REQUIRED ARGUMENTS PER CONDITION TYPE. Supply exactly these fields and no",
        "others. A field that does not belong to the type is invalid, and a missing",
        "field makes the atom unusable -- `lord_of_house_in_house` without `house`",
        "does not say where the lord sits, so it matches nothing.",
    ]
    for condition_type, arguments in sorted(CONDITION_ARGUMENTS.items()):
        names = [name for name in arguments if name != "scope"]
        lines.append(
            f"  {condition_type:24s} {', '.join(names)}"
            f"{'  (+ optional scope)' if 'scope' in arguments else ''}"
        )
        if condition_type in ARGUMENT_SEMANTICS:
            lines.append(f"      {ARGUMENT_SEMANTICS[condition_type]}")
    lines += [
        "",
        "NOT EXPRESSIBLE. If the verse needs any of these, set expressible=false and",
        "name the concept in out_of_scope_reason. Never substitute something close.",
        f"  condition types : {', '.join(sorted(OUT_OF_SCOPE_CONDITION_TYPES))}",
        f"  vargas          : {' '.join(UNEMITTED_VARGA_SCOPES)}",
        f"  reference frames: {' '.join(UNEMITTED_REFERENCE_SCOPES)}",
        "  also absent     : shadbala / bala.*, ashtakavarga bindus, KP sub-lords,",
        "                    chara karakas (atmakaraka..darakaraka), arudha, upapada,",
        "                    karakamsha, avastha, combustion state",
        "  also absent     : BENEFIC and MALEFIC as classes. There is no atom for",
        "                    'a benefic' or 'a malefic'. Naming Jupiter for 'a benefic'",
        "                    or Saturn for 'a malefic' is a substitution and is WRONG:",
        "                    the verse is true of every benefic, the atom is true of",
        "                    one planet. BUT: if the verse NAMES the planets, extract",
        "                    them. 'Mercury, Jupiter or Venus in a kendra' is three",
        "                    atoms under `any`, not a decline -- the text named them,",
        "                    so nothing is being inferred. Only an unnamed 'a benefic'",
        "                    is the gap. Also absent: the dignity or strength of a",
        "                    house LORD ('the strong 9th lord', 'the 11th lord",
        "                    exalted'), since dignity_is takes a planet, not lord_of.",
        "",
        "",
        "The emitted token space in the DEFAULT scope (prefix any scope above to",
        "reach a varga or alternative reference point):",
    ]
    for condition_type, templates in CONDITION_TOKEN_TEMPLATES.items():
        for template in templates:
            lines.append(f"  {template}")
    lines += [
        "",
        "Substitute a planet name for {planet}/{other}, 1-12 for {house}, and one of",
        "maha/antar/pratyantar/sookshma for {level}. Any token you can build this way",
        "is valid; anything you cannot is not expressible.",
    ]
    return "\n".join(lines)


INSTRUCTIONS = """You extract Koonji rules from classical Jyotish (Vedic astrology).
A Koonji rule is one if-then statement from the text, written so software can test it
against a real birth chart. Return zero or more rules for the supplied verse.

HARD RULES -- violating any of these makes the output unusable.

1. SOURCE OF AUTHORITY. A rule comes ONLY from the VERSE and its TRANSLATION. The
   COMMENTARY is a modern editor's opinion and must NEVER become the rule itself. A
   genuine cancellation or exception the commentary states MAY be recorded under
   `exceptions` or `modifiers.cancel`, with `from_commentary: true`.

2. TIMING CANNOT MANUFACTURE A PROMISE. `formation` carries the natal promise ONLY.
   Never place `dasha_of` or `transit_over` inside `formation`; they belong in
   `timing.activation_factors`. A verse whose only antecedent is a period (common in
   the dasha-result chapters) is legitimate: leave `formation` empty and set
   `rule_category: "timing"`.

3. NEVER INVENT A TOKEN. Propose atoms only over the enumerated vocabulary. If the
   verse needs a concept that is not there, set `expressible: false` and name the
   missing concept in `out_of_scope_reason`. Do NOT silently simplify a condition to
   make it fit -- a rule that matches the wrong charts is worse than no rule.

4. FAN OUT ENUMERATIONS. A verse stating one outcome per house or per sign is N
   rules, not one. Emit N siblings sharing a `rule_family` stem.

5. RESOLVE PRONOUNS FROM CONTEXT. Use the CHAPTER CONTEXT block to resolve "he",
   "that planet", "the said lord". If a referent cannot be resolved, set
   `expressible: false` rather than guessing a subject.

6. CONDITION SHAPE. Give a flat atom list: `atoms` combined by `combinator`, `none`
   for negated atoms ("unless Jupiter aspects it"), `any_groups` when a disjunction
   sits inside a conjunction. If the verse genuinely needs deeper logic, set
   `expressible: false` and put the clause verbatim in `raw_condition_text`.

7. SPLIT COMPOUND EFFECTS. One clause per distinct outcome. "bereft of bodily
   pleasures, detractor of gods, and afflicted with wounds" is three effects.

9. GENERIC SUBJECTS. Some verses state a principle about "a house", "the lord" or
   "a planet" with no specific number or name -- BPHS's chapters on judging houses do
   this throughout. Do NOT emit an atom with the subject left out: an atom missing its
   subject says nothing and matches nothing. Either fan the verse out into one sibling
   rule per case when the set is clearly all twelve houses, or set
   `expressible: false` with `out_of_scope_reason` naming it a generic principle. Both
   are acceptable; a subject-less atom is not.

10. NO EMBELLISHMENT. Do not summarise, moralise, soften, or add astrological
   reasoning of your own. Extract only what the text states. If the text asserts
   something harsh, record it with its polarity and let review decide.
"""

WORKED_EXAMPLES = """WORKED EXAMPLES (real verses, correct output).

--- Example 1: commentary holds the exception, not the rule ---
TRANSLATION: "If the 8th Lord happens to be placed in the Ascendant the native will
be bereft of bodily pleasures, be detractor of gods and Brahmins and will have
wounds."
COMMENTARY: "...In the Libra and Aries Ascendants the native does not get the effects
described in the sloka, because Venus and Mars respectively become the 8th Lord and
their moolatrikona sign is in the Ascendant..."
CORRECT:
  formation      : atoms=[{type: lord_of_house_in_house, lord_of: 8, house: 1}]
  effects        : 3 separate negative effects (pleasures, detraction, wounds)
  exceptions     : Aries and Libra ascendants, from_commentary: true
  rule_category  : formation
WHY: three outcomes means three effects. The commentary's cancellation is recorded as
an exception, and is NOT allowed to become the rule or to soften the effects.

--- Example 2: arithmetic is not a rule ---
TRANSLATION: "One half of the summation of Uchcha Rashmi and Cheshta Rashmi is called
Shubha Rashmi and if this is deducted from 8, the remainder is called Ashubha Rashmi."
CORRECT: no rules. expressible: false, out_of_scope_reason: "shadbala computation
(Uchcha/Cheshta Rashmi); defines a quantity rather than predicting an outcome".
WHY: the verse contains "if" and predicts nothing. Extracted as a rule it would sit
in the matcher never matching any chart.

--- Example 3: a period as the antecedent ---
TRANSLATION: "In the antardasa of Saturn in the mahadasa of Jupiter, the native will
suffer loss of wealth and mental agony."
CORRECT:
  formation                : empty
  timing.activation_factors: atoms=[{type: dasha_of, planet: saturn, level: antar},
                                    {type: dasha_of, planet: jupiter, level: maha}]
  effects                  : 2 negative effects
  rule_category            : timing
WHY: there is no natal placement, so there is no promise. Putting the dasha into
`formation` would let timing manufacture one.

--- Example 4: a rule with a remedy attached ---
TRANSLATION: "if Venus is the lord of the 2nd or the 7th house, danger of death is
there and to alleviate the evil effects, recitation of hymns in praise of Lord Shiva,
charity of white cow and silver be resorted to."
CORRECT:
  formation : combinator=any, atoms=[{type: lord_of_house_in_house, lord_of: 2, house: 1},
                                     {type: lord_of_house_in_house, lord_of: 7, house: 1}]
  effects   : one negative effect
  remedies  : the hymns to Shiva, the charity of white cow and silver
WHY: the remedy is part of the same statement. Filing this as a remedy alone would
throw away the prediction.

--- Example 5: disjunction over houses -- use a SET, never `all` ---
TRANSLATION: "Should the lord of the 7th be in the 6th, 8th or 12th house, the
native's wife will be sickly."
CORRECT: atoms=[{type: lord_of_house_in_house, lord_of: 7, houses: [6, 8, 12]}]
WRONG  : three separate atoms under combinator=all. The 7th lord occupies ONE house,
so that condition can never be true of any chart.
Same for named groups: kendra = houses [1,4,7,10], trikona = [1,5,9],
dusthana = [6,8,12], panaphara = [2,5,8,11].

--- Example 6: the dignity of a house lord ---
TRANSLATION: "If the lord of the 10th is exalted or in his own sign, the native
enjoys fame."
CORRECT: expressible=false, out_of_scope_reason: "dignity of a house lord --
`dignity_is` takes a planet, not `lord_of`".
WHY: do NOT put `dignity` on `lord_of_house_in_sign`; that field does not exist there
and the atom will be rejected. Say it is not expressible instead. This gap is known
and recorded.

--- Example 7: "a benefic" is not Jupiter ---
TRANSLATION: "A benefic in the 2nd House is the giver of wealth while a malefic in it
is the destroyer of wealth."
CORRECT: two rules, both expressible=false, out_of_scope_reason: "benefic/malefic as a
class -- no atom expresses planetary benevolence".
WRONG  : {type: planet_in_house, planet: jupiter, house: 2} for the first and
{planet: saturn, house: 2} for the second. The verse says nothing about Jupiter or
Saturn. Those two atoms match a handful of charts and miss every other benefic.
NOTE: a verse stating SEPARATE things splits into separate rules. "When the lord of the
2nd is in a kendra he promotes wealth; a benefic in the 2nd gives wealth" is ONE
expressible rule (the lord) plus ONE declined rule (the benefic) -- two independent
statements, so the inexpressible one must not sink the one that works.
This does NOT apply to a single condition ANDed together. "The 4th lord in the 4th AND
the Ascendant lord there AND aspected by a benefic" is ONE condition, and dropping the
benefic clause makes the rule match charts the verse excludes. Decline the whole rule.
Splitting is for separate statements; never for dropping a conjunct.

--- Example 8: one atom carries ALL of its fields ---
TRANSLATION: "In case the 5th Lord being in the 6th House, and the Ascendant Lord in
conjunction with Mars, the native's first born child will die."
CORRECT: atoms=[{type: lord_of_house_in_house, lord_of: 5, house: 6}]
         combinator=all, and the Ascendant-lord clause declined or omitted.
WRONG  : atoms=[{type: lord_of_house_in_house, lord_of: 5},
                {type: lord_of_house_in_house, house: 6}]
Two half-atoms are not one whole atom. The first says "the 5th lord is somewhere", the
second says "some lord is in the 6th" -- neither is the verse, and together under
`all` they mean something the text never said. Every field the type requires goes on
ONE atom. Same for sets: {lord_of: 11, houses: [1,4,7,10,5,9]}, never {lord_of: 11}
alongside {houses: [1,4,7,10,5,9]}.

--- Example 9: sign CLASSES may be expanded, because they are fixed ---
TRANSLATION: "If at the time of birth the Sun be in a movable sign the lamp will be
flickering, if he be in a fixed sign it will remain fixed, and if in a dual sign it is
sometimes stable and sometimes flickering."
CORRECT: three sibling rules --
  {type: planet_in_sign, planet: sun, signs: [aries, cancer, libra, capricorn]}
  {type: planet_in_sign, planet: sun, signs: [taurus, leo, scorpio, aquarius]}
  {type: planet_in_sign, planet: sun, signs: [gemini, virgo, sagittarius, pisces]}
WHY: movable/chara, fixed/sthira and dual/dvisvabhava are FIXED sets of signs that do
not depend on any other placement, so expanding them adds no assumption. Contrast
"exalted", which is a DIFFERENT sign for each planet and must never be expanded to a
sign list. Expand a class only when the class alone determines the signs.
"""

_PLANET = {"type": "string", "description": "planet NAME, e.g. saturn (never 'Sa')"}
_SCOPE = {
    "type": "string",
    "description": "scope prefix from the vocabulary, e.g. '' or 'd9.' or 'from_moon.'",
}

HOUSE_SET_ALIAS = {"house": "houses", "sign": "signs"}
"""A single atom may name a SET instead of one value.

This exists because the corpus demanded it and the first design refused. "The 7th lord
in the 6th, 8th or 12th", "the 8th lord in a kendra", "the 10th lord exalted or in own
sign" -- disjunction over one field is pervasive in classical Jyotish, not an edge
case. With no way to express it, the model either flattened it into `all` (producing
`mars in house 1 AND 4 AND 7`, which matches no chart that has ever existed) or gave up
with `expressible: false`. Eight of eighteen rules in the first review sample failed
for exactly this.

A set on one field is one extra schema field, unlike the nested `any_groups` construct
that was cut for exceeding the 160-leaf-field budget."""

CONDITION_ARGUMENTS: dict[str, dict] = {
    "planet_in_house": {"planet": _PLANET, "house": {"type": "integer"}, "scope": _SCOPE},
    "planet_in_sign": {"planet": _PLANET, "sign": {"type": "string"}, "scope": _SCOPE},
    "planet_in_nakshatra": {
        "planet": _PLANET,
        "nakshatra": {"type": "string"},
        "pada": {"type": "integer"},
        "scope": _SCOPE,
    },
    "lord_of_house_in_house": {
        "lord_of": {"type": "integer", "description": "which house's lord, 1-12"},
        "house": {"type": "integer"},
        "scope": _SCOPE,
    },
    "lord_of_house_in_sign": {
        "lord_of": {"type": "integer"},
        "sign": {"type": "string"},
        "scope": _SCOPE,
    },
    "conjunct": {"planet": _PLANET, "other": _PLANET, "scope": _SCOPE},
    "aspected_by": {
        "planet": _PLANET,
        "target": {"type": "string", "description": "target house number or planet"},
        "scope": _SCOPE,
    },
    "dignity_is": {
        "planet": _PLANET,
        "dignity": {
            "type": "string",
            "enum": [
                "exalted", "debilitated", "moolatrikona",
                "own_sign", "friendly", "neutral", "enemy",
            ],
        },
        "scope": _SCOPE,
    },
    "house_is_empty": {"house": {"type": "integer"}, "scope": _SCOPE},
    "dasha_of": {
        "planet": _PLANET,
        "level": {
            "type": "string",
            "enum": ["maha", "antar", "pratyantar", "sookshma", "prana"],
        },
    },
    "transit_over": {
        "planet": _PLANET,
        "house": {"type": "integer"},
        "sign": {"type": "string"},
    },
}
"""Argument shape per condition type.

Declared rather than derived: `CONDITION_TOKEN_TEMPLATES` gives the *token* each type
constrains, not its argument names, so there is nothing to derive them from. The risk
of a declaration is drift, so a test asserts these keys and the vocabulary lock's keys
are identical -- a condition type added upstream without a schema here would otherwise
produce atoms the model cannot fill.

An earlier version declared each type as a bare `{"type": "object"}`. Structured
output then had nothing to populate and returned `{"lord_of_house_in_house": {}}` --
schema-valid, entirely empty, and it would have compiled to a rule matching every
chart or none. Leaf conditions must carry their properties.
"""


_ATOM: dict = {
    "type": "object",
    "description": "One condition atom. `type` selects which fields apply.",
    "properties": {
        "type": {"type": "string", "enum": sorted(CONDITION_ARGUMENTS)},
        "planet": _PLANET,
        "other": _PLANET,
        "target": {"type": "string", "description": "target house number or planet"},
        "house": {"type": "integer"},
        "houses": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "ANY of these houses -- use for kendra/trikona/6-8-12",
        },
        "lord_of": {"type": "integer", "description": "which house's lord, 1-12"},
        "sign": {"type": "string"},
        "signs": {"type": "array", "items": {"type": "string"}},
        "nakshatra": {"type": "string"},
        "pada": {"type": "integer"},
        "dignity": {
            "type": "string",
            "enum": [
                "exalted", "debilitated", "moolatrikona",
                "own_sign", "friendly", "neutral", "enemy",
            ],
        },
        "level": {
            "type": "string",
            "enum": ["maha", "antar", "pratyantar", "sookshma", "prana"],
        },
        "scope": _SCOPE,
    },
    "required": ["type"],
}
"""A flat, discriminated atom rather than a nested condition tree.

The tree form is what the rule DSL stores, but it cannot be expressed as a Gemini
`response_schema`: there is no `$ref`, so recursion has to be written out in full, and
three levels over eleven condition types expanded to 294,114 characters and 5,232
nodes -- which the API rejects outright with `400 INVALID_ARGUMENT`.

A flat atom list in conjunctive normal form is the trade: `atoms` are ANDed or ORed by
`combinator`, `none` holds negations ("unless aspected by Jupiter"), and `any_groups`
covers a disjunction inside a conjunction. That spans the overwhelming majority of
classical constructions. Anything genuinely deeper degrades to `expressible: false`
with the text preserved in `raw_condition_text`, which is reportable -- rather than
being silently flattened into a condition that matches the wrong charts.

It also maps one-to-one onto the denormalised `rule_atom` table the matcher prefilters
on, so S6 has less translating to do, not more.
"""

_CONDITION: dict = {
    "type": "object",
    "properties": {
        "combinator": {
            "type": "string",
            "enum": ["all", "any"],
            "description": "how `atoms` combine; default all",
        },
        "atoms": {"type": "array", "items": _ATOM},
        "none": {
            "type": "array",
            "items": _ATOM,
            "description": "atoms that must NOT hold -- the 'unless' clause",
        },
    },
}

_EFFECT: dict = {
    "type": "object",
    "properties": {
        "polarity": {
            "type": "string",
            "enum": ["positive", "negative", "mixed", "neutral"],
        },
        "strength": {"type": "string", "enum": ["weak", "moderate", "strong"]},
        "statement": {
            "type": "string",
            "description": (
                "ONE outcome only. Split compound results: 'bereft of pleasures, "
                "detractor of gods, and wounds' is THREE effects, not one."
            ),
        },
        "life_domain": {"type": "string"},
    },
    "required": ["polarity", "strength", "statement"],
}

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule_key": {"type": "string"},
                    "rule_family": {"type": "string"},
                    "unit_ref": {
                        "type": "string",
                        "description": "chapter.verse this rule came from",
                    },
                    "formation": _CONDITION,
                    "modifiers": {
                        "type": "array",
                        "description": (
                            "Conditions that alter this rule rather than establish "
                            "it. `cancel` is how Neecha Bhanga is expressed."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["strengthen", "weaken", "cancel"],
                                },
                                "condition": _CONDITION,
                                "from_commentary": {"type": "boolean"},
                            },
                            "required": ["kind", "condition"],
                        },
                    },
                    "exceptions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "condition": _CONDITION,
                                "effect_override": _EFFECT,
                                "from_commentary": {"type": "boolean"},
                                "statement": {"type": "string"},
                            },
                        },
                    },
                    "timing": {
                        "type": "object",
                        "properties": {"activation_factors": _CONDITION},
                    },
                    "effects": {
                        "type": "array",
                        "items": _EFFECT,
                        "description": (
                            "One entry per distinct outcome the verse states. A verse "
                            "listing three results yields three effects."
                        ),
                    },
                    "remedies": {"type": "array", "items": {"type": "string"}},
                    "rule_category": {
                        "type": "string",
                        "enum": [
                            "formation",
                            "strength",
                            "relationship",
                            "exception",
                            "timing",
                            "domain",
                        ],
                    },
                    "life_domains": {"type": "array", "items": {"type": "string"}},
                    "rishi_affinity": {
                        "type": "object",
                        "properties": {
                            rishi: {"type": "number"}
                            for rishi in (
                                "atma", "prema", "artha", "karma",
                                "vansh", "aarogya", "yatra", "dharma",
                            )
                        },
                    },
                    "raw_condition_text": {"type": "string"},
                    "expressible": {"type": "boolean"},
                    "out_of_scope_reason": {"type": "string"},
                },
                "required": [
                    "rule_key",
                    "unit_ref",
                    "formation",
                    "effects",
                    "rule_category",
                    "life_domains",
                    "expressible",
                ],
            },
        }
    },
    "required": ["rules"],
}


def invariant_prefix() -> str:
    """The byte-identical block cached once per book and reused every call.

    Deliberately excludes the JSON schema. The schema is passed as `response_schema` in
    per-call config, which the API enforces -- restating it here as prose bought
    nothing and was billed twice: once at the cached rate inside this prefix, and again
    at the full rate per call, because config is not content and cannot be cached. That
    duplication was 4,089 tokens per call, more than the entire rest of the variable
    payload.
    """
    return "\n\n".join((INSTRUCTIONS, fact_vocabulary(), WORKED_EXAMPLES))


TOOL_NAME = "emit_rules"
"""The single function the model is forced to call.

Passing the output contract as a cached **tool declaration** rather than as
`response_schema` in per-call config is the difference between 6,063 and 324 billed
input tokens per call. `response_schema` is config, and config cannot be cached, so the
4,569-token schema was billed at full rate on every one of ~1,300 calls. A tool
declaration lives inside the cached content and is billed once, at the cached rate.

Measured on five real units: billed input fell 18.7x and validity *rose* -- 9 of 9
rules valid, against 5 of 5 with the per-call schema and 3 of 7 with no schema at all.
Cheaper and better, which is rare enough to be worth the note.

Two API constraints, both learned by hitting them:
  * `tools`, `tool_config` and `system_instruction` must be set on the CACHE and must
    NOT be repeated in the request -- doing both returns
    `400 ... should not be set in the request when using cached content`.
  * The response arrives as a `function_call`, so read `part.function_call.args`, not
    `response.text`.
"""


def emit_rules_tool():
    """The output contract, as a tool declaration that can live in the cache."""
    from google.genai import types

    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=TOOL_NAME,
                description="Emit the Koonji rules extracted from the supplied verse.",
                parameters=RESPONSE_SCHEMA,
            )
        ]
    )


def cached_contents() -> str:
    """The non-instruction half of the cache: vocabulary plus worked examples."""
    return fact_vocabulary() + "\n\n" + WORKED_EXAMPLES


def verse_block(
    *,
    chapter: str,
    verse_ref: str,
    verse_devanagari: str,
    translation: str,
    commentary: str = "",
    chapter_context: str = "",
) -> str:
    """The per-verse suffix. Kept strictly separate from the prefix so the prefix
    stays byte-identical and therefore cacheable."""
    parts = [f"UNIT_REF: {chapter}.{verse_ref}"]
    if chapter_context:
        parts.append(f"CHAPTER CONTEXT:\n{chapter_context}")
    parts += [
        f"VERSE (Devanagari):\n{verse_devanagari}",
        f"TRANSLATION:\n{translation}",
        f"COMMENTARY (never the rule itself):\n{commentary or '(none)'}",
    ]
    return "\n\n".join(parts)
