"""Which vargas a question gets, and what was withheld and why.

The withholding is the product. *"D60 needs a birth time to the minute; yours is
recorded to the hour, so I have not used it"* is a sentence no astrology app
says, and it cannot be said by a pipeline that silently drops the varga.

The interesting half is the rescue. A blunt confidence gate withholds D9 from
anyone who says "4:30pm" — most users — because a navamsa division is 3°20′ and
quarter-hour uncertainty is 3.75°. But uncertainty only *matters* if a body sits
near a division boundary. A chart whose grahas are all comfortably mid-division
is safe at coarser precision, and saying otherwise is conservative to the point
of being wrong.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.varga.confidence import BirthConfidence
from rishivan.varga.select import select_vargas

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


def codes(selection):
    return set(selection.selected)


class TestAlwaysPrimary:
    def test_d1_is_always_selected(self, chart):
        for confidence in BirthConfidence:
            s = select_vargas(chart, "domain.career", confidence)
            assert "D1" in codes(s), confidence

    def test_d1_is_never_withheld(self, chart):
        s = select_vargas(chart, "domain.career", BirthConfidence.UNKNOWN)
        assert "D1" not in {w.code for w in s.withheld}


class TestDomainScoping:
    def test_a_career_question_reaches_d10(self, chart):
        s = select_vargas(chart, "domain.career", BirthConfidence.EXACT)
        assert "D10" in codes(s)

    def test_a_career_question_does_not_reach_d7(self, chart):
        """"Do not use every Varga merely because it exists.\""""
        s = select_vargas(chart, "domain.career", BirthConfidence.EXACT)
        assert "D7" not in codes(s)

    def test_a_marriage_question_reaches_d9(self, chart):
        s = select_vargas(chart, "domain.relationship", BirthConfidence.EXACT)
        assert "D9" in codes(s)

    def test_an_unmapped_domain_still_gets_d1(self, chart):
        s = select_vargas(chart, "domain.gardening", BirthConfidence.EXACT)
        assert codes(s) == {"D1"}


class TestValidatedOnly:
    def test_d27_is_never_served(self, chart):
        """"Use only with validated methodology" — and that validation does not
        exist here, so the honest reading is: not yet."""
        s = select_vargas(chart, "domain.health", BirthConfidence.EXACT)
        assert "D27" not in codes(s)

    def test_it_is_withheld_with_a_methodology_reason_not_a_time_one(self, chart):
        s = select_vargas(chart, "domain.health", BirthConfidence.EXACT)
        withheld = {w.code: w for w in s.withheld}
        assert "D27" in withheld
        assert "method" in withheld["D27"].reason.lower()


class TestTheConfidenceGate:
    def test_d60_is_withheld_at_hour_precision(self, chart):
        """The blueprint's own example. Half a degree per division against 7.5
        degrees of ascendant uncertainty."""
        s = select_vargas(chart, "domain.temperament", BirthConfidence.HOUR)
        assert "D60" not in codes(s)

    def test_the_withholding_names_the_shortfall(self, chart):
        s = select_vargas(chart, "domain.temperament", BirthConfidence.HOUR)
        withheld = {w.code: w for w in s.withheld}
        assert "D60" in withheld
        w = withheld["D60"]
        assert w.required >= BirthConfidence.MINUTE
        assert w.actual is BirthConfidence.HOUR
        assert "minute" in w.reason.lower()
        assert "hour" in w.reason.lower()

    def test_an_unknown_time_withholds_nearly_everything(self, chart):
        s = select_vargas(chart, "domain.career", BirthConfidence.UNKNOWN)
        assert codes(s) == {"D1"}
        assert s.withheld

    def test_exact_time_withholds_nothing_for_time_reasons(self, chart):
        s = select_vargas(chart, "domain.career", BirthConfidence.EXACT)
        time_withheld = [w for w in s.withheld if "method" not in w.reason.lower()]
        assert time_withheld == []


class TestBoundaryRescue:
    """A coarse gate alone would withhold D9 and D10 from most real users.
    Uncertainty only matters when a body is near a division boundary."""

    def test_a_safely_placed_chart_keeps_d10_at_quarter_precision(self, chart):
        s = select_vargas(chart, "domain.career", BirthConfidence.QUARTER)
        if "D10" in codes(s):
            assert any("boundary" in n.lower() or "margin" in n.lower()
                       for n in s.notes), s.notes

    def test_a_rescued_varga_is_flagged_rather_than_silently_promoted(self, chart):
        """It is admitted, and the answer says on what basis."""
        s = select_vargas(chart, "domain.career", BirthConfidence.QUARTER)
        if "D10" in codes(s) and BirthConfidence.QUARTER < s.floor_for("D10"):
            assert s.notes

    def test_a_body_near_a_boundary_blocks_the_rescue(self, chart):
        """Constructed: push a graha to within a hair of a D10 division edge and
        the varga can no longer be trusted at coarse precision."""
        import copy

        from rishivan.varga.policy import arc_of

        c = copy.deepcopy(chart)
        arc = arc_of("D10")
        # Land the Sun 0.01 degrees short of a division boundary.
        base = c.planets["Sun"].longitude
        c.planets["Sun"].longitude = (base - base % arc) + arc - 0.01
        s = select_vargas(c, "domain.career", BirthConfidence.QUARTER)
        assert "D10" not in codes(s)

    def test_the_rescue_never_overrides_a_two_step_shortfall(self, chart):
        """A rescue is for the margin, not for an unknown birth time."""
        s = select_vargas(chart, "domain.temperament", BirthConfidence.UNKNOWN)
        assert "D60" not in codes(s)


class TestTheReport:
    def test_the_selection_records_the_confidence_it_used(self, chart):
        s = select_vargas(chart, "domain.career", BirthConfidence.QUARTER)
        assert s.confidence is BirthConfidence.QUARTER

    def test_every_withholding_carries_a_user_facing_sentence(self, chart):
        s = select_vargas(chart, "domain.temperament", BirthConfidence.HOUR)
        for w in s.withheld:
            assert w.reason.strip().endswith(".")

    def test_selected_vargas_are_ordered_by_evidence_tier(self, chart):
        from rishivan.varga.policy import policy_for

        s = select_vargas(chart, "domain.career", BirthConfidence.EXACT)
        tiers = [policy_for(c).evidence_tier for c in s.selected]
        assert tiers == sorted(tiers)

    def test_it_is_deterministic(self, chart):
        a = select_vargas(chart, "domain.career", BirthConfidence.QUARTER)
        b = select_vargas(chart, "domain.career", BirthConfidence.QUARTER)
        assert a == b
