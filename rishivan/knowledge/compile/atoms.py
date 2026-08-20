"""Compile a validated rule condition into the denormalized atoms SQL prefilters on.

`rishivan/astro/vocab.py:94` names this file's job: derive `atom_to_fact_token` from
`CONDITION_TOKEN_TEMPLATES` rather than hand-writing token strings. Hand-writing them is
the specific mistake the vocabulary docstring warns about, because a mistyped token
raises nothing -- the rule just never matches any chart, and a rule base that silently
matches nothing looks exactly like a rule base that is merely thin.

Two design points worth stating, because both look like limitations and are not:

**Atoms are a prefilter, not the condition.** `rule_atom` has scalar `object_int` /
`object_str` and no set column, so `houses: [6, 8, 12]` compiles to three rows. Those
rows cannot express "exactly one of these", and they are not asked to: they narrow the
rule base to a handful of candidates, and `Rule.condition` JSONB is then evaluated
exactly. The model's own docstring says as much -- "the SQL prefilter the matcher uses
instead of loading every rule and evaluating it in Python".

**Compilation refuses what validation should have caught.** An atom missing a required
field, or a timing atom inside a formation, raises rather than compiling to something
harmless-looking. A half-atom in the prefilter widens a rule to charts the verse never
described, and that is worse than a loud failure at load time.
"""

from dataclasses import dataclass

from rishivan.astro.vocab import CONDITION_TOKEN_TEMPLATES, EMITTED_SCOPES, SET_FORM
from rishivan.knowledge.extract.prompt import CONDITION_ARGUMENTS

TIMING_TYPES = frozenset({"dasha_of", "transit_over"})
"""Identical in meaning to `rishivan.knowledge.extract.validate.TIMING_TYPES`: atoms that say
*when*, which may never satisfy a *promise*. Blueprint §8 rule 2."""

OPTIONAL_ARGUMENTS = frozenset({"scope"})


SUBJECT_FIELD: dict[str, str] = {
    "planet_in_house": "planet",
    "planet_in_sign": "planet",
    "planet_in_nakshatra": "planet",
    "lord_of_house_in_house": "lord_of",
    "lord_of_house_in_sign": "lord_of",
    "conjunct": "planet",
    "aspected_by": "planet",
    "dignity_is": "planet",
    "house_is_empty": "house",
    "dasha_of": "planet",
    "transit_over": "planet",
}

OBJECT_FIELD: dict[str, str] = {
    "planet_in_house": "house",
    "planet_in_sign": "sign",
    "planet_in_nakshatra": "nakshatra",
    "lord_of_house_in_house": "house",
    "lord_of_house_in_sign": "sign",
    "conjunct": "other",
    "aspected_by": "target",
    "dignity_is": "dignity",
    "house_is_empty": "house",
    "dasha_of": "level",
    "transit_over": "house",
}
"""Which field carries the asserted VALUE rather than the subject.

`aspected_by` is the one that reads backwards: `planet` casts the aspect and `target`
receives it, so the target is the object. `ARGUMENT_SEMANTICS` in the extraction prompt
spells this out because the model inverted it in a real run.
"""

_HOUSE_SUBJECT_TYPES = frozenset({"house_is_empty"})


@dataclass(frozen=True)
class CompiledAtom:
    condition_type: str
    subject: str
    object_int: int | None
    object_str: str | None
    from_reference: str
    varga: str
    negate: bool
    fact_token: str


