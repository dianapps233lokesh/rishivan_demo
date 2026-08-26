"""Dated predictions, written down where they can later be scored.

**The falsifiability play, and the reason it is small.** A prediction is only
written when it has a claim above the floor *and* a window to land in. A ledger
of unfalsifiable statements scores nothing and reads as rigour, which is worse
than not keeping one at all.
"""

import inspect
import json

import pytest

from rishivan.council import ledger as ledger_module
from rishivan.council.answer_plan import AllowedClaim, AnswerPlan
from rishivan.council.ledger import Ledger, Prediction, predictions_from

ASKED = "2026-08-26T12:00:00"

DATED = AllowedClaim(
    claim_id="career.rise", band="strongly_indicated",
    phrasing="strongly indicated", confidence=0.8,
    citations=("bphs ch10.v1",), rule_ids=("R3",), tier="house",
    corroborated=True, window="Aug 2026 – Aug 2036",
)

UNDATED = AllowedClaim(
    claim_id="wealth.accumulation", band="strongly_indicated",
    phrasing="strongly indicated", confidence=0.78,
    citations=("bphs ch34.v12",), rule_ids=("R1",), tier="house",
    corroborated=True,
)


def _plan(allowed):
    return AnswerPlan(question="q", domain="domain.career",
                      allowed=tuple(allowed))


def _preds(allowed=(DATED,), run_id="run-1"):
    return predictions_from(_plan(allowed), run_id=run_id, asked_at=ASKED)


# ==========================================================================
# What becomes a prediction
# ==========================================================================


def test_a_claim_without_a_window_is_not_a_prediction():
    """Unfalsifiable. A ledger full of these scores nothing."""
    assert predictions_from(_plan([UNDATED]), run_id="r", asked_at=ASKED) == []


def test_a_claim_with_a_window_becomes_a_prediction():
    assert len(_preds()) == 1


def test_only_the_dated_claims_are_written():
    assert [p.claim_id for p in _preds([DATED, UNDATED])] == ["career.rise"]


def test_an_empty_plan_writes_nothing():
    assert _preds(()) == []


# ==========================================================================
# What a prediction carries
# ==========================================================================


def test_a_prediction_carries_the_verses_behind_it():
    """A prediction nobody can trace back to a verse cannot be argued with,
    only believed or not."""
    p = _preds()[0]
    assert p.citations and p.rule_ids


def test_a_prediction_carries_its_window():
    p = _preds()[0]
    assert p.window == DATED.window


def test_a_prediction_carries_its_confidence_and_band():
    """Scoring later needs to know how loudly it was said. A ledger where a
    0.4 and a 0.9 look alike cannot tell calibration from luck."""
    p = _preds()[0]
    assert p.confidence == DATED.confidence
    assert p.band == DATED.band


def test_a_prediction_starts_open():
    assert _preds()[0].outcome == "open"


def test_a_prediction_records_when_it_was_asked():
    assert _preds()[0].asked_at == ASKED


# ==========================================================================
# Identity
# ==========================================================================


def test_the_same_run_and_claim_produce_the_same_id():
    """Content-addressed, so replaying a run cannot double-count it."""
    assert _preds()[0].prediction_id == _preds()[0].prediction_id


def test_two_different_claims_produce_different_ids():
    other = AllowedClaim(
        claim_id="career.change", band="strongly_indicated",
        phrasing="strongly indicated", confidence=0.7,
        citations=("bphs ch10.v2",), rule_ids=("R4",), tier="house",
        corroborated=True, window="Aug 2026 – Aug 2036",
    )
    ids = {p.prediction_id for p in _preds([DATED, other])}
    assert len(ids) == 2


def test_two_runs_of_the_same_claim_produce_different_ids():
    a = _preds(run_id="run-1")[0]
    b = _preds(run_id="run-2")[0]
    assert a.prediction_id != b.prediction_id


# ==========================================================================
# The store
# ==========================================================================


def test_appending_the_same_prediction_twice_stores_one(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    p = _preds()[0]
    led.append(p)
    led.append(p)
    assert len(led.all()) == 1


def test_a_prediction_survives_a_round_trip(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.append(_preds()[0])
    assert Ledger(tmp_path / "l.jsonl").all()[0].claim_id == "career.rise"


def test_reading_a_ledger_that_does_not_exist_yet_is_empty(tmp_path):
    assert Ledger(tmp_path / "nothing.jsonl").all() == []


def test_a_corrupt_line_does_not_take_down_the_ledger(tmp_path):
    """JSONL on disk. One bad append must cost one record, not the file."""
    path = tmp_path / "l.jsonl"
    led = Ledger(path)
    led.append(_preds()[0])
    with path.open("a") as fh:
        fh.write("{not json\n")
    led.append(_preds(run_id="run-2")[0])
    assert len(Ledger(path).all()) == 2


def test_resolving_a_prediction_records_when_and_why(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    p = _preds()[0]
    led.append(p)
    led.resolve(p.prediction_id, outcome="occurred",
                resolved_at="2030-01-01T00:00:00", note="promotion in March")
    stored = led.all()[0]
    assert stored.outcome == "occurred"
    assert stored.resolved_at and stored.note


def test_resolving_an_unknown_prediction_raises(tmp_path):
    """Silently doing nothing would let a scoring script report a clean run
    while resolving nothing at all."""
    led = Ledger(tmp_path / "l.jsonl")
    with pytest.raises(KeyError):
        led.resolve("nope", outcome="occurred", resolved_at=ASKED)


def test_an_invalid_outcome_is_refused(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    p = _preds()[0]
    led.append(p)
    with pytest.raises(ValueError):
        led.resolve(p.prediction_id, outcome="sort of", resolved_at=ASKED)


def test_open_at_finds_what_is_still_unresolved(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    led.append(_preds()[0])
    assert led.open_predictions()


def test_a_resolved_prediction_is_no_longer_open(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    p = _preds()[0]
    led.append(p)
    led.resolve(p.prediction_id, outcome="did_not_occur", resolved_at=ASKED)
    assert led.open_predictions() == []


# ==========================================================================
# Determinism
# ==========================================================================


def test_the_ledger_never_reads_the_clock():
    """A backtest asks about 1998. A ledger that stamps `now` makes every
    replayed run look like it was predicted today, and the calibration figure
    it produces is meaningless."""
    source = inspect.getsource(ledger_module)
    assert "datetime.now" not in source
    assert "time.time" not in source


def test_predictions_are_json_serialisable():
    json.dumps(_preds()[0].to_dict())
