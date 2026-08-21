# Rule-Grounded RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn extracted Koonji rules into the primary retrieval path for an answer, with the existing page-vector RAG as the fallback, so every answer cites either a matched rule or a source page and never invents either.

**Architecture:** A chart is reduced to a flat dict of **fact tokens** (`planet.saturn.house` → `7`). Each extracted rule is compiled to `rule_atom` rows carrying the same tokens, so SQL can *prefilter* candidate rules cheaply; the exact condition (combinators, `none`, set forms) is then evaluated in Python against the rule's `condition` JSONB. Matched rules are scored for the answering Rishi via the persona → life-domain map, and the orchestrator prefers them over page retrieval, falling back to pages when nothing matches.

**Tech Stack:** Python 3.14, SQLAlchemy 2 async + asyncpg (knowledge layer), Qdrant (existing page vectors), Streamlit (runtime), Swiss Ephemeris via `pyswisseph`, pytest.

**Spec:** `/Users/admin/Downloads/Rishivan_Ultimate_Astrology_AI_Engine_Master_Implementation_Blueprint (1).pdf` (Blueprint) and `/Users/admin/Downloads/Rishivan_Eight_Rishis_Complete_Domain_Ownership_and_Question_Coverage (1).pdf` (Eight Rishis). Copy both into `docs/client/` as Task 0 so the plan's authority travels with the repo.

## Global Constraints

- **The LLM never asserts astrology.** Blueprint §18: it "may explain structured conclusions" and "must not invent planetary positions, invent citations, rewrite canonical rules silently, or override deterministic calculations."
- **Never build PDF → embeddings → LLM → prediction.** Blueprint §1. Rules are retrieved structurally; vectors are for passages only.
- **Three retrieval systems, not one.** Blueprint §11: semantic/vector + structured SQL + knowledge graph. This plan delivers vector + structured SQL. The knowledge graph is explicitly out of scope and is a separate plan.
- **Only approved rules may reach a user.** `MATCHABLE_PREDICATE` in `app/models/knowledge/rule.py:28` is the single definition: `status = 'parsed' AND approved_at IS NOT NULL AND deleted_at IS NULL`. Never re-express it inline.
- **Natal promise and timing stay separate.** Blueprint §8 rule 2. `formation` carries the promise; `timing.activation_factors` carries activation. A timing atom must never satisfy a formation condition.
- **Aarogya forbidden claims.** Eight Rishis §9: "Never diagnose a disease, predict death as certainty, prescribe treatment, or tell the user to avoid medical care. Present traditional interpretations with clear uncertainty."
- **Vocabulary is generated, never restated.** `app/astro/vocab.py` is the single source for tokens; its docstring warns "a second copy is a second thing to drift, and drift here means every affected rule silently matches nothing." Any copy requires a contract test.
- **Planet names, never book codes.** `saturn`, never `Sa`. `PLANET_TOKEN_NAME` maps one to the other.
- **Rishi keys.** Rules are annotated with the client's eight life domains (`atma prema artha karma vansh aarogya yatra dharma`). The runtime's eight personas (`agam vyom dhruvan ritam tejan medhan tattvan pragnav`) reach them through `RISHI_LIFE_DOMAINS` in `rishivan/council/domains.py`. Personas stay canonical per the user's decision of 2026-08-19.

## Measured Baseline (why the tasks are ordered this way)

Taken on 2026-08-19 against 58 valid extracted rules and the live chart engine:

| Atom type | Count in valid rules | Chart engine emits it today? |
|---|---|---|
| `lord_of_house_in_house` | 33 | yes (`Chart.house_lords`) |
| `planet_in_house` | 17 | yes (`PlanetPosition.house`) |
| `planet_in_sign` | 6 | yes (`PlanetPosition.rashi`) |
| `lord_of_house_in_sign` | 2 | yes |
| `aspected_by` | 4 | **no** |
| `conjunct` | 4 | **no** |
| `dignity_is` | 2 | **no** |

**84% of valid rules are matchable with what the chart engine already computes.** The missing three types block 9 of 58 rules (16%), which is why they are Task 9 rather than Task 1 — the pipeline delivers value before them.

Two hard facts that constrain the design:

1. **The runtime has no database.** `grep` for `async_session_factory|sqlalchemy|asyncpg` across `rishivan/` and `streamlit_app.py` returns nothing — the answering path is Qdrant-only. Rules live in Postgres. Task 6 resolves this and is the plan's one genuine architectural decision.
2. **`rule_atom` cannot express a set.** It has `object_int`/`object_str` scalars and no set column, so `houses: [6,8,12]` becomes three rows. That is why atoms are a *prefilter* and the authoritative evaluation reads `Rule.condition` JSONB — exactly as the model's own docstring states ("the SQL prefilter the matcher uses instead of loading every rule and evaluating it in Python").

---

### Task 0: Vendor the client specs into the repo

**Files:**
- Create: `docs/client/README.md`
- Copy: the two client PDFs into `docs/client/`

- [ ] **Step 1: Copy the specs**

```bash
mkdir -p docs/client
cp "/Users/admin/Downloads/Rishivan_Ultimate_Astrology_AI_Engine_Master_Implementation_Blueprint (1).pdf" \
   docs/client/blueprint-master-implementation.pdf
cp "/Users/admin/Downloads/Rishivan_Eight_Rishis_Complete_Domain_Ownership_and_Question_Coverage (1).pdf" \
   docs/client/eight-rishis-domain-ownership.pdf
```

- [ ] **Step 2: Write the index**

```markdown
# Client specifications

The two documents this pipeline implements. Vendored because every design decision
below cites them by section, and a plan whose authority lives in someone's Downloads
folder cannot be checked by the next engineer.

- `blueprint-master-implementation.pdf` — the engine architecture. §1 non-negotiable
  architecture, §6 the Koonji rule format, §8 the twelve reasoning rules, §11 three
  retrieval systems, §12 source tiers, §15 the validation lab, §18 what the LLM may
  and may not do, §19 the production answer contract.
- `eight-rishis-domain-ownership.pdf` — the Rishi division. §3 the eight dimensions,
  §12 questions that cross multiple Rishis, §14 what each Rishi's Koonji must hold,
  §15 the weighted Book × Rishi matrix, §21 the final naming directive.

Note on naming: §21 names the eight Rishis ATMA…DHARMA. This repo keeps its own eight
persona names and maps them onto the client's eight via `RISHI_LIFE_DOMAINS`
(`rishivan/council/domains.py`). That was a deliberate decision, not an oversight —
the two sets are different taxonomies, so the mapping is weighted and many-to-many.
```

- [ ] **Step 3: Commit**

```bash
git add docs/client
git commit -m "docs: vendor the client blueprint and Rishi domain specs"
```

---

### Task 1: Chart → fact tokens

The join key between a birth chart and the rule base. Everything downstream depends on this producing exactly the tokens `vocab.py` defines.

**Files:**
- Create: `rishivan/chart/tokens.py`
- Test: `tests/chart/test_tokens.py`

**Interfaces:**
- Consumes: `rishivan.chart.ephemeris.Chart` (fields `planets: dict[str, PlanetPosition]`, `house_lords: dict[int, str]`, `lagna_rashi`), `PlanetPosition` (`house: int`, `rashi: str`, `nakshatra: str`, `pada: int`).
- Produces: `chart_tokens(chart: Chart, *, scope: str = "") -> dict[str, int | str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/chart/test_tokens.py
"""The join key between a chart and the rule base.

Every assertion here is a contract with `app/astro/vocab.py`. A token this module
spells differently from the vocabulary is not an error anyone sees -- the affected
rules simply match no chart, ever.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.tokens import chart_tokens

# 15 Aug 1947, 00:00 IST, New Delhi. A fixed, real chart so the expected tokens are
# checkable by hand against any ephemeris.
INDIA = BirthData(
    year=1947, month=8, day=15, hour=0, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture(scope="module")
def tokens():
    return chart_tokens(compute_chart(INDIA))


def test_every_planet_has_a_house_token(tokens):
    for planet in ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn",
                   "rahu", "ketu"):
        key = f"planet.{planet}.house"
        assert key in tokens, f"missing {key}"
        assert 1 <= tokens[key] <= 12


def test_planet_names_are_token_names_not_book_codes(tokens):
    """`planet.Sa.house` looks perfectly reasonable and matches nothing, ever."""
    assert "planet.saturn.house" in tokens
    assert not any(".Sa." in key or ".Su." in key for key in tokens)


def test_signs_are_lowercase_english(tokens):
    """Rules carry `sign: "aries"`; a token holding "Mesha" or "Aries" never matches."""
    for planet in ("sun", "moon", "saturn"):
        value = tokens[f"planet.{planet}.sign"]
        assert value.islower(), value
        assert value in {
            "aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra",
            "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
        }


def test_every_house_has_a_lord_house_token(tokens):
    """33 of 58 valid extracted rules are `lord_of_house_in_house` -- the single most
    used atom type in the corpus, so this token carries most of the rule base."""
    for house in range(1, 13):
        key = f"house.{house}.lord.house"
        assert key in tokens, f"missing {key}"
        assert 1 <= tokens[key] <= 12


def test_house_occupant_counts_are_present_for_all_twelve(tokens):
    for house in range(1, 13):
        assert tokens[f"house.{house}.occupant_count"] >= 0
    # Nine bodies distributed over twelve houses.
    assert sum(tokens[f"house.{h}.occupant_count"] for h in range(1, 13)) == 9


def test_nakshatra_and_pada_tokens_exist(tokens):
    assert isinstance(tokens["planet.moon.nakshatra"], str)
    assert 1 <= tokens["planet.moon.pada"] <= 4


def test_scope_prefixes_every_token(tokens):
    """A varga token is the same base under a scope prefix. Mixing scopes silently
    would compare a D9 placement against a D1 rule."""
    d9 = chart_tokens(compute_chart(INDIA), scope="d9.")
    assert all(key.startswith("d9.") for key in d9)
    assert "d9.planet.saturn.house" in d9


def test_rejects_an_unemitted_scope():
    """`vocab.py` enumerates the emitted scopes; anything else is a typo that would
    produce tokens no rule can ever reference."""
    with pytest.raises(ValueError, match="not emitted"):
        chart_tokens(compute_chart(INDIA), scope="d40.")


def test_ketu_is_derived_and_opposite_rahu(tokens):
    """The ephemeris computes only the mean node. Ketu is 180 degrees away, and rules
    reference it by name, so it must be a first-class token."""
    assert (tokens["planet.ketu.house"] - tokens["planet.rahu.house"]) % 12 == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/chart/test_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rishivan.chart.tokens'`

- [ ] **Step 3: Write the implementation**

