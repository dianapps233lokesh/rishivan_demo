"""The model path, driven end to end without a network.

`extract.py`'s own tests cover the six calls and their blindness properties.
These cover what wraps them: that a run survives a passage blowing up, that a
blocked candidate cannot reach a rule file, that the compiler is the only thing
allowed to decide what gets written, and that nothing arrives as `production`.

The client is scripted. The point is the orchestration, and the orchestration is
where the mistakes that cost a corpus live.
"""

import json

import pytest

from rishivan.koonji.client import Budget, ExtractionUnavailable, RecordingClient
from rishivan.koonji.corpus import Unit
from rishivan.koonji.pipeline import (
    ExtractRun,
    convert_books,
    detect_restatements,
    gate,
)
from rishivan.koonji.registry import seed_registry


# -- a scripted client ------------------------------------------------------


def _rule(rule_id="T.WEALTH.CH1V1.0001", quote="A verse about wealth."):
    return {
        "id": rule_id,
        "school": "school.parashari",
        "assertion": "assert_claim",
        "domains": {"domain.wealth": 0.9},
        "source": {"quote": quote},
        "when": {"occupies_bhava": {"subject": "10th lord", "bhava": 11}},
        "indicates": {"claim": "wealth.accumulation", "polarity": "positive",
                      "magnitude": "strong", "text": "wealth"},
        "confidence": 0.8,
    }


def _script(rule=None, verdict="ACCEPT"):
    rule = rule or _rule()
    return [
        json.dumps({"rule_bearing": True, "count": 1}),        # classify
        json.dumps({"rules": [rule], "proposals": []}),         # extract @0.0
        json.dumps({"rules": [rule], "proposals": []}),         # extract @0.4
        json.dumps({"rules": [rule], "disagreements": []}),     # reconcile
        json.dumps({"verdicts": [{                              # verify
            "rule_id": rule["id"], "verdict": verdict,
            "findings": [] if verdict == "ACCEPT" else [{
                "category": "dropped_condition", "severity": "error",
                "message": "a condition in the verse is missing",
            }],
        }]}),
        "If the 10th lord is in the 11th, the native gains wealth.",  # back-translate
    ]


class ScriptedClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def complete(self, **kw):
        self.calls += 1
        return self.script.pop(0) if self.script else "{}"


class ExplodingClient:
    def complete(self, **kw):
        raise ExtractionUnavailable("provider is down")


@pytest.fixture
def registry():
    return seed_registry()


# ==========================================================================


class TestGate:
    def test_the_compiler_decides_what_is_written(self, registry):
        """Not the producer. A converter that dropped rules on its own reasoning
        would grow a second, undocumented copy of the compiler."""
        good = _doc("GOOD")
        bad = _doc("BAD")
        bad["when"] = {"combust": {"subject": "graha.sun"}}  # pass 7 rejects this
        rules, report, _ = gate([good, bad], registry)
        assert [r.rule_id for r in rules] == ["GOOD"]
        assert "BAD" in report.dropped

    def test_a_dropped_rule_carries_the_diagnostic_that_killed_it(self, registry):
        bad = _doc("BAD")
        bad["when"] = {"combust": {"subject": "graha.sun"}}
        _, report, _ = gate([bad], registry)
        assert "realizability" in report.dropped["BAD"]

    def test_a_corpus_level_error_is_surfaced_not_dropped_around(self, registry):
        """A duplicate id belongs to no single rule. Attributing it to one and
        dropping that rule would remove the wrong thing."""
        rules, report, _ = gate([_doc("DUP"), _doc("DUP")], registry)
        assert report.warnings

    def test_nothing_is_written_that_cannot_be_read_back(self, registry):
        """A rule that fails the round trip is one a reviewer would approve and
        the engine would never load."""
        rules, report, _ = gate([_doc("OK")], registry)
        assert report.round_trip_failures == {}
        assert len(rules) == 1

    def test_the_report_renders(self, registry):
        _, report, _ = gate([_doc("OK")], registry)
        assert "documents" in str(report)


class TestConvertRun:
    def test_a_dry_run_writes_nothing(self, tmp_path):
        run = convert_books(out_dir=tmp_path, limit=50, write=False)
        assert run.written == []
        assert list(tmp_path.iterdir()) == []

    def test_writing_lands_under_converted(self, tmp_path):
        """Machine output never shares a file with reviewed hand-authored
        material - the generated file is overwritten on every run, and a hand
        edit inside it would vanish without trace."""
        run = convert_books(out_dir=tmp_path, limit=400)
        assert run.written
        assert all(p.parent.name == "converted" for p in run.written)

    def test_a_second_run_is_byte_identical(self, tmp_path):
        """Stable ids and sorted output, so a re-run diffs to nothing and a real
        change is visible."""
        first = convert_books(out_dir=tmp_path, limit=400)
        before = {p: p.read_text() for p in first.written}
        convert_books(out_dir=tmp_path, limit=400)
        assert {p: p.read_text() for p in before} == before

    def test_the_run_reports_both_halves(self, tmp_path):
        run = convert_books(out_dir=tmp_path, limit=200, write=False)
        text = str(run)
        assert "rule documents" in text
        assert "documents ->" in text


