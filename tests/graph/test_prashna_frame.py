"""A prashna chart is a moment, not a nativity — and not a nativity with a
badly-remembered birth time either.

Both bugs here shipped together and reached a real reading. The first withheld
the D9 from every prashna turn; the second answered a marriage question using a
spouse significator computed from the afternoon the question was asked.
"""

from datetime import datetime

import pytest

from rishivan.council.domains import QueryDomain
from rishivan.graph.nodes.chart import chart_moment_node
from rishivan.graph.nodes.diagnosis import chart_state_node
from rishivan.graph.nodes.hierarchy import hierarchy_node
from rishivan.graph.nodes.varga import varga_select_node
from rishivan.graph.state import initial_state
from rishivan.varga.confidence import BirthConfidence

WHEN = datetime(2026, 8, 29, 14, 32, 17)


def _moment_state(domain=QueryDomain.PRASHNA, target=None,
                  question="when will I get married?"):
    state = initial_state(question, query_time=WHEN, target_time=target)
    state["query_domain"] = domain
    state.update(chart_moment_node(state))
    state.update(chart_state_node(state))
    state.update(hierarchy_node(state))
    state.update(varga_select_node(state))
    return state


class TestConfidenceIsStatedNotInferred:
    def test_a_prashna_moment_is_exact(self):
        """`resolve_confidence` falls through to `infer_confidence(birth_data)`,
        and this node discards birth_data - so every prashna chart resolved to
        UNKNOWN. The confidence machinery measures uncertainty in a REMEMBERED
        birth time. There is none here: the moment is a timestamp we generated.
        """
        assert _moment_state()["birth_confidence"] is BirthConfidence.EXACT

    def test_the_d9_reaches_a_prashna_reading(self):
        """The symptom. Step 4 of `prema`'s protocol is "D9 confirmation", and
        it was declared unavailable on every prashna turn - explaining itself
        with "needs a birth time known to the minute; yours is recorded to the
        hour" about a chart with no birth time at all."""
        assert "D9" in _moment_state()["vargas"].selected

    def test_a_muhurta_with_no_named_target_stays_unknown(self):
        """"Is tomorrow good?" names a DAY. The clock time is today's carried
        forward, so the ascendant is arbitrary within that day and every
        division depending on it must stay withheld."""
        state = _moment_state(QueryDomain.MUHURTA,
                              question="is tomorrow good for travel?")
        assert state["birth_confidence"] is BirthConfidence.UNKNOWN
        assert "D9" not in state["vargas"].selected

    def test_a_muhurta_with_a_named_target_is_exact(self):
        state = _moment_state(QueryDomain.MUHURTA,
                              target=datetime(2026, 9, 4, 10, 15))
        assert state["birth_confidence"] is BirthConfidence.EXACT


class TestNativityOnlyTechniquesAreWithheld:
    """Chara karakas rank the NATIVE'S grahas; an arudha counts from the BIRTH
    lagna. Fed a moment chart both still return a graha and a sign, and the
    answer is about that afternoon.

    A real prashna reading returned "Darakaraka Sun in the 6th house - the
    specific indicator for the spouse is also caught in a house of disputes",
    weighted it `moderate`, and used it to support a verdict that the chart
    carried no promise of marriage.
    """

    def test_the_prompt_names_no_spouse_significator(self):
        from rishivan.council.direct_prompt import build_direct_prompt

        prompt = build_direct_prompt(_moment_state(), for_analysis=True)
        assert "DARAKARAKA" not in prompt
        assert "UPAPADA" not in prompt

    def test_the_reading_is_told_why_rather_than_left_to_notice(self):
        from rishivan.council.direct_prompt import build_direct_prompt

        prompt = build_direct_prompt(_moment_state(), for_analysis=True)
        assert "chara karakas" in prompt
        assert "Do not name a spouse significator" in prompt

    def test_the_profile_stops_asking_for_them(self):
        from rishivan.council.question_profile import profile_for

        profile = profile_for("when will I marry?",
                              koonji_domain="domain.relationship",
                              has_birth_chart=False)
        assert not profile.needs("karaka.dara")
        assert not profile.needs("from_arudha_lagna.house.12")

    def test_the_producer_refuses_even_if_a_row_asks_for_it(self):
        """Defence in depth, and it is warranted: the requirement table is
        hand-editable in Mongo, so a row added there must not be able to
        resurrect a fabricated spouse."""
        from rishivan.council.requirements.producers import Context, produce

        state = _moment_state()
        ctx = Context(state=state, chart=state["chart"],
                      chart_state=state["chart_state"], when=WHEN,
                      is_natal=False)
        assert produce("karaka.dara", ctx) is None
        assert produce("from_arudha_lagna.house.12", ctx) is None

    def test_a_natal_chart_still_gets_both(self):
        """The fix must not cost a real nativity its Jaimini step."""
        from rishivan.chart.ephemeris import BirthData, compute_chart
        from rishivan.council.requirements.producers import Context, produce

        chart = compute_chart(BirthData(
            year=1990, month=1, day=1, hour=12, minute=0,
            tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
        ))
        ctx = Context(state={}, chart=chart, when=WHEN, is_natal=True)
        assert produce("karaka.dara", ctx)
        assert produce("from_arudha_lagna.house.12", ctx)