```python
# rishivan/chart/tokens.py
"""Reduce a computed chart to the flat fact tokens the rule base is written against.

This module is the contract between two halves of the system that were built
separately and do not otherwise speak. The chart engine produces English sentences for
page retrieval ("Ascendant (Lagna) is Aries."); rules are compiled to tokens
(`planet.saturn.house` -> 7). Both are needed, and only the tokens can be matched.

The failure mode this module must not have is silence. `vocab.py` warns that a token
spelled differently from the vocabulary means "every affected rule silently matches
nothing" -- no exception, no empty-result signal, just a rule base that appears thin.
So the scope is validated against the emitted list, and a contract test in
`tests/chart/test_tokens.py` pins the spelling of every token family.

Deliberately does NOT emit `dignity_is`, `conjunct` or `aspected_by`: the ephemeris
computes no dignity table, no aspect model and no conjunction orb. That gap blocks 9 of
58 valid extracted rules (16%) and is closed by its own task rather than guessed at
here -- a wrong aspect model would match the wrong charts, which is worse than
matching none.
"""

from app.astro.vocab import EMITTED_SCOPES, PLANET_TOKEN_NAME
from rishivan.chart.ephemeris import Chart

SIGN_TOKEN_NAME: dict[str, str] = {
    "Aries": "aries", "Taurus": "taurus", "Gemini": "gemini", "Cancer": "cancer",
    "Leo": "leo", "Virgo": "virgo", "Libra": "libra", "Scorpio": "scorpio",
    "Sagittarius": "sagittarius", "Capricorn": "capricorn", "Aquarius": "aquarius",
    "Pisces": "pisces",
}
"""Ephemeris rashi name -> the name rules use. The extractor emits `sign: "aries"`
because the vocabulary is lowercase English, so a token holding "Aries" or "Mesha"
matches nothing."""

EPHEMERIS_PLANET_NAME: dict[str, str] = {
    "Sun": "sun", "Moon": "moon", "Mars": "mars", "Mercury": "mercury",
    "Jupiter": "jupiter", "Venus": "venus", "Saturn": "saturn",
    "Rahu": "rahu", "Ketu": "ketu",
}
"""`Chart.planets` is keyed by display name; tokens use the vocabulary's names."""


def chart_tokens(chart: Chart, *, scope: str = "") -> dict[str, int | str]:
    """Every fact token this chart supports, as token -> value.

    `scope` is a prefix from `EMITTED_SCOPES` -- "" for D1 counted from the Ascendant,
    "d9." for Navamsa, "from_moon." for a lunar reference frame. Callers pass one scope
    per call and merge, so a D1 rule can never accidentally read a D9 placement.
    """
    if scope not in EMITTED_SCOPES:
        raise ValueError(
            f"scope {scope!r} is not emitted by the fact engine; "
            f"emitted scopes are {EMITTED_SCOPES}"
        )

    tokens: dict[str, int | str] = {}
    occupants = dict.fromkeys(range(1, 13), 0)

    for display_name, position in chart.planets.items():
        planet = EPHEMERIS_PLANET_NAME.get(display_name)
        if planet is None:
            continue
        tokens[f"{scope}planet.{planet}.house"] = position.house
        tokens[f"{scope}planet.{planet}.sign"] = SIGN_TOKEN_NAME.get(
            position.rashi, position.rashi.lower()
        )
        tokens[f"{scope}planet.{planet}.nakshatra"] = position.nakshatra
        tokens[f"{scope}planet.{planet}.pada"] = position.pada
        occupants[position.house] = occupants.get(position.house, 0) + 1

    for house in range(1, 13):
        tokens[f"{scope}house.{house}.occupant_count"] = occupants[house]
        lord = chart.house_lords.get(house)
        if lord is None:
            continue
        lord_name = EPHEMERIS_PLANET_NAME.get(lord, lord.lower())
        lord_position = chart.planets.get(lord)
        if lord_position is None:
            continue
        tokens[f"{scope}house.{house}.lord.house"] = lord_position.house
        tokens[f"{scope}house.{house}.lord.sign"] = SIGN_TOKEN_NAME.get(
            lord_position.rashi, lord_position.rashi.lower()
        )
        tokens[f"{scope}house.{house}.lord.name"] = lord_name

    return tokens


def assert_ketu_present(chart: Chart) -> None:
    """Rules name Ketu; `_PLANETS` in the ephemeris computes only the mean node.

    Called by `compute_chart` callers that need token coverage. Kept as an explicit
    check rather than a silent derivation so a missing Ketu surfaces here instead of as
    a rule that never fires.
    """
    if "Ketu" not in chart.planets:
        raise ValueError(
            "chart has no Ketu; rules reference planet.ketu.* and would never match"
        )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/chart/test_tokens.py -v`
Expected: PASS. If `test_ketu_is_derived_and_opposite_rahu` fails, the ephemeris is not
deriving Ketu — fix `rishivan/chart/ephemeris.py` to add it (Rahu longitude + 180°,
same house arithmetic) rather than weakening the test.

- [ ] **Step 5: Commit**

```bash
git add rishivan/chart/tokens.py tests/chart/test_tokens.py
git commit -m "feat(chart): emit fact tokens so charts and rules share one vocabulary"
```

---

### Task 2: Compile a rule's condition into atoms

**Files:**
- Create: `app/knowledge/compile/atoms.py`
- Test: `tests/knowledge/compile/test_atoms.py`

**Interfaces:**
- Consumes: `CONDITION_ARGUMENTS` from `app.knowledge.extract.prompt`, `CONDITION_TOKEN_TEMPLATES` from `app.astro.vocab`.
- Produces:
  - `atom_to_fact_token(atom: dict, *, scope: str = "") -> str`
  - `CompiledAtom` dataclass with fields `condition_type, subject, object_int, object_str, from_reference, varga, negate, fact_token`
  - `compile_condition(condition: dict, *, negate: bool = False) -> list[CompiledAtom]`

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/compile/test_atoms.py
"""Rule condition JSON -> the denormalized atoms SQL prefilters on.

`vocab.py:94` states the requirement this file satisfies: "P2's rule compiler must
derive `atom_to_fact_token`" from the vocabulary rather than hand-writing token
strings.
"""

import pytest

from app.astro.vocab import CONDITION_TOKEN_TEMPLATES
from app.knowledge.compile.atoms import (
    atom_to_fact_token,
    compile_condition,
)


def test_planet_in_house_token():
    assert (
        atom_to_fact_token({"type": "planet_in_house", "planet": "saturn", "house": 7})
        == "planet.saturn.house"
    )


def test_lord_of_house_in_house_token():
    """The most common atom in the corpus: 33 of 58 valid rules."""
    assert (
        atom_to_fact_token(
            {"type": "lord_of_house_in_house", "lord_of": 8, "house": 1}
        )
        == "house.8.lord.house"
    )


def test_scope_prefixes_the_token():
    assert (
        atom_to_fact_token(
            {"type": "planet_in_house", "planet": "moon", "house": 4},
            scope="from_sun.",
        )
        == "from_sun.planet.moon.house"
    )


def test_every_condition_type_in_the_vocabulary_can_be_tokenised():
    """A type the compiler cannot tokenise is a rule family that silently never
    matches, so the compiler must cover the vocabulary exhaustively."""
    samples = {
        "planet_in_house": {"planet": "sun", "house": 1},
        "planet_in_sign": {"planet": "sun", "sign": "leo"},
        "planet_in_nakshatra": {"planet": "moon", "nakshatra": "ashwini", "pada": 1},
        "lord_of_house_in_house": {"lord_of": 1, "house": 1},
        "lord_of_house_in_sign": {"lord_of": 1, "sign": "aries"},
        "conjunct": {"planet": "sun", "other": "moon"},
        "aspected_by": {"planet": "jupiter", "target": "7"},
        "dignity_is": {"planet": "mars", "dignity": "exalted"},
        "house_is_empty": {"house": 7},
        "dasha_of": {"planet": "saturn", "level": "maha"},
        "transit_over": {"planet": "jupiter", "house": 10},
    }
    assert set(samples) == set(CONDITION_TOKEN_TEMPLATES), (
        "sample set has drifted from the vocabulary"
    )
    for condition_type, arguments in samples.items():
        token = atom_to_fact_token({"type": condition_type, **arguments})
        assert token, condition_type
        assert "{" not in token, f"{condition_type} left a placeholder: {token}"


def test_a_set_form_compiles_to_one_atom_per_value():
    """`rule_atom` has scalar `object_int` and no set column, so "the 7th lord in the
    6th, 8th or 12th" becomes three rows sharing a rule. They are a PREFILTER: the
    disjunction lives in `Rule.condition` and is evaluated there."""
    atoms = compile_condition(
        {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7,
                    "houses": [6, 8, 12]}]}
    )
    assert len(atoms) == 3
    assert {a.object_int for a in atoms} == {6, 8, 12}
    assert {a.fact_token for a in atoms} == {"house.7.lord.house"}


def test_negated_atoms_are_marked():
    """"unless Jupiter aspects it" must not prefilter as though it were required."""
    atoms = compile_condition(
        {
            "atoms": [{"type": "planet_in_house", "planet": "saturn", "house": 7}],
            "none": [{"type": "planet_in_house", "planet": "jupiter", "house": 7}],
        }
    )
    by_planet = {a.subject: a.negate for a in atoms}
    assert by_planet == {"saturn": False, "jupiter": True}


def test_string_values_go_to_object_str_and_ints_to_object_int():
    signs = compile_condition(
        {"atoms": [{"type": "planet_in_sign", "planet": "sun", "sign": "leo"}]}
    )
    assert signs[0].object_str == "leo" and signs[0].object_int is None
    houses = compile_condition(
        {"atoms": [{"type": "planet_in_house", "planet": "sun", "house": 5}]}
    )
    assert houses[0].object_int == 5 and houses[0].object_str is None


def test_house_subject_is_prefixed_so_it_cannot_collide_with_a_planet():
    """`RuleAtom.subject` is documented as "Planet code, or `house:7`". Without the
    prefix, house 7 and a planet named "7" would share a subject."""
    atoms = compile_condition({"atoms": [{"type": "house_is_empty", "house": 7}]})
    assert atoms[0].subject == "house:7"


def test_timing_atoms_are_refused_in_a_formation():
    """Blueprint §8 rule 2. A dasha compiled into formation lets timing manufacture a
    natal promise, which the client states as an absolute."""
    with pytest.raises(ValueError, match="timing atom"):
        compile_condition(
            {"atoms": [{"type": "dasha_of", "planet": "saturn", "level": "maha"}]}
        )


def test_an_incomplete_atom_is_refused_rather_than_compiled():
    """`validate_rule` should have caught this upstream; compiling it anyway would put
    a half-atom in the prefilter, matching charts the verse never described."""
    with pytest.raises(ValueError, match="missing"):
        compile_condition({"atoms": [{"type": "lord_of_house_in_house", "lord_of": 5}]})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/knowledge/compile/test_atoms.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.knowledge.compile'`