class TestExtractRun:
    def test_a_clean_passage_becomes_a_written_rule(self, tmp_path, monkeypatch):
        run = _run(monkeypatch, tmp_path, ScriptedClient(_script()))
        assert run.candidates == 1
        assert run.written
        assert run.gate.kept == 1

    def test_a_blocked_candidate_never_reaches_a_rule_file(self, tmp_path, monkeypatch):
        """It goes to the review queue instead. A candidate the validator
        rejected is a reviewer's problem, not a rule."""
        run = _run(monkeypatch, tmp_path, ScriptedClient(_script(verdict="REJECT")))
        assert run.blocked == 1
        assert run.candidates == 0
        assert run.written == []

    def test_a_blocked_candidate_still_appears_in_the_queue(self, tmp_path, monkeypatch):
        run = _run(monkeypatch, tmp_path, ScriptedClient(_script(verdict="REJECT")))
        assert run.queue

    def test_a_fabricated_quote_is_blocked(self, tmp_path, monkeypatch):
        """The most damaging output this system can produce."""
        rule = _rule(quote="A verse that is nowhere in the passage.")
        run = _run(monkeypatch, tmp_path, ScriptedClient(_script(rule)))
        assert run.blocked == 1
        assert run.written == []

    def test_one_exploding_passage_does_not_end_the_run(self, tmp_path, monkeypatch):
        """Losing four hundred passages to one malformed response is the failure
        mode that makes people stop trusting the pipeline."""
        run = _run(monkeypatch, tmp_path, ExplodingClient(), passages=3)
        assert run.passages == 3
        assert len(run.failures) == 3
        assert run.written == []

    def test_the_queue_is_worst_first(self, tmp_path, monkeypatch):
        run = _run(monkeypatch, tmp_path, ScriptedClient(_script()))
        priorities = [row[0] for row in run.queue]
        assert priorities == sorted(priorities, reverse=True)

    def test_call_count_is_recorded(self, tmp_path, monkeypatch):
        run = _run(monkeypatch, tmp_path, ScriptedClient(_script()))
        assert run.calls == 6

    def test_the_run_renders(self):
        assert "passages" in str(ExtractRun(passages=2, candidates=1))


class TestBudget:
    def test_a_ceiling_stops_the_run(self):
        """One forgotten `--limit` turning a proving run into a full corpus run
        is the expensive mistake here."""
        budget = Budget(max_calls=2)
        budget.spend("a", "b")
        budget.spend("a", "b")
        with pytest.raises(ExtractionUnavailable, match="budget"):
            budget.check()

    def test_no_ceiling_by_default_but_the_cli_sets_one(self):
        budget = Budget()
        for _ in range(50):
            budget.spend("a", "b")
        budget.check()  # does not raise

    def test_spend_is_reported(self):
        budget = Budget()
        budget.spend("x" * 1000, "y" * 500)
        assert budget.calls == 1
        assert "1 calls" in str(budget)


class TestRecordingClient:
    def test_every_exchange_is_written(self, tmp_path):
        path = tmp_path / "run.jsonl"
        client = RecordingClient(ScriptedClient(["hello"]), path)
        client.complete(system="s", prompt="p", temperature=0.4, model="m")
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        assert rows[0]["response"] == "hello"
        assert rows[0]["temperature"] == 0.4


class TestRestatements:
    def test_two_rules_with_the_same_conditions_are_grouped(self, registry):
        """BPHS and Jataka Parijata saying the same thing is one piece of
        evidence. An unaware confidence calculation counts it twice."""
        a, b = _doc("A"), _doc("B")
        rules, _, _ = gate([a, b], registry)
        groups = detect_restatements(rules)
        assert any(set(ids) == {"A", "B"} for ids in groups.values())

    def test_condition_order_does_not_hide_a_restatement(self, registry):
        """Without sorting, this finds only restatements that happen to have
        been written down in the same order - the easy half."""
        a, b = _doc("A"), _doc("B")
        pair = [{"occupies_bhava": {"subject": "10th lord", "bhava": 11}},
                {"in_kendra": {"subject": "graha.jupiter"}}]
        a["when"] = {"all": pair}
        b["when"] = {"all": list(reversed(pair))}
        rules, _, _ = gate([a, b], registry)
        assert any(set(ids) == {"A", "B"} for ids in detect_restatements(rules).values())

    def test_different_conditions_are_not_grouped(self, registry):
        a, b = _doc("A"), _doc("B")
        b["when"] = {"occupies_bhava": {"subject": "2nd lord", "bhava": 5}}
        rules, _, _ = gate([a, b], registry)
        assert detect_restatements(rules) == {}

    def test_it_proposes_rather_than_writes(self, registry):
        """`restates` goes into provenance only once somebody agrees the two
        really are the same statement."""
        rules, _, _ = gate([_doc("A"), _doc("B")], registry)
        detect_restatements(rules)
        assert all(r.provenance.restates == [] for r in rules)


# -- helpers ---------------------------------------------------------------


def _doc(rule_id: str) -> dict:
    return {
        "id": rule_id,
        "status": "candidate",
        "school": "school.parashari",
        "assertion": "assert_claim",
        "domains": {"domain.wealth": 0.9},
        "source": {"book": "bphs", "edition": "bphs-gcsharma-vol1",
                   "locator": "ch1.v1", "quote": "a verse"},
        "when": {"occupies_bhava": {"subject": "10th lord", "bhava": 11}},
        "indicates": {"claim": "wealth.accumulation", "polarity": "positive",
                      "magnitude": "strong", "text": "wealth"},
    }


def _run(monkeypatch, tmp_path, client, passages: int = 1):
    """Drive `extract_books` over a fixed synthetic corpus."""
    from rishivan.koonji import pipeline

    units = [
        Unit(unit_id=str(i), book_id="bphs", edition_id="bphs-gcsharma-vol1",
             chapter="1", verse_ref=str(i + 1),
             translation="A verse about wealth.")
        for i in range(passages)
    ]
    monkeypatch.setattr(pipeline, "load_corpus", lambda **kw: units)
    return pipeline.extract_books(client, out_dir=tmp_path)
