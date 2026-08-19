"""Rule condition JSON -> the denormalized atoms SQL prefilters on.

`vocab.py:94` states the requirement this file satisfies: "P2's rule compiler must
derive `atom_to_fact_token`" from the vocabulary rather than hand-writing token strings.

Every fixture is a real condition from the BPHS vol 1 whole-book run, because the
failure that matters here is not a crash -- it is a token spelled one character
differently from what the chart emits, which raises nothing and matches nothing.
"""

import pytest

from app.astro.vocab import CONDITION_TOKEN_TEMPLATES
from app.knowledge.compile.atoms import atom_to_fact_token, compile_condition


def test_planet_in_house_token():
    assert (
        atom_to_fact_token({"type": "planet_in_house", "planet": "saturn", "house": 7})
        == "planet.saturn.house"
    )


def test_lord_of_house_in_house_token_uses_lord_of_not_house():
    """The most common atom in the corpus -- 204 of chapter 26's rules alone. The
    template is `house.{house}.lord.house`, and the number belongs to `lord_of` (whose
    lord) rather than `house` (where it sits). Swapping them yields a valid-looking
    token for entirely the wrong house."""
    assert (
        atom_to_fact_token({"type": "lord_of_house_in_house", "lord_of": 8, "house": 1})
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


def test_an_unemitted_scope_is_refused():
    with pytest.raises(ValueError, match="not emitted"):
        atom_to_fact_token(
            {"type": "planet_in_house", "planet": "moon", "house": 4}, scope="d40."
        )


def test_every_condition_type_in_the_vocabulary_can_be_tokenised():
    """A type the compiler cannot tokenise is a whole rule family that silently never
    matches, so coverage of the vocabulary must be exhaustive."""
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
        "sample set has drifted from the vocabulary lock"
    )
    for condition_type, arguments in samples.items():
        token = atom_to_fact_token({"type": condition_type, **arguments})
        assert token, condition_type
        assert "{" not in token, f"{condition_type} left a placeholder: {token}"


def test_a_set_form_compiles_to_one_atom_per_value():
    """`rule_atom` has a scalar `object_int` and no set column, so BPHS 20.2's "the 7th
    lord in the 6th, 8th or 12th" becomes three rows sharing a rule. They are a
    PREFILTER: the disjunction lives in `Rule.condition` and is evaluated there."""
    atoms = compile_condition(
        {
            "atoms": [
                {"type": "lord_of_house_in_house", "lord_of": 7, "houses": [6, 8, 12]}
            ]
        }
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
    assert {a.subject: a.negate for a in atoms} == {"saturn": False, "jupiter": True}


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
    """Blueprint §8 rule 2. A dasha compiled into a formation lets timing manufacture a
    natal promise, which the client states as an absolute."""
    with pytest.raises(ValueError, match="timing"):
        compile_condition(
            {"atoms": [{"type": "dasha_of", "planet": "saturn", "level": "maha"}]}
        )


def test_an_incomplete_atom_is_refused_rather_than_compiled():
    """`validate_rule` should have caught this upstream. Compiling it anyway would put a
    half-atom in the prefilter, matching charts the verse never described."""
    with pytest.raises(ValueError, match="missing"):
        compile_condition({"atoms": [{"type": "lord_of_house_in_house", "lord_of": 5}]})


def test_varga_scope_becomes_the_varga_column():
    atoms = compile_condition(
        {
            "atoms": [
                {
                    "type": "planet_in_house",
                    "planet": "venus",
                    "house": 7,
                    "scope": "d9.",
                }
            ]
        }
    )
    assert atoms[0].varga == "D9"
    assert atoms[0].fact_token == "d9.planet.venus.house"


def test_a_reference_frame_scope_becomes_from_reference():
    atoms = compile_condition(
        {
            "atoms": [
                {
                    "type": "planet_in_house",
                    "planet": "venus",
                    "house": 7,
                    "scope": "from_moon.",
                }
            ]
        }
    )
    assert atoms[0].from_reference == "from_moon"
    assert atoms[0].varga == "D1"


def test_the_real_chapter_26_condition_compiles():
    """From the whole-book run: BPHS 26.1, the Ascendant lord in the Ascendant."""
    atoms = compile_condition(
        {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 1, "house": 1}]}
    )
    assert len(atoms) == 1
    assert atoms[0].fact_token == "house.1.lord.house"
    assert atoms[0].object_int == 1
    assert atoms[0].subject == "1"


def test_house_is_empty_set_form_produces_one_token_per_house():
    """The only type whose subject and object are the same field, so each value names a
    different token. Found by compiling the whole book: this was the 1 shape of 376 that
    would not compile."""
    atoms = compile_condition(
        {"atoms": [{"type": "house_is_empty", "houses": [3, 6]}]}
    )
    assert len(atoms) == 2
    assert {a.fact_token for a in atoms} == {
        "house.3.occupant_count",
        "house.6.occupant_count",
    }
    assert {a.subject for a in atoms} == {"house:3", "house:6"}


def test_house_is_empty_scalar_form_still_works():
    atoms = compile_condition({"atoms": [{"type": "house_is_empty", "house": 3}]})
    assert len(atoms) == 1
    assert atoms[0].fact_token == "house.3.occupant_count"