- [ ] **Step 3: Write the implementation**

```python
# app/knowledge/compile/atoms.py
"""Compile a validated rule condition into the denormalized atoms SQL prefilters on.

`app/astro/vocab.py:94` names this file's job: derive `atom_to_fact_token` from
`CONDITION_TOKEN_TEMPLATES` rather than hand-writing token strings. Hand-writing them
is the specific mistake the vocabulary docstring warns about, because a mistyped token
raises nothing -- the rule just never matches any chart.

Two design points worth stating, because both look like limitations and are not:

**Atoms are a prefilter, not the condition.** `rule_atom` has scalar `object_int` /
`object_str` and no set column, so `houses: [6, 8, 12]` compiles to three rows. Those
rows cannot express "exactly one of these", and they are not asked to: they narrow
millions of rules to a handful, and `Rule.condition` JSONB is then evaluated exactly.
The model's own docstring says as much -- "the SQL prefilter the matcher uses instead
of loading every rule and evaluating it in Python".

**Compilation refuses what validation should have caught.** An atom missing a required
field, or a timing atom inside a formation, raises rather than compiling to something
harmless-looking. A half-atom in the prefilter widens a rule to charts the verse never
described, and that is worse than a loud failure at load time.
"""

from dataclasses import dataclass

from app.astro.vocab import CONDITION_TOKEN_TEMPLATES, EMITTED_SCOPES
from app.knowledge.extract.prompt import CONDITION_ARGUMENTS

TIMING_TYPES = frozenset({"dasha_of", "transit_over"})
"""Kept identical to `app.knowledge.extract.validate.TIMING_TYPES` in meaning: atoms
that say *when*, which may never satisfy a *promise*."""

OPTIONAL_ARGUMENTS = frozenset({"scope"})

_SET_FORM = {"house": "houses", "sign": "signs"}

_SUBJECT_FIELD: dict[str, str] = {
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

_OBJECT_FIELD: dict[str, str] = {
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
"""Which field carries the asserted VALUE, as opposed to the subject. `aspected_by` is
the one that reads backwards: `planet` casts the aspect and `target` receives it, so
the target is the object. `ARGUMENT_SEMANTICS` in the prompt spells this out because
the model inverted it in a real run."""

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
    # `planet_in_nakshatra` and `transit_over` declare two templates; the first is the
    # one the atom's object constrains, and `pada` / `sign` ride along as extra atoms
    # only when the rule actually supplies them.
    filled = template.format(
        planet=atom.get("planet", ""),
        other=atom.get("other", ""),
        target=atom.get("target", ""),
        house=atom.get("lord_of") if "lord" in template else atom.get("house", ""),
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


def _values_for(atom: dict, object_field: str) -> list[int | str]:
    """The asserted values, whether given as a scalar or as its set form."""
    plural = _SET_FORM.get(object_field)
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
        key for key, value in atom.items() if key != "type" and value not in (None, "", [])
    }
    required = set(_required_fields(condition_type))
    for scalar, plural in _SET_FORM.items():
        if plural in supplied:
            required.discard(scalar)
    if missing := sorted(required - supplied):
        raise ValueError(
            f"atom {atom!r} is missing {missing} -- validation should have rejected it "
            f"before compilation"
        )

    scope = atom.get("scope") or ""
    token = atom_to_fact_token(atom, scope=scope)
    subject_field = _SUBJECT_FIELD[condition_type]
    subject = str(atom.get(subject_field))
    if condition_type in _HOUSE_SUBJECT_TYPES:
        subject = f"house:{subject}"

    compiled = []
    for value in _values_for(atom, _OBJECT_FIELD[condition_type]):
        is_int = isinstance(value, bool) is False and isinstance(value, int)
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


def compile_condition(condition: dict | None, *, negate: bool = False) -> list[CompiledAtom]:
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/knowledge/compile/test_atoms.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add app/knowledge/compile tests/knowledge/compile
git commit -m "feat(compile): derive rule_atom fact tokens from the vocabulary lock"
```

---

### Task 3: Load extracted rules into the rule base

**Files:**
- Create: `app/knowledge/compile/persist.py`
- Create: `scripts/load_koonji.py`
- Test: `tests/knowledge/compile/test_persist.py`

**Interfaces:**
- Consumes: `CompiledAtom`, `compile_condition` (Task 2); `Rule`, `RuleAtom` from `app.models.knowledge.rule`; `SutraUnit`.
- Produces: `LoadReport` dataclass (`rules, atoms, skipped, refused, failures`), `async def load_rules(session, *, rows: list[dict], book_slug: str) -> LoadReport`

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/compile/test_persist.py
"""Loading extracted rules is where "degraded, never dropped" becomes a row count.

These tests use no database: `load_rules` is split so the decision logic --
what to load, what to refuse, what a rule_key is -- is a pure function over rows.
"""

import pytest

from app.knowledge.compile.persist import (
    load_decision,
    rule_key_for,
)

VALID_ROW = {
    "unit_id": 9420, "chapter": "12", "verse_ref": "2", "verdict": "VALID",
    "valid": True, "translation": "If even one among Mercury, Jupiter and Venus...",
    "problems": [],
    "rule": {
        "rule_key": "12.2.1",
        "formation": {"combinator": "any", "atoms": [
            {"type": "planet_in_house", "planet": "mercury", "houses": [1, 4, 7, 10]},
        ]},
        "effects": [{"polarity": "positive", "strength": "moderate",
                     "statement": "destroys all evils"}],
        "life_domains": ["general"], "rule_category": "formation",
        "expressible": True,
    },
}


def test_a_valid_rule_is_loaded_as_parsed_and_unapproved():
    """`ix_rule_matchable` requires `approved_at IS NOT NULL`, so loading must never
    set it. An auto-approved rule reaches a user unreviewed."""
    decision = load_decision(VALID_ROW)
    assert decision.load is True
    assert decision.status == "parsed"
    assert decision.approved_at is None


def test_a_declined_row_is_not_a_rule():
    """61% of extractions are declines. They belong in `knowledge_item` with their
    reason, and loading them as rules would fill the rule base with conditionless
    rows that match every chart or none."""
    row = {**VALID_ROW, "verdict": "DECLINED", "valid": True,
           "rule": {**VALID_ROW["rule"], "expressible": False,
                    "out_of_scope_reason": "benefic/malefic as a class",
                    "formation": {"atoms": []}}}
    decision = load_decision(row)
    assert decision.load is False
    assert "declined" in decision.reason


def test_an_invalid_row_is_loaded_unparsed_not_discarded():
    """Degraded, never dropped: an invalid extraction is kept with its faults so a
    reviewer can fix it, but `status='unparsed'` keeps it out of `ix_rule_matchable`."""
    row = {**VALID_ROW, "verdict": "INVALID", "valid": False,
           "problems": ["atom[0] conjunct: required field 'planet' is missing"]}
    decision = load_decision(row)
    assert decision.load is True
    assert decision.status == "unparsed"


def test_rule_key_is_namespaced_by_book():
    """`uq_rule_key_version` is unique across the whole table, and two books both have
    a chapter 12 verse 2."""
    key = rule_key_for(VALID_ROW, book_slug="bphs-gcsharma-vol1")
    assert key.startswith("bphs-gcsharma-vol1:")
    assert "12.2" in key


def test_rule_key_is_stable_across_runs():
    """Re-running extraction must update a rule, not append a twin."""
    assert rule_key_for(VALID_ROW, book_slug="b") == rule_key_for(VALID_ROW, book_slug="b")


def test_two_rules_from_one_verse_get_distinct_keys():
    """A verse fanned out into siblings -- BPHS 24.2 produced three -- must not
    collapse into one row."""
    second = {**VALID_ROW, "rule": {**VALID_ROW["rule"], "rule_key": "12.2.2"}}
    assert rule_key_for(VALID_ROW, book_slug="b") != rule_key_for(second, book_slug="b")


