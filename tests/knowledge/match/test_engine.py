"""Exact condition evaluation. The prefilter narrows; this decides.

Every case is drawn from a real extracted rule, because the failure that matters is not a
crash -- it is a rule that quietly matches the wrong chart, which no error surfaces and
no count reveals.
"""

from app.knowledge.match.engine import satisfies

# Saturn in the 7th, the 7th lord in the 6th, the Moon in Cancer in the 4th, the 8th
# house empty. A hand-written chart rather than a computed one, so each assertion below
# states its own premise.
CHART = {
    "planet.saturn.house": 7,
    "planet.moon.house": 4,
    "planet.moon.sign": "cancer",
    "planet.jupiter.house": 9,
    "house.7.lord.house": 6,
    "house.2.lord.house": 11,
    "house.7.occupant_count": 1,
    "house.8.occupant_count": 0,
    "from_sun.planet.moon.house": 4,
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
        {
            "atoms": [
                {"type": "lord_of_house_in_house", "lord_of": 7, "houses": [6, 8, 12]}
            ]
        },
        CHART,
    )


def test_a_set_form_that_excludes_the_chart():
    assert not satisfies(
        {
            "atoms": [
                {"type": "lord_of_house_in_house", "lord_of": 7, "houses": [1, 4, 10]}
            ]
        },
        CHART,
    )


def test_combinator_all_requires_every_atom():
    assert not satisfies(
        {
            "combinator": "all",
            "atoms": [
                {"type": "planet_in_house", "planet": "saturn", "house": 7},
                {"type": "planet_in_house", "planet": "jupiter", "house": 1},
            ],
        },
        CHART,
    )


def test_combinator_any_requires_only_one_atom():
    """BPHS 12.2 fanned Mercury, Jupiter and Venus into three `any` atoms."""
    assert satisfies(
        {
            "combinator": "any",
            "atoms": [
                {"type": "planet_in_house", "planet": "saturn", "house": 1},
                {"type": "planet_in_house", "planet": "jupiter", "house": 9},
            ],
        },
        CHART,
    )


def test_a_missing_combinator_defaults_to_all():
    """The extractor omits it on single-atom conditions, where the two are equivalent.
    Defaulting to `any` would silently widen every multi-atom rule in the base."""
    assert not satisfies(
        {
            "atoms": [
                {"type": "planet_in_house", "planet": "saturn", "house": 7},
                {"type": "planet_in_house", "planet": "jupiter", "house": 1},
            ]
        },
        CHART,
    )


def test_none_blocks_a_match():
    """"unless Jupiter is in the 9th" -- and Jupiter is in the 9th."""
    assert not satisfies(
        {
            "atoms": [{"type": "planet_in_house", "planet": "saturn", "house": 7}],
            "none": [{"type": "planet_in_house", "planet": "jupiter", "house": 9}],
        },
        CHART,
    )


def test_none_that_does_not_apply_leaves_the_match_standing():
    assert satisfies(
        {
            "atoms": [{"type": "planet_in_house", "planet": "saturn", "house": 7}],
            "none": [{"type": "planet_in_house", "planet": "jupiter", "house": 1}],
        },
        CHART,
    )


def test_an_unknown_token_never_matches():
    """9 of vol 1's 376 valid rules use dignity/conjunct/aspect, which the chart engine
    does not compute. They must be inert -- not exceptions, and above all not passes."""
    assert (
        satisfies(
            {"atoms": [{"type": "dignity_is", "planet": "mars", "dignity": "exalted"}]},
            CHART,
        )
        is False
    )


def test_a_malformed_atom_never_matches_and_never_raises():
    """22 rules loaded as `unparsed` carry atoms like `conjunct{planet: "7th lord"}`.
    Reachable in production, so it must degrade rather than explode."""
    assert not satisfies(
        {"atoms": [{"type": "conjunct", "planet": "7th lord", "other": "venus"}]}, CHART
    )
    assert not satisfies({"atoms": [{"type": "not_a_real_type"}]}, CHART)


def test_an_empty_condition_never_matches():
    """A conditionless rule would fire on every chart ever cast."""
    assert not satisfies({"atoms": []}, CHART)
    assert not satisfies({}, CHART)
    assert not satisfies(None, CHART)


def test_house_is_empty_reads_the_occupant_count():
    assert satisfies({"atoms": [{"type": "house_is_empty", "house": 8}]}, CHART)
    assert not satisfies({"atoms": [{"type": "house_is_empty", "house": 7}]}, CHART)


def test_string_comparison_ignores_casing_on_both_sides():
    """The extractor has emitted `sign: "Aries"` with a capital while the chart emits
    lowercase. Neither side should decide a match on casing."""
    assert satisfies(
        {"atoms": [{"type": "planet_in_sign", "planet": "moon", "sign": "Cancer"}]},
        CHART,
    )


def test_a_scoped_atom_reads_the_scoped_token():
    """15 of the loaded atoms are `from_sun.`, and reading the lagna token instead would
    answer a different question with the same confidence."""
    assert satisfies(
        {
            "atoms": [
                {
                    "type": "planet_in_house",
                    "planet": "moon",
                    "houses": [1, 4, 7, 10],
                    "scope": "from_sun.",
                }
            ]
        },
        CHART,
    )


def test_a_scoped_atom_does_not_fall_back_to_the_unscoped_token():
    chart_without_scope = {"planet.moon.house": 4}
    assert not satisfies(
        {
            "atoms": [
                {
                    "type": "planet_in_house",
                    "planet": "moon",
                    "house": 4,
                    "scope": "from_sun.",
                }
            ]
        },
        chart_without_scope,
    )


def test_match_chart_sql_actually_executes():
    """`MATCHABLE_PREDICATE` is raw SQL over unqualified column names, and `rule` and
    `rule_atom` both have a `deleted_at`. Joining them made the predicate ambiguous and
    Postgres rejected the whole query -- a failure no unit test over `satisfies` could
    have caught, because the defect was in the statement rather than the logic.
    """
    from app.knowledge.match.engine import match_chart
    from tests.conftest import run_db, skip_without_database

    matched = None
    try:
        matched = run_db(lambda session: match_chart(session, tokens=CHART))
    except Exception as exc:  # noqa: BLE001
        skip_without_database(exc)
    # Nothing is approved yet, so the only correct answer is an empty list. The point of
    # the test is that the statement runs at all.
    assert matched == []
