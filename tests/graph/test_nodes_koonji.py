"""The node that connects 1,117 compiled rules to a user's question.

Before this node the Koonji engine was unreachable from the graph — `grep -rn
koonji rishivan/graph` found two reads of a key nothing wrote and nothing else.
Every rule extracted from every book was inert.

Two things here are easy to lose in a refactor and expensive to lose quietly:
the selected vargas must reach the fact set, and a bundle failure must cost the
rule half of the answer rather than the answer.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.council.hierarchy import hierarchy_for
from rishivan.graph.nodes import koonji
from rishivan.graph.nodes.chart import chart_natal_node
from rishivan.graph.nodes.diagnosis import chart_state_node
from rishivan.graph.nodes.hierarchy import hierarchy_node
from rishivan.graph.nodes.koonji import koonji_read_node
from rishivan.graph.nodes.varga import varga_select_node
from rishivan.graph.state import RishivanState, initial_state

BIRTH = BirthData(year=1990, month=1, day=1, hour=12, minute=0,
                  tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="Delhi")
PRECISE = BirthData(year=1990, month=1, day=1, hour=12, minute=37,
                    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="Delhi")
"""12:00 reads as HOUR confidence and Phase 3 correctly withholds D9 from it —
3.33° divisions against 7.5° of ascendant uncertainty. A varga test needs a
birth time that earns the varga."""
WHEN = datetime(2026, 8, 26, 12, 0)


def _prepared(question="will I become wealthy?", *, chart=True, birth=BIRTH):
    s = initial_state(question, birth_data=birth if chart else None,
                      query_time=WHEN)
    if chart:
        s.update(chart_natal_node(s))
        s.update(chart_state_node(s))
    s.update(hierarchy_node(s))
    if chart:
        s.update(varga_select_node(s))
    return s


@pytest.fixture(scope="module")
def served():
    return koonji_read_node(_prepared())


def test_a_real_chart_produces_a_reading(served):
    assert served["reading"] is not None
    assert served["reading"].considered > 0


def test_rules_actually_fire(served):
    """Not merely retrieved. A reading that considers 151 rules and fires none
    is a fact set and a rule base that stopped agreeing."""
    assert served["reading"].firings


def test_claims_come_out_with_citations(served):
    reading = served["reading"]
    assert reading.claims
    assert reading.citations()


def test_the_served_statuses_are_stated_not_inherited():
    """Every extracted rule is `candidate`; none is `production`. Reading at
    the engine's default returns zero rules — silently, and looking exactly
    like a chart the classical material has nothing to say about."""
    assert "candidate" in koonji.SERVED_STATUSES


def test_the_reading_is_labelled_unreviewed(served):
    """A rule nobody has reviewed may still be served. It may not be served
    as though somebody had."""
    assert served["reading_is_unreviewed"] is True


def test_the_selected_vargas_reach_the_fact_set():
    """Phase 3 selects D9 for a marriage question. The fact set is compiled
    once, so a division not passed here can never match a rule however the
    policy scoped it."""
    state = _prepared("when will I get married?", birth=PRECISE)
    assert "D9" in state["vargas"].selected
    out = koonji_read_node(state)
    names = out["reading"].facts.atom_names()
    assert any("varga.d9" in n for n in names), "no D9 atom reached the fact set"


def test_the_hierarchy_weights_reach_the_evidence_graph(monkeypatch):
    seen = {}
    import rishivan.koonji.engine as engine_mod

    original = engine_mod.build_evidence

    def spy(*args, **kw):
        seen.update(kw)
        return original(*args, **kw)

    monkeypatch.setattr(engine_mod, "build_evidence", spy)
    koonji_read_node(_prepared("will I become wealthy?"))
    assert seen["tier_weights"] == hierarchy_for("domain.wealth").tier_weights
    assert seen["min_independent"] == (
        hierarchy_for("domain.wealth").min_independent_sources
    )


def test_no_chart_means_no_reading_and_no_exception():
    out = koonji_read_node(_prepared(chart=False))
    assert out["reading"] is None


def test_a_varga_the_birth_time_cannot_support_stays_out_of_the_fact_set():
    """The other half of the gate. A withheld division must be absent, not
    merely unreported - 144 atoms of noise wearing a decimal point is still
    matchable by a rule."""
    state = _prepared("when will I get married?")
    assert "D9" not in state["vargas"].selected
    names = koonji_read_node(state)["reading"].facts.atom_names()
    assert not any("varga.d9" in n for n in names)


def test_a_bundle_failure_degrades_to_no_reading_not_to_a_crash(monkeypatch):
    """A stale or missing bundle costs the Koonji half of the answer. Page
    retrieval is untouched and still grounds a reply. Failing the turn here
    would make a deployment problem look like a silent corpus."""
    def boom():
        raise RuntimeError("bundle is stale")

    monkeypatch.setattr(koonji, "_engine", boom)
    out = koonji_read_node(_prepared())
    assert out["reading"] is None


def test_the_engine_is_loaded_once():
    """`from_rules()` compiles 1,117 rules. Paying that per request would put
    seconds on the critical path of every chart question."""
    assert koonji._engine() is koonji._engine()


def test_every_key_returned_is_declared_in_the_state(served):
    assert set(served) <= set(RishivanState.__annotations__)


def test_the_node_makes_no_model_call():
    import inspect

    assert "client" not in inspect.signature(koonji_read_node).parameters


def test_the_reading_is_deterministic():
    state = _prepared()
    a = koonji_read_node(state)["reading"]
    b = koonji_read_node(state)["reading"]
    assert [c.claim_id for c in a.claims] == [c.claim_id for c in b.claims]
    assert [round(c.confidence, 6) for c in a.claims] == [
        round(c.confidence, 6) for c in b.claims
    ]