def test_a_rule_whose_atoms_will_not_compile_is_refused_loudly():
    """Compilation refuses half-atoms. The loader must surface that as a refusal with
    the rule key, not swallow it and load a rule with no atoms -- a rule with an empty
    prefilter is invisible to the matcher while looking present in the table."""
    row = {**VALID_ROW, "rule": {**VALID_ROW["rule"],
           "formation": {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 5}]}}}
    decision = load_decision(row)
    assert decision.load is False
    assert "compile" in decision.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/knowledge/compile/test_persist.py -v`
Expected: FAIL — cannot import `load_decision`

- [ ] **Step 3: Write the implementation**

```python
# app/knowledge/compile/persist.py
"""Load extracted rules into `rule` + `rule_atom`, idempotently.

The decision logic is a pure function (`load_decision`) over an extraction row, so the
rules about what may enter the rule base are testable without a database. Three of them
matter more than the rest:

**Nothing is auto-approved.** `MATCHABLE_PREDICATE` requires `approved_at IS NOT NULL`,
and this loader never sets it. Every rule enters `status='parsed'` and invisible.

**Declines are not rules.** 61% of extractions decline, correctly, because the
vocabulary cannot express the verse. Those belong in `knowledge_item` with their
`out_of_scope_reason`; loading them as rules would fill the matcher with conditionless
rows.

**Invalid extractions are kept, not dropped.** They load as `status='unparsed'` with
their faults recorded, which keeps them out of the matchable index while leaving a
reviewer something to fix. What is refused instead is a rule whose atoms will not
compile: a rule with an empty prefilter is invisible to the matcher while looking
perfectly present in the table, and that is the failure mode this whole pipeline is
built to avoid.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.compile.atoms import CompiledAtom, compile_condition
from app.models.knowledge.book import Book
from app.models.knowledge.rule import Rule, RuleAtom


@dataclass
class Decision:
    load: bool
    status: str = "parsed"
    approved_at: datetime | None = None
    reason: str = ""
    atoms: list[CompiledAtom] = field(default_factory=list)


@dataclass
class LoadReport:
    rules: int = 0
    atoms: int = 0
    updated: int = 0
    refused: int = 0
    failures: list[str] = field(default_factory=list)

    def line(self) -> str:
        return (
            f"rules={self.rules} updated={self.updated} atoms={self.atoms} "
            f"refused={self.refused}"
        )


def rule_key_for(row: dict, *, book_slug: str) -> str:
    """A stable, book-namespaced identity for one extracted rule.

    `uq_rule_key_version` is unique across the whole table and two books both have a
    chapter 12 verse 2, so the slug is part of the key. The extractor's own `rule_key`
    distinguishes siblings from one verse (BPHS 24.2 produced three).
    """
    inner = str(row["rule"].get("rule_key") or f"{row['chapter']}.{row['verse_ref']}")
    return f"{book_slug}:{inner}"


def load_decision(row: dict) -> Decision:
    """Whether this extraction row may enter the rule base, and how."""
    rule = row.get("rule") or {}
    if rule.get("expressible") is False or row.get("verdict", "").startswith("DECLINED"):
        return Decision(
            load=False,
            reason=(
                "declined by the extractor: "
                f"{rule.get('out_of_scope_reason') or 'no reason given'}"
            ),
        )
    try:
        atoms = compile_condition(rule.get("formation"))
    except ValueError as exc:
        return Decision(load=False, reason=f"will not compile: {exc}")
    if not atoms:
        return Decision(
            load=False,
            reason="will not compile: no atoms, so the prefilter would be empty",
        )
    return Decision(
        load=True,
        status="parsed" if row.get("valid") else "unparsed",
        approved_at=None,
        atoms=atoms,
    )


async def load_rules(
    session: AsyncSession, *, rows: list[dict], book_slug: str
) -> LoadReport:
    """Write rules and their atoms. Re-running replaces a rule's atoms rather than
    appending, so a second load is a no-op rather than a duplication."""
    report = LoadReport()
    book = (
        await session.execute(select(Book).where(Book.slug == book_slug))
    ).scalar_one()

    for row in rows:
        decision = load_decision(row)
        if not decision.load:
            report.refused += 1
            report.failures.append(
                f"{rule_key_for(row, book_slug=book_slug)}: {decision.reason}"
            )
            continue

        key = rule_key_for(row, book_slug=book_slug)
        rule = (
            await session.execute(select(Rule).where(Rule.rule_key == key))
        ).scalar_one_or_none()
        payload = row["rule"]
        if rule is None:
            rule = Rule(rule_key=key, version=1, book_id=book.id, unit_id=row["unit_id"])
            session.add(rule)
            report.rules += 1
        else:
            report.updated += 1
            # Replace the prefilter wholesale: a stale atom is a rule matching charts
            # its current condition does not describe.
            for existing in (
                await session.execute(
                    select(RuleAtom).where(RuleAtom.rule_id == rule.id)
                )
            ).scalars():
                await session.delete(existing)

        rule.condition = payload.get("formation")
        rule.raw_condition_text = payload.get("raw_condition_text")
        rule.effect = {"effects": payload.get("effects") or []}
        rule.life_domains = payload.get("life_domains") or []
        rule.source = {
            "book_slug": book_slug,
            "chapter": row["chapter"],
            "verse_ref": row["verse_ref"],
            "unit_id": row["unit_id"],
            "translation": row.get("translation", ""),
        }
        rule.status = decision.status
        rule.atom_count = len(decision.atoms)
        rule.approved_at = None

        await session.flush()
        for atom in decision.atoms:
            session.add(
                RuleAtom(
                    rule_id=rule.id,
                    condition_type=atom.condition_type,
                    subject=atom.subject,
                    object_int=atom.object_int,
                    object_str=atom.object_str,
                    from_reference=atom.from_reference,
                    varga=atom.varga,
                    negate=atom.negate,
                    fact_token=atom.fact_token,
                )
            )
            report.atoms += 1
    return report
```

- [ ] **Step 4: Write the loader script**

```python
# scripts/load_koonji.py
"""Load an extraction artefact into the rule base.

    uv run python -m scripts.load_koonji koonji-bphs-vol1.jsonl --book bphs-gcsharma-vol1
    uv run python -m scripts.load_koonji koonji-bphs-vol1.json --dry-run

Accepts either the streaming JSONL checkpoint or the final JSON array, because a run
that was interrupted only has the former.
"""

import argparse
import asyncio
import json
import sys

from app.db.session import async_session_factory
from app.knowledge.compile.persist import load_rules

MAX_FAILURES_SHOWN = 30


def read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        if path.endswith(".jsonl"):
            return [json.loads(line) for line in handle if line.strip()]
        return json.load(handle)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="load extracted Koonji rules")
    parser.add_argument("path")
    parser.add_argument("--book", default="bphs-gcsharma-vol1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rows = read_rows(args.path)
    print(f"{len(rows)} extraction rows from {args.path}")

    async with async_session_factory() as session:
        report = await load_rules(session, rows=rows, book_slug=args.book)
        print(report.line())
        for failure in report.failures[:MAX_FAILURES_SHOWN]:
            print(f"  refused {failure}", file=sys.stderr)
        if len(report.failures) > MAX_FAILURES_SHOWN:
            print(f"  ... and {len(report.failures) - MAX_FAILURES_SHOWN} more",
                  file=sys.stderr)
        if args.dry_run:
            print("dry run: rolling back")
            await session.rollback()
        else:
            await session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 5: Run the tests, then a dry-run load**

```bash
.venv/bin/python -m pytest tests/knowledge/compile -v
PYTHONPATH=. .venv/bin/python -m scripts.load_koonji koonji-bphs-vol1.jsonl --dry-run
```

Expected: tests pass; the dry run prints a `rules=`/`atoms=`/`refused=` line where
`refused` is roughly 60% of rows (the declines) and rolls back.

- [ ] **Step 6: Commit**

```bash
git add app/knowledge/compile/persist.py scripts/load_koonji.py tests/knowledge/compile/test_persist.py
git commit -m "feat(compile): load extracted rules into rule + rule_atom idempotently"
```

---

### Task 4: The matcher

**Files:**
- Create: `app/knowledge/match/engine.py`
- Test: `tests/knowledge/match/test_engine.py`

**Interfaces:**
- Consumes: `chart_tokens` (Task 1); `Rule`, `RuleAtom`, `MATCHABLE_PREDICATE`.
- Produces:
  - `satisfies(condition: dict, tokens: dict) -> bool`
  - `MatchedRule` dataclass (`rule_key, condition, effects, source, matched_atoms`)
  - `async def match_chart(session, *, tokens: dict, limit: int = 40) -> list[MatchedRule]`

- [ ] **Step 1: Write the failing test**

```python
# tests/knowledge/match/test_engine.py
"""Exact condition evaluation. The prefilter narrows; this decides.

Every case here is drawn from a real extracted rule, because the failure that matters
is not a crash -- it is a rule that quietly matches the wrong chart.
"""

from app.knowledge.match.engine import satisfies

# Saturn in the 7th, the 7th lord in the 6th, the Moon in Cancer in the 4th.
CHART = {
    "planet.saturn.house": 7,
    "planet.moon.house": 4,
    "planet.moon.sign": "cancer",
    "planet.jupiter.house": 9,
    "house.7.lord.house": 6,
    "house.2.lord.house": 11,
    "house.7.occupant_count": 1,
    "house.8.occupant_count": 0,
}


def test_a_single_atom_matches():
    assert satisfies(
        {"atoms": [{"type": "planet_in_house", "planet": "saturn", "house": 7}]}, CHART
    )


def test_a_single_atom_that_does_not_hold():
    assert not satisfies(
        {"atoms": [{"type": "planet_in_house", "planet": "saturn", "house": 1}]}, CHART
    )


def test_a_set_form_matches_any_member():
    """BPHS 20.2: "the 7th lord in the 6th, 8th or 12th". The 7th lord is in the 6th."""
    assert satisfies(
        {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7,
                    "houses": [6, 8, 12]}]}, CHART
    )


def test_a_set_form_that_excludes_the_chart():
    assert not satisfies(
        {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7,
                    "houses": [1, 4, 10]}]}, CHART
    )


def test_combinator_all_requires_every_atom():
    condition = {
        "combinator": "all",
        "atoms": [
            {"type": "planet_in_house", "planet": "saturn", "house": 7},
            {"type": "planet_in_house", "planet": "jupiter", "house": 1},
        ],
    }
    assert not satisfies(condition, CHART)


def test_combinator_any_requires_one_atom():
    """BPHS 12.2 fanned Mercury/Jupiter/Venus into three `any` atoms."""
    condition = {
        "combinator": "any",
        "atoms": [
            {"type": "planet_in_house", "planet": "saturn", "house": 1},
            {"type": "planet_in_house", "planet": "jupiter", "house": 9},
        ],
    }
    assert satisfies(condition, CHART)


def test_missing_combinator_defaults_to_all():
    """The extractor omits it on single-atom conditions; defaulting to `any` would
    make every multi-atom rule far too permissive."""
    condition = {
        "atoms": [
            {"type": "planet_in_house", "planet": "saturn", "house": 7},
            {"type": "planet_in_house", "planet": "jupiter", "house": 1},
        ]
    }
    assert not satisfies(condition, CHART)


def test_none_blocks_a_match():
    """"unless Jupiter is in the 9th" -- and Jupiter is in the 9th."""
    condition = {
        "atoms": [{"type": "planet_in_house", "planet": "saturn", "house": 7}],
        "none": [{"type": "planet_in_house", "planet": "jupiter", "house": 9}],
    }
    assert not satisfies(condition, CHART)


def test_none_that_does_not_apply_leaves_the_match_standing():
    condition = {
        "atoms": [{"type": "planet_in_house", "planet": "saturn", "house": 7}],
        "none": [{"type": "planet_in_house", "planet": "jupiter", "house": 1}],
    }
    assert satisfies(condition, CHART)


def test_an_unknown_token_never_matches():
    """A rule referencing a token the chart cannot emit must return False, not raise
    and not pass. 16% of valid rules use dignity/conjunct/aspect, which the engine
    does not compute yet -- they must be inert, not exceptions."""
    condition = {"atoms": [{"type": "dignity_is", "planet": "mars",
                            "dignity": "exalted"}]}
    assert satisfies(condition, CHART) is False


def test_an_empty_condition_never_matches():
    """A conditionless rule would fire on every chart ever cast."""
    assert not satisfies({"atoms": []}, CHART)
    assert not satisfies({}, CHART)
    assert not satisfies(None, CHART)


def test_house_is_empty_reads_the_occupant_count():
    assert satisfies({"atoms": [{"type": "house_is_empty", "house": 8}]}, CHART)
    assert not satisfies({"atoms": [{"type": "house_is_empty", "house": 7}]}, CHART)


def test_string_comparison_is_case_insensitive_on_both_sides():
    """The extractor has emitted `sign: "Aries"` with a capital; the chart emits
    lowercase. Neither side should decide a match on casing."""
    assert satisfies(
        {"atoms": [{"type": "planet_in_sign", "planet": "moon", "sign": "Cancer"}]},
        CHART,
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/knowledge/match/test_engine.py -v`
Expected: FAIL — no module `app.knowledge.match.engine`

- [ ] **Step 3: Write the implementation**

```python
# app/knowledge/match/engine.py
"""Decide which rules a chart satisfies.

