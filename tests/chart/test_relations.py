"""Dignity, conjunction and aspect -- the three token families that blocked 16% of the
rule base.

Blueprint §7: "Drishti: School-specific aspect rules; never assume one universal aspect
model." The model is therefore pinned here, not just implemented.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.relations import dignity_of, relation_tokens

INDIA = BirthData(
    year=1947, month=8, day=15, hour=0, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(INDIA)


@pytest.fixture(scope="module")
def tokens(chart):
    return relation_tokens(chart)


@pytest.mark.parametrize(
    "planet,sign,expected",
    [
        ("sun", "aries", "exalted"),
        ("sun", "libra", "debilitated"),
        ("sun", "leo", "moolatrikona"),
        ("moon", "taurus", "exalted"),
        ("mars", "capricorn", "exalted"),
        ("mars", "cancer", "debilitated"),
        ("mars", "scorpio", "own_sign"),
        ("mercury", "virgo", "exalted"),
        ("jupiter", "cancer", "exalted"),
        ("jupiter", "pisces", "own_sign"),
        ("venus", "pisces", "exalted"),
        ("venus", "virgo", "debilitated"),
        ("saturn", "libra", "exalted"),
        ("saturn", "aries", "debilitated"),
        ("saturn", "capricorn", "own_sign"),
        ("sun", "gemini", None),
        ("rahu", "gemini", None),
    ],
)
def test_the_classical_dignity_table(planet, sign, expected):
    """`dignity_is` atoms were grounded by the extractor against these exact words --
    exalted, debilitated, moolatrikona, own_sign -- so the spellings are a contract."""
    assert dignity_of(planet, sign) == expected


def test_exaltation_outranks_ownership():
    """Mercury owns Virgo and is also exalted there. A rule saying "exalted" means
    exalted, so the more specific label has to win."""
    assert dignity_of("mercury", "virgo") == "exalted"


def test_conjunction_is_whole_sign_and_symmetric(tokens):
    """Not an orb: BPHS is a whole-sign text and an orb model answers differently."""
    pairs = [key for key in tokens if ".conjunct." in key]
    assert pairs, "this chart should have at least one conjunction"
    for key in pairs:
        _, left, _, right = key.split(".", 3)
        assert tokens.get(f"planet.{right}.conjunct.{left}") is True, key


def test_no_planet_is_conjunct_itself(tokens):
    for key in tokens:
        if ".conjunct." not in key:
            continue
        _, left, _, right = key.split(".", 3)
        assert left != right


def test_every_planet_aspects_the_seventh_from_itself(chart, tokens):
    from rishivan.chart.tokens import PLANET_TOKEN_NAME

    for display, position in chart.planets.items():
        planet = PLANET_TOKEN_NAME[display]
        seventh = ((position.house - 1 + 6) % 12) + 1
        assert tokens.get(f"planet.{planet}.aspects.{seventh}") is True, planet


def test_mars_jupiter_and_saturn_have_their_special_aspects(chart, tokens):
    from rishivan.chart.tokens import PLANET_TOKEN_NAME

    expected = {"mars": (4, 7, 8), "jupiter": (5, 7, 9), "saturn": (3, 7, 10)}
    reverse = {v: k for k, v in PLANET_TOKEN_NAME.items()}
    for planet, offsets in expected.items():
        house = chart.planets[reverse[planet]].house
        for offset in offsets:
            aspected = ((house - 1 + offset - 1) % 12) + 1
            assert tokens.get(f"planet.{planet}.aspects.{aspected}") is True


def test_an_aspect_on_a_planet_is_emitted_as_well_as_on_a_house(tokens):
    """Verses say both "the 4th aspected by Jupiter" and "Venus aspected by Saturn", so
    both target forms must resolve."""
    planet_targets = [
        key
        for key in tokens
        if ".aspects." in key and not key.rsplit(".", 1)[1].isdigit()
    ]
    assert planet_targets, "no planet-target aspect tokens emitted"


def test_relations_are_merged_into_chart_tokens(chart):
    """The 9 rules using these types read them from `chart_tokens`, not from here."""
    from rishivan.chart.tokens import all_chart_tokens

    merged = all_chart_tokens(chart)
    assert any(key.endswith(".dignity") for key in merged)
    assert any(".conjunct." in key for key in merged)
    assert any(".aspects." in key for key in merged)
