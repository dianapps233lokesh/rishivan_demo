"""Dasha fact tokens -- the timing half of the join key.

Blueprint §8 rule 2 separates potential from timing, and `astro/vocab.py` has always
declared `dasha_of -> dasha.{level}.lord`. Nothing emitted it: 636 activation atoms
across the corpus addressed a token family the chart never produced, so every "when"
question fell back to the natal promise with no way to say whether it was running.

Unlike every other token family this one is a function of a MOMENT as well as a chart,
which is why `all_chart_tokens` takes `when`.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.tokens import all_chart_tokens, dasha_tokens

INDIA = BirthData(
    year=1947, month=8, day=15, hour=0, minute=0, tz_offset_hours=5.5,
    lat=28.6139, lon=77.2090, place="New Delhi",
)

DASHA_LEVELS = ("maha", "antar", "pratyantar", "sookshma", "prana")


@pytest.fixture
def chart():
    return compute_chart(INDIA)


def test_every_dasha_level_the_corpus_cites_is_emitted(chart):
    """The corpus cites all five: 217 maha, 277 antar, 51 pratyantar, 56 sookshma,
    36 prana. `current_periods` stopped at pratyantar, so the last two matched
    nothing."""
    tokens = dasha_tokens(chart, datetime(2026, 8, 21))
    for level in DASHA_LEVELS:
        assert f"dasha.{level}.lord" in tokens, level


def test_a_dasha_lord_is_a_planet_name_not_a_level(chart):
    """The token holds the LORD. `OBJECT_FIELD` had `dasha_of -> level`, which made
    `_atom_holds` compare this planet name against the string "maha"."""
    tokens = dasha_tokens(chart, datetime(2026, 8, 21))
    assert tokens["dasha.maha.lord"] in {
        "sun", "moon", "mars", "mercury", "jupiter",
        "venus", "saturn", "rahu", "ketu",
    }


def test_dasha_tokens_are_lowercase_like_every_other_token(chart):
    """`Period.lord` is title-case ("Saturn") and the rule vocabulary is lowercase.
    An exact comparison across that difference matches nothing."""
    tokens = dasha_tokens(chart, datetime(2026, 8, 21))
    for level in DASHA_LEVELS:
        value = tokens[f"dasha.{level}.lord"]
        assert value == value.lower(), f"{level} -> {value!r}"


def test_the_running_period_changes_with_the_moment(chart):
    """The whole point of a timing token. If these agreed, `when` was ignored and every
    timing rule would be evaluated against one frozen instant."""
    early = dasha_tokens(chart, datetime(1950, 1, 1))
    late = dasha_tokens(chart, datetime(2026, 8, 21))
    assert early["dasha.maha.lord"] != late["dasha.maha.lord"]


def test_all_chart_tokens_carries_the_dasha_family(chart):
    """`all_chart_tokens` is documented as what the matcher consumes, and its docstring
    warns that a caller merging by hand can forget a scope. Dasha must not be the scope
    everyone forgets."""
    merged = all_chart_tokens(chart, when=datetime(2026, 8, 21))
    assert merged["dasha.maha.lord"] == dasha_tokens(
        chart, datetime(2026, 8, 21)
    )["dasha.maha.lord"]
    # the natal families must survive the merge
    assert "planet.saturn.house" in merged
    assert "house.7.lord.house" in merged


def test_all_chart_tokens_still_works_without_a_moment(chart):
    """Existing callers pass a chart alone. They must keep working -- and still get
    dasha tokens, defaulted to now, rather than silently losing timing."""
    merged = all_chart_tokens(chart)
    assert "dasha.maha.lord" in merged


def test_a_moment_before_birth_emits_no_dasha_tokens(chart):
    """No period is running, and an absent token is the honest answer. `_atom_holds`
    treats a missing token as unmatched, so this degrades to "cannot say" rather than
    to a false activation."""
    tokens = dasha_tokens(chart, datetime(1900, 1, 1))
    assert "dasha.maha.lord" not in tokens
