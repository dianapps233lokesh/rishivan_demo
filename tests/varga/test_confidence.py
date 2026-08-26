"""How much of a recorded birth time is actually known.

`BirthData` records hour/minute/second and says nothing about precision, so this
infers it from how *round* the recorded time is. `4:37:00` was read off
something; `12:00` and `4:30` were almost certainly rounded to the nearest
convenient number.

The inference is a heuristic and is labelled one. The override is authoritative,
and is what a rectified chart uses.
"""

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.varga.confidence import (
    ASCENDANT_DEGREES_PER_HOUR,
    BirthConfidence,
    arc_uncertainty_degrees,
    infer_confidence,
    min_confidence_for_arc,
)


def birth(hour=12, minute=0, second=0) -> BirthData:
    return BirthData(year=1990, month=1, day=1, hour=hour, minute=minute,
                     second=second, tz_offset_hours=5.5, lat=28.6139, lon=77.2090)


class TestInference:
    def test_seconds_recorded_means_exact(self):
        assert infer_confidence(birth(4, 37, 12)) is BirthConfidence.EXACT

    def test_an_odd_minute_means_minute_precision(self):
        """Nobody rounds to 4:37."""
        assert infer_confidence(birth(4, 37)) is BirthConfidence.MINUTE

    def test_a_quarter_hour_is_treated_as_rounded(self):
        for minute in (15, 30, 45):
            assert infer_confidence(birth(4, minute)) is BirthConfidence.QUARTER

    def test_on_the_hour_is_the_roundest_of_all(self):
        assert infer_confidence(birth(4, 0)) is BirthConfidence.HOUR

    def test_midnight_exactly_is_unknown(self):
        """00:00 is what a form defaults to when nobody entered anything, and
        treating it as a real time is how a D60 reading gets built on a blank
        field."""
        assert infer_confidence(birth(0, 0)) is BirthConfidence.UNKNOWN

    def test_noon_exactly_is_only_hour_precision_not_unknown(self):
        """Noon is a real convention for an unknown time, but it is also a real
        birth time. Hour precision is the honest middle."""
        assert infer_confidence(birth(12, 0)) is BirthConfidence.HOUR

    def test_five_minute_marks_are_rounded_too(self):
        assert infer_confidence(birth(4, 5)) is BirthConfidence.QUARTER
        assert infer_confidence(birth(4, 20)) is BirthConfidence.QUARTER


class TestOrdering:
    def test_confidence_increases_with_precision(self):
        assert (BirthConfidence.UNKNOWN < BirthConfidence.HOUR
                < BirthConfidence.QUARTER < BirthConfidence.MINUTE
                < BirthConfidence.EXACT)

    def test_it_compares_as_an_integer(self):
        """The gate is `actual >= required`, so ordering has to be real."""
        assert BirthConfidence.MINUTE >= BirthConfidence.QUARTER


class TestArcUncertainty:
    def test_the_ascendant_moves_about_fifteen_degrees_an_hour(self):
        assert ASCENDANT_DEGREES_PER_HOUR == pytest.approx(15.0)

    def test_hour_uncertainty_is_about_seven_degrees(self):
        """Half an hour either way, at 15 degrees an hour."""
        assert arc_uncertainty_degrees(BirthConfidence.HOUR) == pytest.approx(7.5)

    def test_quarter_uncertainty_is_about_four_degrees(self):
        assert arc_uncertainty_degrees(BirthConfidence.QUARTER) == pytest.approx(3.75)

    def test_minute_uncertainty_is_a_quarter_degree(self):
        assert arc_uncertainty_degrees(BirthConfidence.MINUTE) == pytest.approx(0.25)

    def test_uncertainty_falls_as_confidence_rises(self):
        arcs = [arc_uncertainty_degrees(c) for c in BirthConfidence]
        assert arcs == sorted(arcs, reverse=True)

    def test_an_unknown_time_is_uncertain_by_half_a_day(self):
        """Noon assumed against a real birth anywhere in the day."""
        assert arc_uncertainty_degrees(BirthConfidence.UNKNOWN) >= 90.0


class TestTheGate:
    """The arithmetic that decides which vargas may speak."""

    def test_even_d1_needs_a_known_hour(self):
        """The finding the arithmetic forced, and it is worth stating plainly.

        An UNKNOWN time is half a day of uncertainty — about 180 degrees of
        ascendant, so the lagna could be any of the twelve signs. Nothing
        house-based survives that, D1 included. What does survive is the
        sign-level layer: planets in rashis, dispositors, conjunctions, every
        graha but the Moon barely moving in a day.

        So the blueprint's "D1 always primary" is a statement about the
        *sign* layer, and the house layer needs at least an hour."""
        assert min_confidence_for_arc(30.0) is BirthConfidence.HOUR
        assert arc_uncertainty_degrees(BirthConfidence.UNKNOWN) > 30.0

    def test_d9_needs_at_least_quarter_precision(self):
        """3 degrees 20 minutes per division."""
        assert min_confidence_for_arc(360 / 9 / 12) >= BirthConfidence.QUARTER

    def test_d60_needs_minute_precision(self):
        """Half a degree per division. At hour precision the ascendant moves
        7.5 degrees — fifteen divisions of noise."""
        assert min_confidence_for_arc(0.5) >= BirthConfidence.MINUTE

    def test_a_finer_division_never_needs_less_confidence(self):
        arcs = [30.0, 10.0, 3.33, 1.0, 0.5]
        needed = [min_confidence_for_arc(a) for a in arcs]
        assert needed == sorted(needed)

    def test_the_gate_is_arithmetic_not_a_lookup(self):
        """A varga this codebase has never heard of still gets a correct answer,
        which is what makes the policy table maintainable."""
        assert min_confidence_for_arc(360 / 81 / 12) >= BirthConfidence.MINUTE


class TestOverride:
    def test_an_explicit_confidence_wins(self):
        """A rectified chart knows its precision better than any heuristic over
        the digits can."""
        from rishivan.varga.confidence import resolve_confidence

        assert resolve_confidence(birth(12, 0), BirthConfidence.EXACT) is (
            BirthConfidence.EXACT
        )

    def test_no_override_falls_back_to_inference(self):
        from rishivan.varga.confidence import resolve_confidence

        assert resolve_confidence(birth(4, 37), None) is BirthConfidence.MINUTE

    def test_no_birth_data_is_unknown(self):
        from rishivan.varga.confidence import resolve_confidence

        assert resolve_confidence(None, None) is BirthConfidence.UNKNOWN
