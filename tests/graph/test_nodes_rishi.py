"""One node, many Sends — and the assertions are on the prompt.

Phase 1's lesson: 133 node-level tests missed two shipping bugs, and both lived
in what reached the prompt. So this file fakes the model and asserts on the
string, not on the return shape.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.council.hierarchy import hierarchy_for
from rishivan.graph.nodes.chart import chart_natal_node
from rishivan.graph.nodes.diagnosis import chart_state_node
from rishivan.graph.nodes.hierarchy import hierarchy_node
from rishivan.graph.nodes.koonji import koonji_read_node
from rishivan.graph.nodes.rishi import rishi_node
from rishivan.graph.nodes.timing import dasha_windows_node
from rishivan.graph.nodes.varga import varga_select_node
from rishivan.graph.state import RishivanState, initial_state

BIRTH = BirthData(year=1990, month=1, day=1, hour=12, minute=37,
                  tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="Delhi")
WHEN = datetime(2026, 8, 26, 12, 0)

VALID = (
    '{"supporting": [{"statement": "the 2nd lord is exalted", '
    '"rule_ids": ["r1"], "chart_basis": ["x"], "weight": 0.5, '
    '"tier": "house"}], "weakening": [{"statement": "Saturn aspects it", '
    '"rule_ids": ["r2"], "chart_basis": ["y"], "weight": 0.3, '
    '"tier": "house"}], "score": 0.4, "confidence": 0.6, '
    '"assumptions": [], "would_change_my_mind": [], '
    '"confidence_reasons": ["two independent sources"]}'
)


class RecordingClient:
    """Captures the prompt instead of calling a model."""

    def __init__(self, response=VALID):
        self.prompts = []
        self.response = response
        self.models = self

    def generate_content(self, *, model, contents, config=None):
        self.prompts.append(contents)
        return type("R", (), {"text": self.response})()


class FailingClient:
    def __init__(self):
        self.models = self

    def generate_content(self, **kw):
        raise RuntimeError("the model is down")


@pytest.fixture(scope="module")
def prepared():
    s = initial_state("will I become wealthy?", birth_data=BIRTH, query_time=WHEN)
    for node in (chart_natal_node, chart_state_node, hierarchy_node,
                 varga_select_node, koonji_read_node, dasha_windows_node):
        s.update(node(s))
    return s


def _state(prepared, rishi="dhruvan"):
    s = dict(prepared)
    s["rishi"] = rishi
    return s


# ==========================================================================
# The return shape
# ==========================================================================


def test_the_report_lands_in_the_reduced_channel(prepared):
    out = rishi_node(_state(prepared), client=RecordingClient())
    assert isinstance(out["reports"], list) and len(out["reports"]) == 1


def test_it_returns_only_the_key_it_owns(prepared):
    """`reports` is the only reduced channel. A second key written from a
    fanned-out node is an InvalidUpdateError at runtime, on a concurrent
    branch no node test can reach."""
    out = rishi_node(_state(prepared), client=RecordingClient())
    assert set(out) == {"reports"}


def test_the_report_is_stamped_with_the_rishi_the_send_named(prepared):
    out = rishi_node(_state(prepared, "medhan"), client=RecordingClient())
    assert out["reports"][0].rishi == "medhan"


def test_the_report_is_stamped_with_the_routed_domain(prepared):
    out = rishi_node(_state(prepared), client=RecordingClient())
    assert out["reports"][0].domain == prepared["koonji_domain"]


def test_every_key_returned_is_declared_in_the_state(prepared):
    out = rishi_node(_state(prepared), client=RecordingClient())
    assert set(out) <= set(RishivanState.__annotations__)


# ==========================================================================
# The prompt
# ==========================================================================


def test_the_prompt_names_the_hierarchy_it_must_argue_from(prepared):
    client = RecordingClient()
    rishi_node(_state(prepared), client=client)
    prompt = client.prompts[0]
    assert "EVIDENCE HIERARCHY" in prompt
    assert "2th" in prompt or "2nd" in prompt or "11th" in prompt


def test_the_prompt_states_the_corroboration_floor(prepared):
    client = RecordingClient()
    rishi_node(_state(prepared), client=client)
    floor = hierarchy_for(prepared["koonji_domain"]).min_independent_sources
    assert f"{floor} independent source" in client.prompts[0]


def test_the_prompt_carries_the_fired_rules_with_their_ids(prepared):
    client = RecordingClient()
    rishi_node(_state(prepared), client=client)
    assert "RULES THAT FIRED" in client.prompts[0]
    assert "rule_ids:" in client.prompts[0]


def test_the_prompt_carries_the_cancelled_rules_section(prepared):
    """A yoga the VM cancelled is the most important thing a Rishi can be told
    and the one it will never infer from the fired list."""
    client = RecordingClient()
    rishi_node(_state(prepared), client=client)
    assert "CANCELLED" in client.prompts[0]


def test_the_prompt_carries_the_withheld_vargas(prepared):
    client = RecordingClient()
    rishi_node(_state(prepared), client=client)
    assert "DIVISIONAL CHARTS USED" in client.prompts[0]


def test_the_prompt_states_the_remit(prepared):
    client = RecordingClient()
    rishi_node(_state(prepared, "medhan"), client=client)
    assert "YOUR REMIT" in client.prompts[0]
    assert "marriage" in client.prompts[0]


def test_two_rishis_get_different_remits(prepared):
    a, b = RecordingClient(), RecordingClient()
    rishi_node(_state(prepared, "medhan"), client=a)
    rishi_node(_state(prepared, "dhruvan"), client=b)
    assert a.prompts[0] != b.prompts[0]


def test_the_prompt_demands_weakening_evidence(prepared):
    client = RecordingClient()
    rishi_node(_state(prepared), client=client)
    assert "weakening" in client.prompts[0].lower()


def test_the_prompt_says_the_rules_are_unreviewed(prepared):
    """All 1,117 are candidates. A Rishi told they are verified will weigh
    them as verified."""
    client = RecordingClient()
    rishi_node(_state(prepared), client=client)
    assert "review" in client.prompts[0].lower()


def test_the_prompt_forbids_uncited_statements(prepared):
    client = RecordingClient()
    rishi_node(_state(prepared), client=client)
    assert "cites at least one rule id" in client.prompts[0]


# ==========================================================================
# Failure
# ==========================================================================


def test_a_model_failure_becomes_an_abstention(prepared):
    """A Rishi that dies costs one opinion. Synthesis proceeds with fewer and
    says so."""
    out = rishi_node(_state(prepared), client=FailingClient())
    assert out["reports"][0].abstained


def test_a_contract_violation_becomes_an_abstention(prepared):
    bad = ('{"supporting": [{"statement": "good", "rule_ids": ["r1"], '
           '"chart_basis": ["x"], "weight": 0.5, "tier": "house"}], '
           '"weakening": [], "score": 0.5, "confidence": 0.6}')
    out = rishi_node(_state(prepared), client=RecordingClient(bad))
    assert out["reports"][0].abstained


def test_prose_where_json_was_asked_for_becomes_an_abstention(prepared):
    out = rishi_node(_state(prepared), client=RecordingClient("Looks good!"))
    assert out["reports"][0].abstained


def test_an_abstention_still_names_which_rishi_abstained(prepared):
    out = rishi_node(_state(prepared, "medhan"), client=FailingClient())
    assert out["reports"][0].rishi == "medhan"


def test_no_reading_still_produces_a_report():
    """Chartless questions reach the council too. An empty list downstream is
    indistinguishable from a crash."""
    s = initial_state("what is a yoga?")
    s["rishi"] = "vyom"
    out = rishi_node(s, client=RecordingClient())
    assert out["reports"]
