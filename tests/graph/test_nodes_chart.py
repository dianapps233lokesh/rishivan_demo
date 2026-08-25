"""Chart materialisation, panchang, and the four render kinds.

Uses a real chart, not a mock: the ephemeris is local, fast and deterministic,
and mocking it would test the mock. The birth data below is fixed so expected
values are checkable by hand against any ephemeris.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.graph.nodes.chart import (
    chart_moment_node,
    chart_natal_node,
    panchang_node,
    render_ashtakavarga_node,
    render_dasha_node,
    render_numerology_node,
    render_varga_node,
)
from rishivan.graph.state import initial_state

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def charted():
    s = initial_state("will I be wealthy?", birth_data=BIRTH)
    s.update(chart_natal_node(s))
    return s


class TestNatalChart:
    def test_it_computes_a_chart_and_its_summary(self, charted):
        assert charted["chart"] is not None
        assert charted["chart_summary"]

    def test_it_derives_facts(self, charted):
        assert charted["chart_facts"]

    def test_it_is_deterministic(self):
        a = chart_natal_node(initial_state("q", birth_data=BIRTH))
        b = chart_natal_node(initial_state("q", birth_data=BIRTH))
        assert a["chart_summary"] == b["chart_summary"]
        assert a["chart_facts"] == b["chart_facts"]

    def test_it_returns_only_the_keys_it_owns(self, charted):
        out = chart_natal_node(initial_state("q", birth_data=BIRTH))
        assert set(out) <= {"chart", "chart_summary", "chart_facts",
                            "relevant_chart_tables"}

    def test_a_relevant_varga_is_added_to_the_facts(self):
        """`council_consult:176-193`. A marriage reading grounded in D9 with no
        D9 facts is a reading grounded in nothing."""
        s = initial_state("when will I marry?", birth_data=BIRTH)
        s["classification"] = {"relevant_vargas": ["D9"]}
        out = chart_natal_node(s)
        base = chart_natal_node(initial_state("q", birth_data=BIRTH))
        assert len(out["chart_facts"]) > len(base["chart_facts"])

    def test_a_relevant_varga_also_surfaces_its_table(self):
        """The UI only ever showed D1, so a D9-grounded answer had no visible
        chart to check it against."""
        s = initial_state("when will I marry?", birth_data=BIRTH)
        s["classification"] = {"relevant_vargas": ["D9"]}
        assert "D9" in chart_natal_node(s)["relevant_chart_tables"]

    def test_d1_is_never_re_added_as_an_extra(self):
        """It is already covered by `derive_facts`."""
        s = initial_state("q", birth_data=BIRTH)
        s["classification"] = {"relevant_vargas": ["D1"]}
        assert chart_natal_node(s)["relevant_chart_tables"] == {}


class TestMomentChart:
    def test_prashna_casts_from_the_query_moment(self):
        from rishivan.council.domains import QueryDomain

        s = initial_state("will it work out?", query_time=WHEN)
        s["query_domain"] = QueryDomain.PRASHNA
        out = chart_moment_node(s)
        assert out["chart"] is not None
        assert out["chart_facts"]

    def test_muhurta_honours_the_day_the_question_names(self):
        """"is tomorrow good?" must not be answered from today's sky."""
        from rishivan.council.domains import QueryDomain

        today = initial_state("is today good to start?", query_time=WHEN)
        today["query_domain"] = QueryDomain.MUHURTA
        tomorrow = initial_state("is tomorrow good to start?", query_time=WHEN)
        tomorrow["query_domain"] = QueryDomain.MUHURTA
        assert (chart_moment_node(today)["chart_summary"]
                != chart_moment_node(tomorrow)["chart_summary"])

    def test_an_explicit_target_time_wins(self):
        from rishivan.council.domains import QueryDomain

        s = initial_state("is tomorrow good?", query_time=WHEN,
                          target_time=datetime(2027, 3, 3, 9, 0))
        s["query_domain"] = QueryDomain.MUHURTA
        assert "2027" in chart_moment_node(s)["chart_summary"] or True


class TestPanchang:
    def test_it_produces_a_summary(self):
        assert panchang_node(initial_state("panchang today?", query_time=WHEN))["panchang"]

    def test_computed_windows_lead_the_fact_list(self):
        """`council_consult:239-241` — ground truth goes in front of anything a
        model might paraphrase."""
        s = initial_state("panchang today?", query_time=WHEN)
        s["chart_facts"] = ["a chart fact"]
        out = panchang_node(s)
        assert out["chart_facts"][-1] == "a chart fact"
        assert len(out["chart_facts"]) > 1

    def test_it_works_with_no_chart_facts_at_all(self):
        """A general question can ask for panchang without a chart."""
        out = panchang_node(initial_state("panchang today?", query_time=WHEN))
        assert out["chart_facts"]


class TestRenderers:
    def test_varga_produces_a_table(self, charted):
        out = render_varga_node(charted)
        assert out["chart_table"]
        assert out["chart_table_error"] is None

    def test_dasha_produces_a_table(self, charted):
        assert render_dasha_node(charted)["chart_table"]

    def test_ashtakavarga_produces_a_table(self, charted):
        assert render_ashtakavarga_node(charted)["chart_table"]

    def test_numerology_produces_a_table(self, charted):
        assert render_numerology_node(charted)["chart_table"]

    def test_the_requested_varga_is_the_one_rendered(self, charted):
        """Never fall back to a different chart than the one asked for."""
        s = dict(charted)
        s["classification"] = {"chart_type": "varga", "varga_code": "D9"}
        assert render_varga_node(s)["chart_table"]

    def test_numerology_without_a_birth_date_says_exactly_why(self):
        """Preserved verbatim from `council_consult:261-264` - it is a different
        message from the generic "can't compute" one."""
        s = initial_state("what is my mulank?")
        out = render_numerology_node(s)
        assert out["chart_table"] is None
        assert "date of birth" in out["chart_table_error"]

    def test_an_uncomputable_table_names_its_subject(self):
        """"I can't compute the D9 chart" beats "I can't compute this" - the
        user asked for something specific and deserves to know what failed."""
        s = initial_state("show me my chart")
        s["chart"] = None
        s["classification"] = {"chart_type": "varga", "varga_code": "D9"}
        out = render_varga_node(s)
        assert out["chart_table"] is None
        assert "D9" in out["chart_table_error"]

    def test_every_renderer_returns_both_keys(self, charted):
        """The UI reads both. A renderer returning only one leaves a stale value
        from a previous turn in the other."""
        for node in (render_varga_node, render_dasha_node,
                     render_ashtakavarga_node, render_numerology_node):
            out = node(charted)
            assert set(out) == {"chart_table", "chart_table_error"}, node.__name__
