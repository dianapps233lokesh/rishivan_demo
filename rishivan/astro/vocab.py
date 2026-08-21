"""The fact token vocabulary. Freeze before any rule extraction begins.

The tightest coupling in the system: the chart's token vocabulary *is* the rule DSL's
condition vocabulary. A rule compiled to a token this module does not describe matches
no chart and raises nothing — the platform quietly degrades to passage retrieval. So it
is declared once, here, and pinned from both sides by tests.

A token is `<scope><base>`, scope empty for the default frame:

    planet.saturn.house                  Saturn's house, D1, counted from Lagna
    d9.planet.saturn.house               ... in Navamsa
    from_moon.planet.saturn.house        ... counted from the Moon
    house.7.lord.house                   where the 7th lord sits

**Recognised is not emitted.** `UNEMITTED_*` scopes are in the grammar so the compiler
can mark an atom `out_of_scope` — honest and reportable — rather than compile it into
one that silently matches nothing.
"""

from rishivan.astro.constants import PLANET_CODES

BASE_PREFIXES = (
    "lagna.",
    "planet.",
    "house.",
    "dasha.",
    "nakshatra.",
    "numerology.",
    "transit.",
)

EMITTED_VARGA_SCOPES = ("d2.", "d7.", "d9.", "d10.", "d12.", "d30.")
"""Wealth D2, children D7, marriage D9, career D10, parents D12, health D30. D1 is the
default scope and is never prefixed."""

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
"""Computed on every chart but not flattened into tokens: the full shodashavarga
cross-product would roughly triple a JSONB column that carries a GIN index."""

EMITTED_REFERENCE_SCOPES = ("from_moon.", "from_sun.")
"""Chandra and Surya lagna — the most cited alternative reference points."""

UNEMITTED_REFERENCE_SCOPES = ("from_arudha_lagna.",) + tuple(
    f"from_house{n}." for n in range(1, 13)
)
"""Arudha Lagna needs a computation the engine lacks; `from_house_n` is rare enough
that twelve more frames is a poor trade."""

ALL_VARGA_SCOPES = EMITTED_VARGA_SCOPES + UNEMITTED_VARGA_SCOPES
ALL_REFERENCE_SCOPES = EMITTED_REFERENCE_SCOPES + UNEMITTED_REFERENCE_SCOPES

EMITTED_SCOPES = ("",) + EMITTED_VARGA_SCOPES + EMITTED_REFERENCE_SCOPES
"""Varga and reference scopes are emitted independently, never combined: `d9.from_moon.`
is recognised by the grammar but never emitted."""


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
"""**The vocabulary lock** — each condition type mapped to the token it constrains.

`atom_to_fact_token` derives from this table rather than restating it: a second copy is
a second thing to drift, and drift here means every affected rule matches nothing.
Templates take a scope prefix plus the atom's values, so `planet_in_house` for Saturn in
Navamsa becomes `d9.planet.saturn.house`.
"""

SUPPORTED_CONDITION_TYPES = frozenset(CONDITION_TOKEN_TEMPLATES)

SET_FORM = {"house": "houses", "sign": "signs"}
"""Fields whose atom may name a SET instead of one value, singular -> plural.

Disjunction over one field is pervasive in classical Jyotish, not an edge case: "the
7th lord in the 6th, 8th or 12th", "the 8th lord in a kendra". With no way to say it
the model either flattened it into `all` -- `mars in house 1 AND 4 AND 7`, matching no
chart that has ever existed -- or gave up with `expressible: false`, which accounted
for eight of eighteen rules in the first review sample.

Lives here because the extractor, the validator, the compiler and the matcher must all
agree on it, and four copies of a mapping is four things to drift."""

OUT_OF_SCOPE_CONDITION_TYPES = frozenset({"strength_cmp"})
"""Cut from DSL v1 deliberately. `strength_cmp` needs Shadbala, which the engine does
not compute and on which implementations genuinely disagree — Cheshta and Kaala bala
conventions diverge. A condition the matcher cannot evaluate is a silent false promise,
so rules needing it park at `status='out_of_scope'` and stay passage-only."""

PLANET_TOKEN_NAME = {code: name for name, code in PLANET_CODES.items()}
"""Classical two-letter codes (how the books write them) to token names (how the engine
emits them). The likeliest cause of a total silent matching failure: `planet.Sa.house`
looks reasonable and matches nothing, ever. Derived from `constants.PLANET_CODES` so the
two spellings cannot drift."""


def split_scope(key: str) -> tuple[str, str]:
    """Split a token into `(scope, base)`, peeling varga then reference.

    The trailing dot in every scope is load-bearing — it stops `d2.` from swallowing the
    front of `d20.planet.sun.sign`.
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
