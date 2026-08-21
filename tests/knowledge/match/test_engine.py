"""Exact condition evaluation. The prefilter narrows; this decides.

Every case is drawn from a real extracted rule, because the failure that matters is not a
crash -- it is a rule that quietly matches the wrong chart, which no error surfaces and
no count reveals.
"""

from rishivan.knowledge.match.engine import _atom_holds, satisfies

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
    from rishivan.knowledge.match.engine import match_chart
    from tests.conftest import run_db, skip_without_database

    matched = None
    try:
        matched = run_db(lambda session: match_chart(session, tokens=CHART))
    except Exception as exc:  # noqa: BLE001
        skip_without_database(exc)

    # The assertion is the invariant, not the count. An earlier version asserted `== []`
    # because nothing was approved yet, and it broke the moment a chapter was approved --
    # a test that encoded a temporary state rather than a rule.
    assert isinstance(matched, list)
    for rule in matched:
        assert satisfies(rule.condition, CHART), rule.rule_key
        assert rule.effects, f"{rule.rule_key} matched but predicts nothing"


def test_match_chart_returns_only_approved_rules():
    """`MATCHABLE_PREDICATE` is the one definition of "may reach a user", and the matcher
    must not be the place it gets re-expressed loosely."""
    from sqlalchemy import select

    from rishivan.knowledge.match.engine import match_chart
    from rishivan.models.knowledge.rule import Rule
    from tests.conftest import run_db, skip_without_database

    async def load(session):
        matched = await match_chart(session, tokens=CHART)
        keys = [rule.rule_key for rule in matched]
        if not keys:
            return []
        rows = await session.execute(
            select(Rule.rule_key, Rule.status, Rule.approved_at).where(
                Rule.rule_key.in_(keys)
            )
        )
        return list(rows)

    rows = []
    try:
        rows = run_db(load)
    except Exception as exc:  # noqa: BLE001
        skip_without_database(exc)

    for key, status, approved_at in rows:
        assert status == "parsed", key
        assert approved_at is not None, f"{key} was matched without being approved"


# --- Exceptions and cancelling modifiers -------------------------------------
#
# A rule that fires where the book cancels it is worse than a rule that never fires: it
# asserts something the source explicitly denies. Worked Example 1 of the extraction
# prompt exists to capture BPHS 8.1's commentary exception, and the matcher ignored it
# until now.

EIGHTH_LORD_IN_LAGNA = {
    "condition": {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 8,
                             "house": 1}]},
    "exceptions": [
        {
            "statement": "not in Aries or Libra ascendants, where Mars and Venus become "
            "the 8th lord and their moolatrikona is the Ascendant",
            "from_commentary": True,
            "condition": {"atoms": [{"type": "lord_of_house_in_sign", "lord_of": 1,
                                     "signs": ["aries", "libra"]}]},
        }
    ],
}

LAGNA_IN_ARIES = {"house.8.lord.house": 1, "house.1.lord.sign": "aries"}
LAGNA_IN_CANCER = {"house.8.lord.house": 1, "house.1.lord.sign": "cancer"}


def test_the_condition_holds_in_both_charts():
    from rishivan.knowledge.match.engine import satisfies as sat

    assert sat(EIGHTH_LORD_IN_LAGNA["condition"], LAGNA_IN_ARIES)
    assert sat(EIGHTH_LORD_IN_LAGNA["condition"], LAGNA_IN_CANCER)


def test_an_exception_that_holds_blocks_the_rule():
    from rishivan.knowledge.match.engine import applies, blockers

    reasons = blockers(EIGHTH_LORD_IN_LAGNA, LAGNA_IN_ARIES)
    assert reasons and "Aries" in reasons[0]
    assert applies(EIGHTH_LORD_IN_LAGNA, LAGNA_IN_ARIES) is False


def test_an_exception_that_does_not_hold_leaves_the_rule_standing():
    from rishivan.knowledge.match.engine import applies, blockers

    assert blockers(EIGHTH_LORD_IN_LAGNA, LAGNA_IN_CANCER) == []
    assert applies(EIGHTH_LORD_IN_LAGNA, LAGNA_IN_CANCER) is True


def test_a_cancelling_modifier_blocks_the_rule():
    """`cancel` is how Neecha Bhanga is expressed -- a debilitation undone."""
    from rishivan.knowledge.match.engine import applies

    rule = {
        "condition": {"atoms": [{"type": "planet_in_house", "planet": "saturn",
                                 "house": 7}]},
        "modifiers": [
            {"kind": "cancel", "statement": "cancelled when Jupiter aspects",
             "condition": {"atoms": [{"type": "planet_in_house", "planet": "jupiter",
                                      "house": 9}]}}
        ],
    }
    assert applies(rule, CHART) is False


