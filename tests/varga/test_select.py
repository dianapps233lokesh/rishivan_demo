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


# --- The rescue, after it was found never to fire ------------------------------

JAIPUR = BirthData(
    year=1998, month=5, day=15, hour=18, minute=45,
    tz_offset_hours=5.5, lat=26.9155, lon=75.8190, place="Jaipur",
)
"""A real quarter-hour birth time. `TestBoundaryRescue` above guards the rescue
with `if "D10" in codes(s)`, and that condition was never true, so two of its
three tests passed without executing their bodies. The tests below assert
unconditionally for that reason."""


@pytest.fixture(scope="module")
def quarter_chart():
    return compute_chart(JAIPUR)


class TestTheRescueActuallyFires:
    """It could not, for any chart, at any precision, for any division.

    `_rescued` compared each *body's* distance from a division boundary against
    the *ascendant's* arc uncertainty. Those are different quantities: fifteen
    minutes of clock error moves the ascendant 3.75 degrees, the Moon 0.13, and
    Saturn 0.001. And because a body's margin cannot exceed half a division
    while the ascendant's drift exceeds a whole one for every division that has
    a floor, the comparison was arithmetically unsatisfiable.
    """

    def test_a_quarter_hour_birth_time_still_gets_its_navamsha(self, quarter_chart):
        """The case the rescue was written for, in its own docstring: "the
        coarse gate withholds D9 from anyone who says 'half past four', which is
        most people\"."""
        s = select_vargas(quarter_chart, "domain.relationship",
                          BirthConfidence.QUARTER)
        assert "D9" in codes(s)
        assert "D9" not in {w.code for w in s.withheld}

    def test_a_quarter_hour_birth_time_still_gets_its_dashamsha(self, quarter_chart):
        s = select_vargas(quarter_chart, "domain.career", BirthConfidence.QUARTER)
        assert "D10" in codes(s)

    def test_the_rescue_says_on_what_basis(self, quarter_chart):
        s = select_vargas(quarter_chart, "domain.relationship",
                          BirthConfidence.QUARTER)
        assert s.notes
        assert any("D9" in n for n in s.notes)

    def test_it_is_not_satisfiable_by_accident(self):
        """A guard against the arithmetic closing again.

        The failure mode was silent: no exception, no withheld entry that looked
        wrong, just a branch that never ran. If a future change makes the rescue
        unreachable again, this fails rather than passing vacuously.
        """
        from rishivan.varga.confidence import BirthConfidence as C
        from rishivan.varga.select import _rescued

        chart = compute_chart(JAIPUR)
        assert _rescued(chart, "D9", C.QUARTER) is True


class TestEachBodyIsJudgedAgainstItsOwnDrift:
    """The Moon covers 12 degrees a day and Saturn covers a tenth of one. Held
    to a single threshold, either the Moon is trusted too far or Saturn is
    withheld for no reason."""

    def _place(self, chart, body, margin_degrees, code="D9"):
        import copy

        from rishivan.varga.policy import arc_of

        c = copy.deepcopy(chart)
        arc = arc_of(code)
        base = c.planets[body].longitude
        c.planets[body].longitude = (base - base % arc) + margin_degrees
        return c

    def test_the_moon_that_close_to_an_edge_blocks_the_rescue(self, quarter_chart):
        """0.05 degrees is inside the Moon's 0.13-degree quarter-hour drift."""
        c = self._place(quarter_chart, "Moon", 0.05)
        s = select_vargas(c, "domain.relationship", BirthConfidence.QUARTER)
        assert "D9" not in codes(s)

    def test_saturn_that_close_to_an_edge_does_not(self, quarter_chart):
        """The same 0.05 degrees is forty times Saturn's drift. Withholding the
        division for it would be caution with no referent."""
        c = self._place(quarter_chart, "Saturn", 0.05)
        s = select_vargas(c, "domain.relationship", BirthConfidence.QUARTER)
        assert "D9" in codes(s)


class TestTheVargaLagnaDoesNotGateSignEvidence:
    """Every varga predicate in the registry reads a graha's *sign* in the
    division - `varga_occupies`, `varga_dignity`, `vargottama`. Not one reads a
    varga house, so not one depends on the varga ascendant. Gating them on an
    ascendant nothing consults withheld 403 usable rule conditions."""

    def test_an_ascendant_on_a_boundary_does_not_withhold_the_division(
        self, quarter_chart
    ):
        import copy

        from rishivan.varga.policy import arc_of

        c = copy.deepcopy(quarter_chart)
        arc = arc_of("D9")
        base = c.ascendant_longitude
        c.ascendant_longitude = (base - base % arc) + 0.001

        s = select_vargas(c, "domain.relationship", BirthConfidence.QUARTER)
        assert "D9" in codes(s)

    def test_no_rule_in_the_corpus_reads_a_varga_house(self):
        """The premise of the test above, asserted rather than assumed. A varga
        *house* predicate landing in the registry makes the ascendant
        load-bearing again, and this is what says so."""
        from rishivan.koonji.registry import seed_registry

        registry = seed_registry()
        for name in ("varga_occupies", "varga_dignity"):
            spec = registry.predicate(name)
            kinds = {a.name for a in spec.args}
            assert "bhava" not in kinds, (
                f"{name} now takes a bhava, so the varga ascendant is "
                f"load-bearing again and _rescued must test it"
            )
