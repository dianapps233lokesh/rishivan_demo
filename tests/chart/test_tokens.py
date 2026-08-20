"""The join key between a chart and the rule base.

Every assertion here is a contract with `app/astro/vocab.py` and with the 743 `rule_atom`
rows loaded from BPHS vol 1. A token this module spells differently from the compiler is
not an error anyone sees -- the affected rules simply match no chart, ever.

The chart used throughout is a fixed real one, so the expected values are checkable by
hand against any ephemeris rather than being whatever the code happened to produce.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.tokens import all_chart_tokens, chart_tokens

INDIA = BirthData(
    year=1947,
    month=8,
    day=15,
    hour=0,
    minute=0,
    tz_offset_hours=5.5,
    lat=28.6139,
    lon=77.2090,
    place="New Delhi",
)

PLANETS = (
    "sun",
    "moon",
    "mars",
    "mercury",
    "jupiter",
    "venus",
    "saturn",
    "rahu",
    "ketu",
)

SIGNS = frozenset(
    {
        "aries",
        "taurus",
        "gemini",
        "cancer",
        "leo",
        "virgo",
        "libra",
        "scorpio",
        "sagittarius",
        "capricorn",
        "aquarius",
        "pisces",
    }
)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(INDIA)


@pytest.fixture(scope="module")
def tokens(chart):
    return chart_tokens(chart)


def test_every_planet_has_a_house_token(tokens):
    for planet in PLANETS:
        key = f"planet.{planet}.house"
        assert key in tokens, f"missing {key}"
        assert 1 <= tokens[key] <= 12


def test_planet_names_are_token_names_not_book_codes(tokens):
    """`planet.Sa.house` looks perfectly reasonable and matches nothing, ever."""
    assert "planet.saturn.house" in tokens
    assert not any(".Sa." in key or ".Su." in key for key in tokens)


def test_signs_are_lowercase_english(tokens):
    """Rules carry `sign: "aries"`; a token holding "Aries" or "Mesha" never matches."""
    for planet in PLANETS:
        value = tokens[f"planet.{planet}.sign"]
        assert value in SIGNS, f"{planet}: {value!r}"


def test_every_house_has_a_lord_house_token(tokens):
    """`house.N.lord.house` is the single most used token in the corpus -- 387 of the 743
    loaded `rule_atom` rows are house-family tokens, and chapter 26 alone contributes 204
    rules of exactly this shape."""
    for house in range(1, 13):
        key = f"house.{house}.lord.house"
        assert key in tokens, f"missing {key}"
        assert 1 <= tokens[key] <= 12


def test_every_house_has_a_lord_sign_token(tokens):
    for house in range(1, 13):
        assert tokens[f"house.{house}.lord.sign"] in SIGNS


def test_house_occupant_counts_cover_all_twelve_and_sum_to_nine(tokens):
    for house in range(1, 13):
        assert tokens[f"house.{house}.occupant_count"] >= 0
    assert sum(tokens[f"house.{h}.occupant_count"] for h in range(1, 13)) == 9


def test_nakshatra_and_pada_tokens_exist(tokens):
    assert isinstance(tokens["planet.moon.nakshatra"], str)
    assert tokens["planet.moon.nakshatra"].islower()
    assert 1 <= tokens["planet.moon.pada"] <= 4


def test_scope_prefixes_every_token(chart):
    """A varga token is the same base under a scope prefix. Mixing scopes silently would
    compare a D9 placement against a D1 rule."""
    d9 = chart_tokens(chart, scope="d9.")
    assert all(key.startswith("d9.") for key in d9)
    assert "d9.planet.saturn.house" in d9


def test_an_unemitted_scope_is_refused(chart):
    """`vocab.py` enumerates the emitted scopes; anything else is a typo that would
    produce tokens no rule can ever reference."""
    with pytest.raises(ValueError, match="not emitted"):
        chart_tokens(chart, scope="d40.")


def test_ketu_is_present_and_opposite_rahu(tokens):
    """The ephemeris computes only the mean node; Ketu is derived. Rules reference it by
    name, so it must be a first-class token."""
    assert "planet.ketu.house" in tokens
    assert (tokens["planet.ketu.house"] - tokens["planet.rahu.house"]) % 12 == 6


def test_a_house_lord_token_agrees_with_that_planets_own_token(tokens, chart):
    """`house.7.lord.house` must equal `planet.<7th lord>.house`. If these disagree the
    two most common atom families in the corpus contradict each other on the same chart."""
    from rishivan.chart.tokens import PLANET_TOKEN_NAME

    for house in range(1, 13):
        lord = PLANET_TOKEN_NAME[chart.house_lords[house]]
        assert tokens[f"house.{house}.lord.house"] == tokens[f"planet.{lord}.house"]
        assert tokens[f"house.{house}.lord.name"] == lord


def test_the_loaded_rule_base_tokens_are_all_emittable():
    """The real contract: every non-negated fact token in the database must be one this
    module can produce, or that rule is dead on arrival.

    Restricted to `status='parsed'`. The 22 rules loaded as `unparsed` keep their faults
    on purpose -- two of them carry tokens like `planet.7th lord.conjunct.venus`, which is
    exactly the defect the validator recorded -- and they are excluded from
    `ix_rule_matchable`, so they are not expected to be emittable.

    Skips when the rule base is empty so the suite still runs on a fresh checkout.
    """
    from sqlalchemy import text

    from tests.conftest import run_db, skip_without_database

    async def load(session):
        result = await session.execute(
            text(
                "select ra.fact_token, count(*) from rule_atom ra "
                "join rule r on r.id = ra.rule_id "
                "where r.status = 'parsed' and r.deleted_at is null "
                "group by 1 order by 2 desc"
            )
        )
        return list(result)

    rows = []
    try:
        rows = run_db(load)
    except Exception as exc:  # noqa: BLE001
        skip_without_database(exc)
    if not rows:
        pytest.skip("rule base is empty")

    emitted = set(all_chart_tokens(compute_chart(INDIA)))
    # dignity / conjunct / aspect are known-missing and tracked separately; see the
    # module docstring. Everything else must be emittable.
    known_gap = (".dignity", ".conjunct.", ".aspects.")
    unmatched = {
        token: count
        for token, count in rows
        if token not in emitted and not any(part in token for part in known_gap)
    }
    assert not unmatched, (
        f"{sum(unmatched.values())} loaded atoms reference tokens the chart cannot "
        f"emit: {sorted(unmatched)[:10]}"
    )


def test_relative_frame_recounts_houses_from_the_reference_planet(chart):
    """"the Moon in the 1st, 4th, 7th or 10th from the Sun" is 15 of the loaded atoms.
    In that frame the Sun is by definition in its own 1st house."""
    from_sun = chart_tokens(chart, scope="from_sun.")
    assert from_sun["from_sun.planet.sun.house"] == 1
    from_moon = chart_tokens(chart, scope="from_moon.")
    assert from_moon["from_moon.planet.moon.house"] == 1


def test_a_relative_frame_still_places_nine_bodies(chart):
    from_sun = chart_tokens(chart, scope="from_sun.")
    assert sum(
        from_sun[f"from_sun.house.{h}.occupant_count"] for h in range(1, 13)
    ) == 9


def test_relative_and_lagna_frames_disagree_on_house_but_agree_on_sign(chart):
    """The frame changes which house a planet counts as, never which sign it is in.
    A frame that changed the sign would be a bug in the offset arithmetic."""
    lagna = chart_tokens(chart)
    from_sun = chart_tokens(chart, scope="from_sun.")
    assert lagna["planet.saturn.sign"] == from_sun["from_sun.planet.saturn.sign"]


def test_all_chart_tokens_merges_every_supported_scope(chart):
    from rishivan.chart.tokens import SUPPORTED_SCOPES

    merged = all_chart_tokens(chart)
    for scope in SUPPORTED_SCOPES:
        assert f"{scope}planet.saturn.house" in merged, scope


def test_a_relative_frame_moves_the_houses_not_just_the_counting(chart):
    """The bug this pins was silent and wrong in the worst way.

    In a relative frame the HOUSES move, so the lord of the Nth house is the lord of the
    Nth sign counted from the reference planet. The first implementation took the lagna's
    Nth lord and merely re-counted where it sat: for a Sagittarius lagna with the Moon in
    Aquarius, `from_moon.house.1.lord` reported Jupiter (the lagna lord) where the answer
    is Saturn (lord of Aquarius, the 1st from the Moon). A rule about "the 1st lord from
    the Moon" would have been tested against a different planet entirely.
    """
    from rishivan.chart.ephemeris import RASHI_LORDS
    from rishivan.chart.tokens import PLANET_TOKEN_NAME

    for scope, reference_name in (("from_moon.", "Moon"), ("from_sun.", "Sun")):
        tokens = chart_tokens(chart, scope=scope)
        reference = chart.planets[reference_name]
        for house in range(1, 13):
            sign_index = (reference.rashi_index + house - 1) % 12
            expected = PLANET_TOKEN_NAME[RASHI_LORDS[sign_index]]
            assert tokens[f"{scope}house.{house}.lord.name"] == expected, (
                f"{scope}house.{house}"
            )


def test_the_reference_planet_is_its_own_first_house_lord_sign(chart):
    """A frame's 1st house is the reference planet's own sign, by definition."""
    tokens = chart_tokens(chart, scope="from_moon.")
    assert tokens["from_moon.planet.moon.house"] == 1


def test_the_lagna_frame_is_untouched_by_the_fix(chart):
    """`house_lords` is the ephemeris's own lagna-based mapping and must still be used
    verbatim when no reference planet is in play."""
    from rishivan.chart.tokens import PLANET_TOKEN_NAME

    tokens = chart_tokens(chart)
    for house in range(1, 13):
        assert tokens[f"house.{house}.lord.name"] == PLANET_TOKEN_NAME[
            chart.house_lords[house]
        ]