Two stages, for two different reasons. `rule_atom` gives SQL a cheap way to reduce
thousands of rules to a handful whose tokens the chart even mentions. `satisfies` then
evaluates the rule's `condition` JSONB exactly, because the atom table cannot express
a combinator, a negation or a set -- it was never meant to.

The rule that governs every branch below: **an unknown token never matches.** 16% of
valid extracted rules use `dignity_is`, `conjunct` or `aspected_by`, which the chart
engine does not compute. Those rules must be inert -- not exceptions, and above all not
passes. A missing fact is not a satisfied one.
"""

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.compile.atoms import _OBJECT_FIELD, atom_to_fact_token
from app.models.knowledge.rule import MATCHABLE_PREDICATE, Rule, RuleAtom

_SET_FORM = {"house": "houses", "sign": "signs"}


@dataclass
class MatchedRule:
    rule_key: str
    condition: dict
    effects: list[dict]
    source: dict
    life_domains: list[str] = field(default_factory=list)
    rishi_affinity: dict[str, float] = field(default_factory=dict)


def _asserted_values(atom: dict, object_field: str) -> list:
    plural = _SET_FORM.get(object_field)
    if plural and atom.get(plural):
        return list(atom[plural])
    value = atom.get(object_field)
    return [] if value is None else [value]


def _same(left, right) -> bool:
    """Compare a chart value with an asserted one, tolerating case and numeric strings.

    The extractor has emitted `sign: "Aries"` where the chart emits `"aries"`, and
    `target: "4"` where a house is an int. Neither should decide a match.
    """
    if isinstance(left, str) or isinstance(right, str):
        return str(left).strip().lower() == str(right).strip().lower()
    return left == right


def _atom_holds(atom: dict, tokens: dict) -> bool:
    object_field = _OBJECT_FIELD.get(atom.get("type"))
    if object_field is None:
        return False
    try:
        token = atom_to_fact_token(atom, scope=atom.get("scope") or "")
    except ValueError:
        # An incomplete or unknown atom cannot be shown to hold.
        return False
    if token not in tokens:
        return False
    actual = tokens[token]
    values = _asserted_values(atom, object_field)
    if not values:
        return False
    if atom.get("type") == "house_is_empty":
        return actual == 0
    return any(_same(actual, value) for value in values)


def satisfies(condition: dict | None, tokens: dict) -> bool:
    """Whether this chart satisfies this condition, exactly."""
    if not condition:
        return False
    atoms = condition.get("atoms") or []
    blocked = condition.get("none") or []
    if not atoms and not blocked:
        # A conditionless rule would fire on every chart ever cast.
        return False

    if atoms:
        combinator = (condition.get("combinator") or "all").lower()
        holds = (_atom_holds(atom, tokens) for atom in atoms)
        # Default to `all`: the extractor omits the combinator on single-atom
        # conditions, and defaulting to `any` would make every multi-atom rule
        # dramatically more permissive than the verse.
        if not (any(holds) if combinator == "any" else all(holds)):
            return False

    return not any(_atom_holds(atom, tokens) for atom in blocked)


async def match_chart(
    session: AsyncSession, *, tokens: dict, limit: int = 40
) -> list[MatchedRule]:
    """Approved rules this chart satisfies.

    The SQL stage uses `MATCHABLE_PREDICATE` verbatim -- the one definition of "may
    reach a user" -- so an unapproved rule cannot leak through a hand-written filter.
    """
    if not tokens:
        return []

    candidate_ids = (
        select(RuleAtom.rule_id)
        .join(Rule, Rule.id == RuleAtom.rule_id)
        .where(
            RuleAtom.fact_token.in_(list(tokens)),
            RuleAtom.negate.is_(False),
            text(MATCHABLE_PREDICATE.replace("status", "rule.status")),
        )
        .distinct()
    )
    rules = (
        await session.execute(select(Rule).where(Rule.id.in_(candidate_ids)))
    ).scalars()

    matched = []
    for rule in rules:
        if not satisfies(rule.condition, tokens):
            continue
        matched.append(
            MatchedRule(
                rule_key=rule.rule_key,
                condition=rule.condition or {},
                effects=(rule.effect or {}).get("effects") or [],
                source=rule.source or {},
                life_domains=rule.life_domains or [],
            )
        )
        if len(matched) >= limit:
            break
    return matched
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/knowledge/match -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add app/knowledge/match tests/knowledge/match
git commit -m "feat(match): evaluate rule conditions against chart fact tokens"
```

---

### Task 5: Score matched rules for the answering Rishi

**Files:**
- Modify: `rishivan/council/domains.py` (already holds `RISHI_LIFE_DOMAINS` and `rule_relevance`)
- Create: `tests/council/test_rishi_life_domains.py`

**Interfaces:**
- Consumes: `RISHI_LIFE_DOMAINS`, `rule_relevance`, `life_domains_for_rishi` (already written 2026-08-19).
- Produces: no new API; this task is the missing test suite plus the drift guard.

- [ ] **Step 1: Write the failing test**

```python
# tests/council/test_rishi_life_domains.py
"""The persona -> client life-domain mapping, and the drift guard it depends on.

The repo carries two different sets of eight Rishi names: the client's life domains
(`atma`..`dharma`, which the corpus is annotated with) and this repo's personas
(`agam`..`pragnav`, which answer users). They are different taxonomies under the same
count, so the mapping is weighted and many-to-many. If it breaks, rules stop reaching
the Rishi that should cite them -- and nothing raises.
"""

from app.models.knowledge.affinity import RISHI_KEYS, WEIGHT_HIGH
from rishivan.council.domains import (
    DOMAIN_HIGH,
    LIFE_DOMAIN_KEYS,
    RISHI_LIFE_DOMAINS,
    life_domains_for_rishi,
    rishis_for_life_domain,
    rule_relevance,
)
from rishivan.council.personas import ALL_RISHI_NAMES


def test_life_domain_keys_match_the_knowledge_layer_exactly():
    """The copy exists because importing the knowledge layer would pull SQLAlchemy onto
    the Streamlit request path. `vocab.py` warns what an unguarded copy costs."""
    assert LIFE_DOMAIN_KEYS == RISHI_KEYS


def test_weights_match_the_knowledge_layer():
    assert DOMAIN_HIGH == WEIGHT_HIGH


def test_every_persona_has_a_mapping():
    """A persona with no mapping retrieves no rules and degrades to page search
    without saying so."""
    assert set(RISHI_LIFE_DOMAINS) == set(ALL_RISHI_NAMES)


def test_every_client_domain_has_at_least_one_high_owner():
    """Eight Rishis doc §20: "No orphan questions." Yatra is the cell to watch -- no
    persona is really a movement/property specialist, so it is assigned deliberately
    rather than left empty."""
    for domain in LIFE_DOMAIN_KEYS:
        owners = [
            rishi
            for rishi, weights in RISHI_LIFE_DOMAINS.items()
            if weights.get(domain) == DOMAIN_HIGH
        ]
        assert owners, f"no persona owns {domain}"


def test_no_mapping_names_an_unknown_domain():
    for rishi, weights in RISHI_LIFE_DOMAINS.items():
        unknown = set(weights) - set(LIFE_DOMAIN_KEYS)
        assert not unknown, f"{rishi} maps unknown domains {unknown}"


def test_medhan_reaches_all_three_of_its_client_domains():
    """`medhan` is "relationships, family, health" -- one persona over three client
    Rishis. Dropping any of the three silently narrows what it can cite."""
    assert set(life_domains_for_rishi("medhan")) >= {"prema", "vansh", "aarogya"}


def test_dhruvan_reaches_wealth_career_and_property():
    assert set(life_domains_for_rishi("dhruvan")) >= {"artha", "karma", "yatra"}


def test_the_fallback_rishi_can_reach_everything():
    """`classifier.py` falls back to `vyom` for an unrecognised routing result. A
    fallback that reaches only part of the corpus turns a routing miss into a
    retrieval miss."""
    assert set(life_domains_for_rishi("vyom")) == set(LIFE_DOMAIN_KEYS)


def test_reverse_lookup_agrees_with_forward_lookup():
    for rishi in RISHI_LIFE_DOMAINS:
        for domain in life_domains_for_rishi(rishi):
            assert rishi in rishis_for_life_domain(domain)


def test_relevance_is_zero_without_an_affinity_vector():
    """Every rule extracted so far has an empty `rishi_affinity`. Scoring those as
    universally relevant would let any Rishi cite any rule."""
    assert rule_relevance("dhruvan", None) == 0.0
    assert rule_relevance("dhruvan", {}) == 0.0


def test_relevance_is_zero_for_an_unknown_persona():
    assert rule_relevance("not-a-rishi", {"artha": 1.0}) == 0.0


def test_relevance_prefers_the_strongest_single_agreement():
    """§12's master rule is to invoke the minimum set giving independent evidence, so a
    rule strongly about one relevant domain must outrank one weakly about several."""
    focused = rule_relevance("dhruvan", {"artha": 1.0})
    scattered = rule_relevance("dhruvan", {"artha": 0.3, "karma": 0.3, "yatra": 0.3})
    assert focused > scattered
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `.venv/bin/python -m pytest tests/council/test_rishi_life_domains.py -v`

Expected: mostly PASS, since `domains.py` was written on 2026-08-19. Any failure is a
real defect in that mapping — fix `domains.py`, not the test. Create
`tests/council/__init__.py` if pytest cannot collect the directory.

- [ ] **Step 3: Commit**

```bash
git add tests/council
git commit -m "test(council): pin the persona to client life-domain mapping"
```

---

### Task 6: Give the runtime access to the rule base

**This is the plan's one architectural decision and needs a human choice before coding.**

The answering runtime has no database: `grep -rl "async_session_factory|sqlalchemy|asyncpg" rishivan/ streamlit_app.py` returns nothing. Rules live in Postgres. Three options:

| Option | How | Cost |
|---|---|---|
| **A. Export artefact** (recommended) | `scripts/export_rules.py` writes approved rules + atoms to `data/rules-<book>.json`; runtime loads it at startup | No request-time DB, deterministic, versioned, works on Streamlit Cloud. Needs a re-export after each approval batch |
| **B. Direct DB** | Runtime opens a Postgres connection | Matches Blueprint §11's "structured SQL" literally. Adds a network dependency and credentials to the deployed app; `sqlalchemy`/`asyncpg` are already in `requirements.txt` |
| **C. Rules into Qdrant** | Store rule JSON as vector payload | Reuses existing infrastructure, but makes structural matching depend on a vector store, which Blueprint §1 explicitly warns against |

**Recommendation: A now, B for the production backend.** The demo needs no live rule editing, an export is trivially cacheable, and it keeps deterministic matching out of reach of a network failure. Blueprint §11's requirement is about *structured* retrieval rather than about which process holds the table.

**Files (option A):**
- Create: `scripts/export_rules.py`
- Create: `rishivan/rag/rules.py`
- Test: `tests/rag/test_rules.py`

**Interfaces:**
- Produces: `load_rule_pack(path: str) -> RulePack`; `RulePack.match(tokens: dict, *, rishi: str, limit: int) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
# tests/rag/test_rules.py
"""The runtime's read-only view of the rule base.