def test_strengthen_and_weaken_do_not_block():
    """They colour how strongly the effect is stated, and belong in the answer rather
    than in the match."""
    from rishivan.knowledge.match.engine import applies

    for kind in ("strengthen", "weaken"):
        rule = {
            "condition": {"atoms": [{"type": "planet_in_house", "planet": "saturn",
                                     "house": 7}]},
            "modifiers": [
                {"kind": kind,
                 "condition": {"atoms": [{"type": "planet_in_house",
                                          "planet": "jupiter", "house": 9}]}}
            ],
        }
        assert applies(rule, CHART) is True, kind


def test_a_rule_with_no_exceptions_is_unaffected():
    from rishivan.knowledge.match.engine import blockers

    assert blockers({"condition": {}, "exceptions": [], "modifiers": []}, CHART) == []
    assert blockers({}, CHART) == []


# ── Timing atoms (Blueprint §8 rule 2) ───────────────────────────────────────


def test_a_dasha_atom_holds_when_that_lord_is_running():
    """`OBJECT_FIELD` mapped `dasha_of` to `level`, so `_atom_holds` fetched
    `dasha.maha.lord` -- a planet name -- and compared it against the string "maha".
    Every dasha atom in the corpus was therefore false, and once the tokens existed it
    would have stayed false with nothing to show why."""
    tokens = {"dasha.maha.lord": "saturn"}
    atom = {"type": "dasha_of", "planet": "saturn", "level": "maha"}
    assert _atom_holds(atom, tokens) is True


def test_a_dasha_atom_fails_when_a_different_lord_is_running():
    tokens = {"dasha.maha.lord": "jupiter"}
    atom = {"type": "dasha_of", "planet": "saturn", "level": "maha"}
    assert _atom_holds(atom, tokens) is False


def test_a_dasha_atom_reads_the_level_it_names():
    """The level addresses the token. Saturn's ANTAR dasha running is not Saturn's
    MAHA dasha running, and conflating them activates a rule years early."""
    tokens = {"dasha.maha.lord": "jupiter", "dasha.antar.lord": "saturn"}
    assert _atom_holds(
        {"type": "dasha_of", "planet": "saturn", "level": "antar"}, tokens
    ) is True
    assert _atom_holds(
        {"type": "dasha_of", "planet": "saturn", "level": "maha"}, tokens
    ) is False


def test_a_dasha_atom_with_no_planet_never_holds():
    """11 corpus atoms name a level and no planet -- "in the mahadasha" with the lord
    left to the verse's own subject. Unresolvable here, and an unknown token must never
    read as agreement."""
    tokens = {"dasha.maha.lord": "saturn"}
    assert _atom_holds({"type": "dasha_of", "level": "maha"}, tokens) is False


def test_a_dasha_atom_never_holds_on_a_chart_with_no_dasha_tokens():
    """A natal-only token set. Before the tokens existed this was every call."""
    assert _atom_holds(
        {"type": "dasha_of", "planet": "saturn", "level": "maha"},
        {"planet.saturn.house": 7},
    ) is False


def test_activation_factors_are_evaluated_by_satisfies_unchanged():
    """`timing.activation_factors` carries the same {atoms, combinator} shape as a
    condition, so the exact evaluator already covers it -- no second matcher, and no
    second place for the semantics to drift."""
    tokens = {"dasha.maha.lord": "saturn", "dasha.antar.lord": "mercury"}
    activation = {
        "combinator": "all",
        "atoms": [
            {"type": "dasha_of", "planet": "saturn", "level": "maha"},
            {"type": "dasha_of", "planet": "mercury", "level": "antar"},
        ],
    }
    assert satisfies(activation, tokens) is True

    activation["atoms"][1]["planet"] = "venus"
    assert satisfies(activation, tokens) is False


def test_an_any_combinator_activation_needs_only_one_period():
    """11 corpus activations use `any` -- "in the dasha of the 7th lord or the 2nd"."""
    tokens = {"dasha.maha.lord": "saturn"}
    activation = {
        "combinator": "any",
        "atoms": [
            {"type": "dasha_of", "planet": "saturn", "level": "maha"},
            {"type": "dasha_of", "planet": "venus", "level": "maha"},
        ],
    }
    assert satisfies(activation, tokens) is True
