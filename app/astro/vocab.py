"""The facts token vocabulary. Freeze before any rule extraction begins.

This module is one half of the tightest coupling in the system (spec §6.2): the
engine's `facts` token vocabulary *is* the rule DSL's condition vocabulary. If a
rule compiles to a token this module does not describe, the rule never matches
any chart and no error is raised — the platform quietly degrades to plain
passage retrieval. So the vocabulary is declared here, in one near-leaf module
(it reads the planet-code table from `constants` rather than restating it), and
pinned from both sides by tests.

A token is `<scope><base>`, where scope is empty for the default frame:

    planet.saturn.house                  Saturn's house, D1, counted from Lagna
    d9.planet.saturn.house               ... in Navamsa
    from_moon.planet.saturn.house        ... counted from the Moon
    house.7.lord.house                   where the 7th lord sits

**Recognised is not the same as emitted.** `UNEMITTED_*` scopes are part of the
grammar so that P2's rule compiler can recognise an atom and mark it
`out_of_scope` — an honest, reportable status — instead of compiling it into an
atom that silently matches nothing. Widening an `EMITTED_*` tuple is an additive
change: a minor `ENGINE_VERSION` bump, no schema migration.
"""

from app.astro.constants import PLANET_CODES

BASE_PREFIXES = (
    "lagna.",
    "planet.",
    "house.",
    "dasha.",
    "nakshatra.",
    "numerology.",
    "transit.",
)

FACT_PREFIXES = BASE_PREFIXES
"""Kept as the historical name; scoped keys must go through is_valid_fact_key."""

JYOTISH_PREFIXES = tuple(p for p in BASE_PREFIXES if not p.startswith("numerology"))

EMITTED_VARGA_SCOPES = ("d2.", "d7.", "d9.", "d10.", "d12.", "d30.")
"""The vargas §8.3's fact scoping actually pulls: wealth D2, children D7,
marriage D9, career D10, parents D12, health D30. D1 is the default scope and is
never prefixed."""

UNEMITTED_VARGA_SCOPES = (
    "d3.",
    "d4.",
    "d16.",
    "d20.",
    "d24.",
    "d27.",
    "d40.",
    "d45.",
    "d60.",
)
"""Computed on every chart and available in `sheet.vargas`, but not flattened
into tokens: the full shodashavarga cross-product would roughly triple the size
of a JSONB column that sits on every chart row and carries a GIN index."""

EMITTED_REFERENCE_SCOPES = ("from_moon.", "from_sun.")
"""Chandra lagna and Surya lagna — by far the most cited alternative reference
points in the classics."""

UNEMITTED_REFERENCE_SCOPES = ("from_arudha_lagna.",) + tuple(
    f"from_house{n}." for n in range(1, 13)
)
"""Arudha Lagna needs a computation the engine does not yet have; `from_house_n`
is rare enough that twelve more frames is a poor trade."""

ALL_VARGA_SCOPES = EMITTED_VARGA_SCOPES + UNEMITTED_VARGA_SCOPES
ALL_REFERENCE_SCOPES = EMITTED_REFERENCE_SCOPES + UNEMITTED_REFERENCE_SCOPES

EMITTED_SCOPES = ("",) + EMITTED_VARGA_SCOPES + EMITTED_REFERENCE_SCOPES
"""Varga and reference scopes are emitted independently, never combined: a
`d9.from_moon.` frame is recognised by the grammar but not emitted."""


CONDITION_TOKEN_TEMPLATES: dict[str, tuple[str, ...]] = {
    "planet_in_house": ("planet.{planet}.house",),
    "planet_in_sign": ("planet.{planet}.sign",),
    "planet_in_nakshatra": ("planet.{planet}.nakshatra", "planet.{planet}.pada"),
    "lord_of_house_in_house": ("house.{house}.lord.house",),
    "lord_of_house_in_sign": ("house.{house}.lord.sign",),
    "conjunct": ("planet.{planet}.conjunct.{other}",),
    "aspected_by": ("planet.{planet}.aspects.{target}",),
    "dignity_is": ("planet.{planet}.dignity",),
    "house_is_empty": ("house.{house}.occupant_count",),
    "dasha_of": ("dasha.{level}.lord",),
    "transit_over": ("transit.{planet}.house", "transit.{planet}.sign"),
}
"""**The vocabulary lock** — the rule DSL's condition types, mapped to the token
each one constrains. P2's rule compiler must derive `atom_to_fact_token` from
this table rather than restate it; a second copy is a second thing to drift, and
drift here means every affected rule silently matches nothing.

A template is filled with a scope prefix (see `split_scope`) plus the atom's own
values, so `planet_in_house` for Saturn in Navamsa becomes
`d9.planet.saturn.house`.
"""

SUPPORTED_CONDITION_TYPES = frozenset(CONDITION_TOKEN_TEMPLATES)

OUT_OF_SCOPE_CONDITION_TYPES = frozenset({"strength_cmp"})
"""Cut from DSL v1 deliberately.

`strength_cmp` needs Shadbala, which the engine does not compute and which open
decision O2 has not settled — cross-tool agreement on Shadbala is genuinely
unachievable because Cheshta and Kaala bala conventions diverge between
implementations. A condition the matcher cannot evaluate is worse than no
condition: it is a silent false promise. So rules needing it park at
`status='out_of_scope'` and stay passage-only, which is reportable.
"""

PLANET_TOKEN_NAME = {code: name for name, code in PLANET_CODES.items()}
"""Classical two-letter codes (how the books write them) to token names (how the
engine emits them). The mismatch between these two spellings is the single most
likely cause of a total, silent matching failure -- `planet.Sa.house` looks
perfectly reasonable and matches nothing, ever.

Derived from `constants.PLANET_CODES` rather than restated, so the two spellings
cannot drift apart."""


def split_scope(key: str) -> tuple[str, str]:
    """Split a token into `(scope, base)`, peeling varga then reference.

    The trailing dot in every scope is load-bearing — it is what stops `d2.`
    from swallowing the front of `d20.planet.sun.sign`.
    """
    scope = ""
    for group in (ALL_VARGA_SCOPES, ALL_REFERENCE_SCOPES):
        for candidate in group:
            if key.startswith(candidate):
                scope += candidate
                key = key[len(candidate) :]
                break
    return scope, key


def is_valid_fact_key(key: str) -> bool:
    """Whether `key` is well-formed under the grammar — not whether it is emitted."""
    _scope, base = split_scope(key)
    return base.startswith(BASE_PREFIXES)