The runtime has no database, so approved rules ship as an export. These tests pin the
two properties that matter: only approved rules are in the pack, and matching in the
runtime agrees exactly with matching in the knowledge layer.
"""

import json

import pytest

from rishivan.rag.rules import RulePack, load_rule_pack

PACK = {
    "book_slug": "bphs-gcsharma-vol1",
    "exported_at": "2026-08-19T00:00:00Z",
    "rules": [
        {
            "rule_key": "bphs-gcsharma-vol1:20.2.1",
            "condition": {"atoms": [{"type": "lord_of_house_in_house",
                                     "lord_of": 7, "houses": [6, 8, 12]}]},
            "effects": [{"polarity": "negative", "strength": "moderate",
                         "statement": "the wife will be sickly"}],
            "source": {"book_slug": "bphs-gcsharma-vol1", "chapter": "20",
                       "verse_ref": "2", "translation": "In case the 7th Lord..."},
            "life_domains": ["marriage"],
            "rishi_affinity": {"prema": 1.0},
        }
    ],
}

CHART = {"house.7.lord.house": 6}


@pytest.fixture
def pack(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(PACK), encoding="utf-8")
    return load_rule_pack(str(path))


def test_a_matching_rule_is_returned_with_its_citation(pack):
    hits = pack.match(CHART, rishi="medhan", limit=10)
    assert len(hits) == 1
    assert hits[0]["source"]["chapter"] == "20"
    assert hits[0]["source"]["verse_ref"] == "2"


def test_a_rishi_with_no_affinity_for_the_rule_does_not_get_it(pack):
    """`dhruvan` covers wealth, career and property. A marriage rule is not its
    evidence, and letting it cite one is how a Rishi stops being a specialist."""
    assert pack.match(CHART, rishi="dhruvan", limit=10) == []


def test_the_fallback_rishi_gets_it(pack):
    """`vyom` maps to every domain at medium weight."""
    assert len(pack.match(CHART, rishi="vyom", limit=10)) == 1


def test_a_non_matching_chart_returns_nothing(pack):
    assert pack.match({"house.7.lord.house": 1}, rishi="medhan", limit=10) == []


def test_hits_are_ordered_by_relevance(tmp_path):
    pack_data = {
        **PACK,
        "rules": [
            {**PACK["rules"][0], "rule_key": "weak", "rishi_affinity": {"prema": 0.3}},
            {**PACK["rules"][0], "rule_key": "strong", "rishi_affinity": {"prema": 1.0}},
        ],
    }
    path = tmp_path / "p.json"
    path.write_text(json.dumps(pack_data), encoding="utf-8")
    hits = load_rule_pack(str(path)).match(CHART, rishi="medhan", limit=10)
    assert [hit["rule_key"] for hit in hits] == ["strong", "weak"]


def test_an_empty_pack_is_not_an_error(tmp_path):
    """Before the first export the pack does not exist, and the runtime must degrade to
    page retrieval rather than crash on a missing file."""
    assert load_rule_pack(str(tmp_path / "absent.json")).match(
        CHART, rishi="vyom", limit=5
    ) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/rag/test_rules.py -v`
Expected: FAIL — no module `rishivan.rag.rules`

- [ ] **Step 3: Write the runtime reader**

```python
# rishivan/rag/rules.py
"""The runtime's read-only view of the approved rule base.

The answering path has no database -- it is Qdrant plus Swiss Ephemeris -- so approved
rules travel as an export written by `scripts/export_rules.py`. That keeps deterministic
matching independent of a network round trip, and keeps Postgres credentials out of a
publicly deployed Streamlit app.

Matching here must agree exactly with `app.knowledge.match.engine.satisfies`, so this
module imports it rather than reimplementing it. A second evaluator would be a second
thing to drift, and a drifted evaluator produces confidently wrong readings.
"""

import json
from dataclasses import dataclass, field

from app.knowledge.match.engine import satisfies
from rishivan.council.domains import rule_relevance

MIN_RELEVANCE = 0.3
"""Below this a rule is not this Rishi's evidence. Matches DOMAIN_LOW: a persona may
reach adjacent material, but not material it has no stated relationship to."""


@dataclass
class RulePack:
    book_slug: str = ""
    exported_at: str = ""
    rules: list[dict] = field(default_factory=list)

    def match(self, tokens: dict, *, rishi: str, limit: int = 20) -> list[dict]:
        """Approved rules this chart satisfies that are relevant to this Rishi,
        strongest agreement first."""
        scored = []
        for rule in self.rules:
            relevance = rule_relevance(rishi, rule.get("rishi_affinity"))
            if relevance < MIN_RELEVANCE:
                continue
            if not satisfies(rule.get("condition"), tokens):
                continue
            scored.append((relevance, rule))
        scored.sort(key=lambda pair: -pair[0])
        return [rule for _, rule in scored[:limit]]


def load_rule_pack(path: str) -> RulePack:
    """Read an exported pack. A missing pack is empty, not an error: before the first
    export the runtime must degrade to page retrieval rather than fail."""
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return RulePack()
    return RulePack(
        book_slug=payload.get("book_slug", ""),
        exported_at=payload.get("exported_at", ""),
        rules=payload.get("rules") or [],
    )
```

- [ ] **Step 4: Write the exporter**

```python
# scripts/export_rules.py
"""Export approved rules for the runtime, which has no database.

    uv run python -m scripts.export_rules --book bphs-gcsharma-vol1 --out data/rules-bphs-vol1.json

Only rules satisfying `MATCHABLE_PREDICATE` are exported -- the one definition of "may
reach a user". Re-run after every approval batch; the export carries `exported_at` so a
stale pack is visible rather than assumed current.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, text

