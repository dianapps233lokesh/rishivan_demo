"""The one object every node reads and writes.

Phase 1 carries the Phase 2-5 keys already (chart_state, vargas, timing,
reports) so that later phases add nodes rather than migrating state. They stay
None here.
"""

from rishivan.graph.state import RESULT_KEYS, initial_state


def test_initial_state_carries_the_question():
    s = initial_state("will I be wealthy?")
    assert s["question"] == "will I be wealthy?"
    assert s["outcome"] == "pending"


def test_every_run_gets_an_id():
    """It becomes the trace id. Two runs must not share one."""
    assert initial_state("q")["run_id"] != initial_state("q")["run_id"]


def test_the_result_contract_is_declared_not_inferred():
    """`council_consult` returns exactly these 20 keys today. Naming them here
    is what lets the adapter test assert the contract instead of guessing it."""
    assert "primary_rishi" in RESULT_KEYS
    assert "answer_stream" in RESULT_KEYS
    assert len(RESULT_KEYS) == 20


def test_future_phase_keys_exist_and_are_none():
    """Phase 2-5 add nodes, not state migrations."""
    s = initial_state("q")
    for key in ("chart_state", "vargas", "timing", "hierarchy"):
        assert s[key] is None


def test_reports_is_a_list_so_the_fanout_can_reduce_into_it():
    assert initial_state("q")["reports"] == []


def test_birth_kwargs_are_carried_through():
    s = initial_state("q", tz_offset=5.5, place="Delhi")
    assert s["tz_offset"] == 5.5
    assert s["place"] == "Delhi"


def test_every_result_key_has_a_default():
    """A node reading a key nobody set gets a KeyError at the worst possible
    moment, and the gap is invisible until that branch is taken."""
    s = initial_state("q")
    missing = RESULT_KEYS - set(s)
    assert not missing, f"no default for: {sorted(missing)}"