def atom_to_fact_token(atom: dict, *, scope: str = "") -> str:
    """The fact token this atom constrains, derived from the vocabulary templates."""
    condition_type = atom.get("type")
    templates = CONDITION_TOKEN_TEMPLATES.get(condition_type)
    if not templates:
        raise ValueError(f"unknown condition type {condition_type!r}")
    if scope not in EMITTED_SCOPES:
        raise ValueError(f"scope {scope!r} is not emitted by the fact engine")

    template = templates[0]
    # `house.{house}.lord.*` templates take their number from `lord_of` (whose lord),
    # not from `house` (where that lord sits) -- the two are different fields and
    # swapping them produces a token for the wrong house.
    house_value = atom.get("lord_of") if ".lord." in template else atom.get("house")
    filled = template.format(
        planet=atom.get("planet", ""),
        other=atom.get("other", ""),
        target=atom.get("target", ""),
        house=house_value if house_value is not None else "",
        level=atom.get("level", ""),
    )
    if "{" in filled or ".." in filled or filled.endswith("."):
        raise ValueError(
            f"atom {atom!r} left the token incomplete: {filled!r} -- a required field "
            f"is missing"
        )
    return f"{scope}{filled}"


def _required_fields(condition_type: str) -> frozenset[str]:
    return frozenset(
        name
        for name in CONDITION_ARGUMENTS.get(condition_type, {})
        if name not in OPTIONAL_ARGUMENTS
    )


def _values_for(atom: dict, object_field: str) -> list:
    """The asserted values, whether given as a scalar or as its set form."""
    plural = SET_FORM.get(object_field)
    if plural and atom.get(plural):
        return list(atom[plural])
    value = atom.get(object_field)
    return [] if value is None else [value]


def _compile_atom(atom: dict, *, negate: bool) -> list[CompiledAtom]:
    condition_type = atom.get("type")
    if condition_type in TIMING_TYPES:
        raise ValueError(
            f"timing atom {condition_type!r} cannot be compiled into a formation: "
            f"timing must never manufacture a natal promise"
        )
    if condition_type not in CONDITION_ARGUMENTS:
        raise ValueError(f"unknown condition type {condition_type!r}")

    supplied = {
        key
        for key, value in atom.items()
        if key != "type" and value not in (None, "", [])
    }
    required = set(_required_fields(condition_type))
    for scalar, plural in SET_FORM.items():
        if plural in supplied:
            required.discard(scalar)
    if missing := sorted(required - supplied):
        raise ValueError(
            f"atom {atom!r} is missing {missing} -- validation should have rejected it "
            f"before compilation"
        )

    scope = atom.get("scope") or ""
    subject_field = SUBJECT_FIELD[condition_type]
    object_field = OBJECT_FIELD[condition_type]
    # `house_is_empty` is the one type whose subject and object are the same field, so
    # each value of a set names a DIFFERENT token: `houses: [3, 6]` is
    # house.3.occupant_count and house.6.occupant_count, not one token with two values.
    # Everywhere else the token is fixed and only the value varies. Found by compiling
    # the whole book: 375 of 376 rules compiled and this shape was the one that did not.
    token_varies = subject_field == object_field

    compiled = []
    for value in _values_for(atom, object_field):
        is_int = not isinstance(value, bool) and isinstance(value, int)
        token = atom_to_fact_token(
            {**atom, object_field: value} if token_varies else atom, scope=scope
        )
        subject = str(value if token_varies else atom.get(subject_field))
        if condition_type in _HOUSE_SUBJECT_TYPES:
            subject = f"house:{subject}"
        compiled.append(
            CompiledAtom(
                condition_type=condition_type,
                subject=subject,
                object_int=int(value) if is_int else None,
                object_str=None if is_int else str(value),
                from_reference=scope.rstrip(".") or "lagna",
                varga=scope.rstrip(".").upper() if scope.startswith("d") else "D1",
                negate=negate,
                fact_token=token,
            )
        )
    return compiled


def compile_condition(
    condition: dict | None, *, negate: bool = False
) -> list[CompiledAtom]:
    """Every atom in a condition, flattened, with negated atoms marked.

    `negate` marks the whole condition; `none` entries are always negated regardless,
    because "unless Jupiter aspects it" must not prefilter as a requirement.
    """
    if not condition:
        return []
    compiled: list[CompiledAtom] = []
    for atom in condition.get("atoms") or []:
        compiled += _compile_atom(atom, negate=negate)
    for atom in condition.get("none") or []:
        compiled += _compile_atom(atom, negate=True)
    return compiled