from app.db.session import async_session_factory
from app.models.knowledge.book import Book
from app.models.knowledge.rule import MATCHABLE_PREDICATE, Rule


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="export approved rules for the runtime")
    parser.add_argument("--book", default="bphs-gcsharma-vol1")
    parser.add_argument("--out", default="data/rules-bphs-vol1.json")
    args = parser.parse_args(argv)

    async with async_session_factory() as session:
        book = (
            await session.execute(select(Book).where(Book.slug == args.book))
        ).scalar_one()
        rules = (
            await session.execute(
                select(Rule).where(Rule.book_id == book.id, text(MATCHABLE_PREDICATE))
            )
        ).scalars()
        payload = {
            "book_slug": args.book,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "rules": [
                {
                    "rule_key": rule.rule_key,
                    "condition": rule.condition,
                    "effects": (rule.effect or {}).get("effects") or [],
                    "source": rule.source,
                    "life_domains": rule.life_domains,
                    "rishi_affinity": (rule.effect or {}).get("rishi_affinity") or {},
                }
                for rule in rules
            ],
        }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"exported {len(payload['rules'])} approved rules to {args.out}")
    if not payload["rules"]:
        print(
            "  no approved rules: loading sets approved_at=NULL by design, so a "
            "reviewer must approve before anything is exportable"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 5: Run the tests and commit**

```bash
.venv/bin/python -m pytest tests/rag/test_rules.py -v
git add rishivan/rag/rules.py scripts/export_rules.py tests/rag/test_rules.py
git commit -m "feat(rag): ship approved rules to the runtime as an export pack"
```

---

### Task 7: Rules first, pages as fallback

**Files:**
- Modify: `rishivan/rag/retrieve.py` (add `build_rule_context`, extend `build_answer_prompt`)
- Modify: `rishivan/council/orchestrator.py:352-404` (the retrieval block)
- Test: `tests/rag/test_rule_context.py`

**Interfaces:**
- Consumes: `RulePack.match` (Task 6), `chart_tokens` (Task 1).
- Produces: `build_rule_context(matched: list[dict]) -> str`; `build_answer_prompt(query, context_text, chart_facts=None, rule_context="")`

- [ ] **Step 1: Write the failing test**

```python
# tests/rag/test_rule_context.py
"""How matched rules reach the prompt.

Blueprint §18: the LLM "may explain structured conclusions" and "must not invent
citations" or "rewrite canonical rules silently". That makes the shape of this block a
correctness concern, not formatting -- it is the difference between the model reporting
a rule and improvising one.
"""

from rishivan.rag.retrieve import build_answer_prompt, build_rule_context

MATCHED = [
    {
        "rule_key": "bphs-gcsharma-vol1:20.2.1",
        "effects": [{"polarity": "negative", "strength": "moderate",
                     "statement": "the wife will be sickly"}],
        "source": {"chapter": "20", "verse_ref": "2",
                   "book_slug": "bphs-gcsharma-vol1",
                   "translation": "In case the 7th Lord is placed in the 6th, 8th or "
                                  "12th House and is not in his own sign..."},
    }
]


def test_context_carries_the_verse_reference():
    context = build_rule_context(MATCHED)
    assert "20.2" in context or "Chapter 20" in context
    assert "verse 2" in context.lower() or "20.2" in context


def test_context_quotes_the_translation_not_a_paraphrase():
    """The model must have the source text, or a citation is unverifiable."""
    assert "In case the 7th Lord is placed" in build_rule_context(MATCHED)


def test_context_states_the_effect_and_its_polarity():
    context = build_rule_context(MATCHED)
    assert "sickly" in context
    assert "negative" in context.lower()


def test_empty_match_yields_empty_context():
    assert build_rule_context([]) == ""


def test_prompt_tells_the_model_the_rules_are_authoritative():
    prompt = build_answer_prompt("will my wife be healthy?", "page text",
                                 rule_context=build_rule_context(MATCHED))
    lowered = prompt.lower()
    assert "matched" in lowered
    assert "do not invent" in lowered or "never" in lowered


def test_prompt_without_rules_is_unchanged_in_shape():
    """No matched rules must not degrade the existing page-only behaviour."""
    prompt = build_answer_prompt("q", "page text")
    assert "Sources:" in prompt
    assert "MATCHED KOONJI RULES" not in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/rag/test_rule_context.py -v`
Expected: FAIL — cannot import `build_rule_context`

- [ ] **Step 3: Add the context builder**

```python
# append to rishivan/rag/retrieve.py

def build_rule_context(matched: list[dict]) -> str:
    """Render matched Koonji rules for the prompt.

    Each entry carries the citation, the source translation and the stated effect, in
    that order. The translation is included deliberately: Blueprint §18 forbids the LLM
    from inventing citations, and a citation the model cannot see the text of is one it
    has to take on trust -- which is the same thing as inventing it.
    """
    if not matched:
        return ""
    blocks = []
    for index, rule in enumerate(matched, start=1):
        source = rule.get("source") or {}
        reference = f"{source.get('chapter', '?')}.{source.get('verse_ref', '?')}"
        effects = "; ".join(
            f"[{effect.get('polarity')}] {effect.get('statement')}"
            for effect in rule.get("effects") or []
        )
        blocks.append(
            f"RULE {index} — {source.get('book_slug', 'source')} chapter "
            f"{source.get('chapter', '?')}, verse {source.get('verse_ref', '?')} "
            f"({reference})\n"
            f"  The text says: \"{(source.get('translation') or '').strip()}\"\n"
            f"  Stated outcome: {effects or 'none recorded'}"
        )
    return "\n\n".join(blocks)


RULE_GUIDANCE = (
    "\n\nMATCHED KOONJI RULES — these were matched deterministically against the "
    "querent's actual chart by the rule engine, not retrieved by similarity. They are "
    "the authoritative basis for your answer.\n"
    "- Explain what these rules say and why they apply. Do NOT re-derive them, soften "
    "them, or add astrological reasoning of your own.\n"
    "- Cite each rule by its chapter and verse, e.g. \"(BPHS 20.2)\".\n"
    "- Do NOT invent a rule, a verse number, or a placement. If the matched rules do "
    "not answer the question, say so and rely on the source excerpts instead.\n"
    "- Never state a health diagnosis, a treatment, or death as a certainty. Present "
    "traditional interpretations as traditional, with their uncertainty intact.\n"
)
"""The LLM's job description, from Blueprint §18 and the Aarogya rule in Eight Rishis
§9. The last line is not boilerplate: BPHS states outcomes like "his death is quite
certain", and those rules are legitimately in the rule base while being forbidden to
present as certainty."""
```

- [ ] **Step 4: Extend `build_answer_prompt`**

Modify the existing function in `rishivan/rag/retrieve.py` — add the parameter and
splice the block in, leaving the page-only path byte-identical:

```python
def build_answer_prompt(
    query: str, context_text: str, chart_facts=None, rule_context: str = ""
) -> str:
    """Assemble the generation prompt (natural, cited, complete answers)."""
    facts_block = ""
    if chart_facts:
        facts_lines = "\n".join(f"- {f}" for f in chart_facts)
        facts_block = (
            "\n\nQUERENT'S CHART FACTS (ground truth — do NOT recompute or invent "
            f"placements; interpret these against the source text):\n{facts_lines}"
        )

    rules_block = f"{RULE_GUIDANCE}\n{rule_context}" if rule_context else ""

    guidance = (
        "You are a knowledgeable Vedic astrology scholar answering from classical "
        "texts.\n\n"
        "Answer the question directly and naturally, as an expert would, using ONLY "
        "the information in the source excerpts below.\n"
        "- Give a complete answer. If the answer is a list (e.g. names or values), "
        "provide the full list, not a partial one.\n"
        "- Cite the page number(s) you drew from, naturally in-line, "
        'e.g. "(Page 24)".\n'
        "- If the question was asked in Hindi or Hinglish, reply in the same language "
        "and script.\n"
        "- Only if the excerpts genuinely do not contain the answer, say so plainly in "
        "one sentence and stop — never speculate or invent verse numbers.\n"
    )
    return (
        f"{guidance}\nSources:\n{context_text}{rules_block}{facts_block}"
        f"\n\nQuestion: {query}\n"
    )
```

- [ ] **Step 5: Wire it into the orchestrator**

In `rishivan/council/orchestrator.py`, immediately after `chart_facts` is derived
(around line 157) and before retrieval (line 352):

```python
    # Rule matching runs alongside page retrieval, not instead of it. With ~650 rules
    # from one book most questions still match nothing, and a reading that silently
    # returned less because the rule base is thin would be a regression on the
    # page-search behaviour that exists today.
    matched_rules: list[dict] = []
    if birth_data is not None and chart is not None:
        from rishivan.chart.tokens import chart_tokens
        from rishivan.rag.rules import load_rule_pack

        pack = load_rule_pack(RULE_PACK_PATH)
        matched_rules = pack.match(
            chart_tokens(chart), rishi=result["primary_rishi"], limit=12
        )
    result["matched_rules"] = matched_rules
    result["rule_pack_exported_at"] = pack.exported_at if matched_rules else ""
```

and at the generation call, pass the block through:

```python
        rule_context = build_rule_context(matched_rules)
        prompt = build_answer_prompt(
            question, context_text, chart_facts=chart_facts, rule_context=rule_context
        )
```

Add near the top of the module:

```python
RULE_PACK_PATH = "data/rules-bphs-vol1.json"
"""Where the runtime reads approved rules. Absent until `scripts/export_rules.py` has
run, and absent means page retrieval only -- see `load_rule_pack`."""
```

- [ ] **Step 6: Run the full suite and commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add rishivan/rag/retrieve.py rishivan/council/orchestrator.py tests/rag/test_rule_context.py
git commit -m "feat(rag): prefer matched rules over page similarity, with pages as fallback"
```

---

### Task 8: Show the user which rules fired

**Files:**
- Modify: `streamlit_app.py` (the results section, near the existing `chart_summary` block at ~line 497)
- Test: manual, plus `tests/rag/test_rule_context.py` already covers the data shape

**Interfaces:**
- Consumes: `result["matched_rules"]`, `result["rule_pack_exported_at"]` (Task 7).

- [ ] **Step 1: Add the panel**

```python
    # ── Matched Koonji rules ──
    # Blueprint §21's gold standard: "If Rishivan cannot show how an important
    # conclusion travels from user question -> calculation -> rule -> source ->
    # validation -> final explanation, the engine is not finished." This panel is the
    # rule -> source link made visible to the person reading the answer.
    if result.get("matched_rules"):
        with st.expander(
            f"📜 {len(result['matched_rules'])} classical rules matched this chart",
            expanded=False,
        ):
            for rule in result["matched_rules"]:
                source = rule.get("source") or {}
                st.markdown(
                    f"**{source.get('book_slug', 'source')} "
                    f"{source.get('chapter', '?')}.{source.get('verse_ref', '?')}**"
                )
                st.caption((source.get("translation") or "").strip())
                for effect in rule.get("effects") or []:
                    st.markdown(
                        f"- _{effect.get('polarity')}_: {effect.get('statement')}"
                    )
            if result.get("rule_pack_exported_at"):
                st.caption(f"rule base exported {result['rule_pack_exported_at']}")
    elif result.get("chart_facts"):
        st.caption(
            "No classical rule in the current rule base matched this chart — this "
            "reading comes from source passages only."
        )
```

- [ ] **Step 2: Verify by hand**

```bash
.venv/bin/python -m streamlit run streamlit_app.py
```

Ask "will my wife be healthy?" with a birth chart whose 7th lord sits in the 6th, 8th
or 12th. Confirm the panel lists BPHS 20.2, that the quoted translation matches the
book, and that the answer cites it. Then ask a question no rule covers and confirm the
"source passages only" caption appears rather than silence.

- [ ] **Step 3: Commit**

```bash
git add streamlit_app.py
git commit -m "feat(ui): show which classical rules matched, with their source text"
```

---

### Task 9: Close the 16% — dignity, conjunction and aspect

The chart engine computes no dignity table, no conjunction orb and no aspect model, so
`dignity_is`, `conjunct` and `aspected_by` atoms can never match. Measured: **9 of 58
valid rules (16%)**.

**Files:**
- Create: `rishivan/chart/relations.py`
- Modify: `rishivan/chart/tokens.py` (merge relation tokens in)
- Test: `tests/chart/test_relations.py`

**Interfaces:**
- Consumes: `Chart`, `PlanetPosition`.
- Produces: `dignity_of(planet: str, sign: str) -> str | None`; `relation_tokens(chart: Chart, *, scope: str = "") -> dict[str, int | str | bool]`

- [ ] **Step 1: Write the failing test**

```python
# tests/chart/test_relations.py
"""Dignity, conjunction and aspect -- the three token families that block 16% of the
rule base.

Blueprint §7 is explicit that these are school-specific: "Drishti: School-specific
aspect rules; never assume one universal aspect model." So the model used is named in
the code and pinned here, rather than left implicit.
"""

import pytest

from rishivan.chart.relations import dignity_of, relation_tokens
from rishivan.chart.ephemeris import BirthData, compute_chart

INDIA = BirthData(
    year=1947, month=8, day=15, hour=0, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.mark.parametrize(
    "planet,sign,expected",
    [
        ("sun", "aries", "exalted"),
        ("sun", "libra", "debilitated"),
        ("sun", "leo", "own_sign"),
        ("moon", "taurus", "exalted"),
        ("mars", "capricorn", "exalted"),
        ("mars", "aries", "own_sign"),
        ("jupiter", "cancer", "exalted"),
        ("saturn", "libra", "exalted"),
        ("saturn", "aries", "debilitated"),
        ("venus", "pisces", "exalted"),
        ("mercury", "virgo", "own_sign"),
        ("sun", "gemini", None),
    ],
)
def test_classical_dignities(planet, sign, expected):
    """The Parashari exaltation/debilitation/own-sign table. `dignity_is` atoms are
    grounded against these words by the extractor's validator, so the spellings must
    match: exalted, debilitated, own_sign, moolatrikona."""
    assert dignity_of(planet, sign) == expected


def test_dignity_tokens_are_emitted_for_every_planet():
    tokens = relation_tokens(compute_chart(INDIA))
    for planet in ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn"):
        assert f"planet.{planet}.dignity" in tokens


def test_conjunction_is_same_house_and_symmetric():
    """Whole-sign conjunction: same rashi. Stated explicitly because an orb-based model
    would give different answers, and Blueprint §7 forbids assuming one silently."""
    tokens = relation_tokens(compute_chart(INDIA))
    pairs = [key for key in tokens if ".conjunct." in key]
    for key in pairs:
        _, left, _, right = key.split(".", 3)
        assert tokens[f"planet.{right}.conjunct.{left}"] == tokens[key]


def test_a_planet_is_not_conjunct_itself():
    tokens = relation_tokens(compute_chart(INDIA))
    assert not any(
        key == f"planet.{p}.conjunct.{p}"
        for p in ("sun", "moon", "mars")
        for key in [key for key in tokens if ".conjunct." in key]
    )


def test_aspect_tokens_cover_the_seventh_from_every_planet():
    """Parashari drishti: every planet aspects the 7th from itself. Mars, Jupiter and
    Saturn have their special aspects too."""
    tokens = relation_tokens(compute_chart(INDIA))
    assert any(key.startswith("planet.sun.aspects.") for key in tokens)


def test_mars_has_its_special_fourth_and_eighth_aspects():
    tokens = relation_tokens(compute_chart(INDIA))
    aspects = {
        int(key.rsplit(".", 1)[1])
        for key in tokens
        if key.startswith("planet.mars.aspects.") and key.rsplit(".", 1)[1].isdigit()
    }
    assert len(aspects) >= 3, "Mars aspects the 4th, 7th and 8th from itself"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/chart/test_relations.py -v`
Expected: FAIL — no module `rishivan.chart.relations`

- [ ] **Step 3: Write the implementation**

```python
# rishivan/chart/relations.py
"""Dignity, conjunction and aspect tokens -- the Parashari model, named explicitly.

Blueprint §7 requires this to be a stated choice rather than an assumption: "Drishti:
School-specific aspect rules; never assume one universal aspect model." So:

* **Dignity** is the classical exaltation / debilitation / own-sign / moolatrikona
  table. The spellings match `DIGNITY_SYNONYMS` in the extractor's validator, because
  those are the words the rules are grounded against.
* **Conjunction** is whole-sign: two planets in the same rashi. Not an orb. An orb
  model gives materially different answers, and BPHS is a whole-sign text.
* **Aspect** is Parashari drishti: every planet aspects the 7th house from itself;
  Mars additionally the 4th and 8th, Jupiter the 5th and 9th, Saturn the 3rd and 10th.

These three families block 9 of 58 valid extracted rules (16%). Until this module
existed those rules were inert -- `satisfies` returns False for an unknown token, which
is the correct degradation but is still 16% of the rule base unreachable.
"""

from rishivan.chart.ephemeris import Chart
from rishivan.chart.tokens import EPHEMERIS_PLANET_NAME, SIGN_TOKEN_NAME

EXALTATION: dict[str, str] = {
    "sun": "aries", "moon": "taurus", "mars": "capricorn", "mercury": "virgo",
    "jupiter": "cancer", "venus": "pisces", "saturn": "libra",
    "rahu": "taurus", "ketu": "scorpio",
}

DEBILITATION: dict[str, str] = {
    "sun": "libra", "moon": "scorpio", "mars": "cancer", "mercury": "pisces",
    "jupiter": "capricorn", "venus": "virgo", "saturn": "aries",
    "rahu": "scorpio", "ketu": "taurus",
}

OWN_SIGNS: dict[str, tuple[str, ...]] = {
    "sun": ("leo",), "moon": ("cancer",), "mars": ("aries", "scorpio"),
    "mercury": ("gemini", "virgo"), "jupiter": ("sagittarius", "pisces"),
    "venus": ("taurus", "libra"), "saturn": ("capricorn", "aquarius"),
}

MOOLATRIKONA: dict[str, str] = {
    "sun": "leo", "moon": "taurus", "mars": "aries", "mercury": "virgo",
    "jupiter": "sagittarius", "venus": "libra", "saturn": "aquarius",
}

SPECIAL_ASPECTS: dict[str, tuple[int, ...]] = {
    "mars": (4, 7, 8),
    "jupiter": (5, 7, 9),
    "saturn": (3, 7, 10),
}
"""Houses counted from the planet itself. Everything else aspects only the 7th."""

DEFAULT_ASPECTS: tuple[int, ...] = (7,)


def dignity_of(planet: str, sign: str) -> str | None:
    """The planet's dignity in this sign, or None if it is neutral.

    Exaltation outranks moolatrikona, which outranks own sign, because a rule saying
    "exalted" means exalted rather than merely well placed.
    """
    planet, sign = planet.lower(), sign.lower()
    if EXALTATION.get(planet) == sign:
        return "exalted"
    if DEBILITATION.get(planet) == sign:
        return "debilitated"
    if MOOLATRIKONA.get(planet) == sign:
        return "moolatrikona"
    if sign in OWN_SIGNS.get(planet, ()):
        return "own_sign"
    return None


def relation_tokens(chart: Chart, *, scope: str = "") -> dict[str, int | str | bool]:
    """Dignity, conjunction and aspect tokens for this chart."""
    positions = {
        EPHEMERIS_PLANET_NAME[name]: position
        for name, position in chart.planets.items()
        if name in EPHEMERIS_PLANET_NAME
    }
    tokens: dict[str, int | str | bool] = {}

    for planet, position in positions.items():
        sign = SIGN_TOKEN_NAME.get(position.rashi, position.rashi.lower())
        dignity = dignity_of(planet, sign)
        if dignity is not None:
            tokens[f"{scope}planet.{planet}.dignity"] = dignity

        for house_offset in SPECIAL_ASPECTS.get(planet, DEFAULT_ASPECTS):
            aspected = ((position.house - 1 + house_offset - 1) % 12) + 1
            tokens[f"{scope}planet.{planet}.aspects.{aspected}"] = True

    for planet, position in positions.items():
        for other, other_position in positions.items():
            if planet == other:
                continue
            if position.house == other_position.house:
                tokens[f"{scope}planet.{planet}.conjunct.{other}"] = True

    return tokens
```

- [ ] **Step 4: Merge into `chart_tokens`**

In `rishivan/chart/tokens.py`, at the end of `chart_tokens` before `return tokens`:

```python
    from rishivan.chart.relations import relation_tokens

    tokens.update(relation_tokens(chart, scope=scope))
```

and delete the paragraph in the module docstring that says dignity, conjunction and
aspect are deliberately absent — it is no longer true.

- [ ] **Step 5: Re-measure the unlocked rules**

```bash
.venv/bin/python -m pytest tests/chart -v
```

Then confirm the gap actually closed:

```bash
.venv/bin/python - <<'PY'
import json
from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.tokens import chart_tokens
from app.knowledge.match.engine import satisfies

tokens = chart_tokens(compute_chart(BirthData(
    year=1947, month=8, day=15, hour=0, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090)))
rules = [r for r in json.load(open("koonji-bphs-vol1.json")) if r["verdict"] == "VALID"]
MISSING = {"dignity_is", "conjunct", "aspected_by"}
affected = [
    r for r in rules
    if MISSING & {a.get("type") for a in
                  (r["rule"]["formation"].get("atoms") or [])
                  + (r["rule"]["formation"].get("none") or [])}
]
inert = [r for r in affected if not any(
    f"planet.{a.get('planet')}.dignity" in tokens or ".conjunct." in str(tokens)
    for a in r["rule"]["formation"].get("atoms") or [])]
print(f"{len(affected)} rules use dignity/conjunct/aspect; {len(inert)} still inert")
PY
```

Expected: `still inert` is 0. Any remainder is a token-spelling mismatch between
`relations.py` and the compiler — fix the spelling, never the test.

- [ ] **Step 6: Commit**

```bash
git add rishivan/chart/relations.py rishivan/chart/tokens.py tests/chart/test_relations.py
git commit -m "feat(chart): emit dignity, conjunction and aspect tokens (Parashari)"
```

---

## Out of scope — separate plans

Named so nobody assumes they are covered here:

1. **Rule review and approval UI.** Nothing is exportable until a human sets
   `approved_at`, and today that requires hand-written SQL. This is the gate between
   this pipeline and any real user, so it is the highest-priority follow-on.
2. **The `rishi_affinity` enrichment pass.** Every extracted rule has an empty vector,
   which means `rule_relevance` returns 0 and — by Task 6's `MIN_RELEVANCE` — no rule
   reaches any Rishi. **Task 6 and 7 are inert until this exists.** It belongs in its
   own plan because it is derived from the rule's content rather than the verse, so it
   is re-runnable without re-reading the book.
3. **The knowledge graph** (Blueprint §10, §11). The third retrieval system.
4. **The validation lab** (Blueprint §15): backtest, blind test, temporal holdout,
   calibration, ablation, adversarial, expert review, regression suite.
5. **Edition profiles** for books beyond BPHS. Measured: BPHS's chapter detector finds
   0 headings in Phaladeepika, Brihat Jataka, Jataka Parijata, Prasna Marga and Dharma
   Sindhu, because they print `ADHYAYA 1.`, `Adhyaya 1.`, `CHAPTER VI.` and `CHAPTER I`
   (Roman numerals). Three config fields per edition, not a module per book.
6. **Benefic/malefic in the vocabulary.** 51% of extraction declines. The largest single
   lever on rule yield, and a change to the fact engine rather than to this pipeline.

## Self-Review

**Spec coverage.** Blueprint §1 (no PDF→embeddings→prediction) — Tasks 2/4 make
retrieval structural. §6 (Koonji format) — Task 3 persists CONDITIONS, MODIFIERS,
TIMING, EXCEPTIONS, RESULT, SOURCE, VERSION; `CONCEPTS` and `SCHOOL` are extraction-side
gaps noted for the affinity plan. §8 rule 2 (promise vs timing) — Task 2 refuses timing
atoms in a formation. §11 (three retrieval systems) — vector + SQL delivered, graph
listed out of scope. §18 (LLM's job) — Task 7's `RULE_GUIDANCE`. §19 (answer contract) —
partially: Task 8 surfaces chart facts, rules and sources, but not cross-school
agreement or validation level, which need the validation lab. Eight Rishis §9 (Aarogya
forbidden claims) — Task 7's guidance, last line. §12 (multi-Rishi) — Task 5's mapping;
invoking several Rishis per question is orchestrator work not covered here. §15 (weighted
matrix) — Task 5 plus the affinity plan. §20 (no orphan domains) — Task 5 test.

**Placeholder scan.** No TBDs. Every code step carries real code. Task 6 contains a
decision table rather than an instruction, which is deliberate: it needs a human choice,
and the recommended option's code is written out in full.

**Type consistency.** `chart_tokens(chart, *, scope="") -> dict[str, int | str]` is
produced in Task 1 and consumed in Tasks 4, 6, 7, 9. `CompiledAtom` field names match
`RuleAtom` columns exactly (`condition_type, subject, object_int, object_str,
from_reference, varga, negate, fact_token`). `satisfies(condition, tokens)` is defined
in Task 4 and reused verbatim by Task 6 rather than reimplemented. `_OBJECT_FIELD` is
defined in Task 2 and imported by Task 4 — a private name crossing a module boundary,
which is intentional so the two cannot disagree about which field carries the value;
Task 4's implementer should rename it to `OBJECT_FIELD` in both files if the import
reads badly. `EPHEMERIS_PLANET_NAME` and `SIGN_TOKEN_NAME` are defined in Task 1 and
imported by Task 9.

**One risk to flag before starting.** Tasks 6–8 produce visible behaviour only after the
`rishi_affinity` enrichment pass exists, because `MIN_RELEVANCE` filters out every rule
with an empty vector. Either build the affinity pass before Task 6, or temporarily set
`MIN_RELEVANCE = 0.0` and treat rule relevance as unfiltered — but not silently: it
would let any Rishi cite any rule, which is exactly the specialisation the client's
whole design rests on.
