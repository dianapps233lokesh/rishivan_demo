"""The extraction pipeline's orchestration, with a scripted model.

No network and no key: the client is injected, and what is under test is the
sequencing - six calls in the right order, the verifier not shown the
extractor's reasoning, the back-translator not shown the passage, and every
candidate run through the deterministic validators before it can reach a
reviewer. That sequencing is where the interesting mistakes live.
"""

import json

import pytest

from rishivan.koonji.extract import (
    EXTRACTION_TEMPERATURES,
    Extractor,
    Passage,
    approximation_rate,
    form_distribution,
)
from rishivan.koonji.registry import seed_registry

PASSAGE_TEXT = (
    "13. If the 10th Lord is situated in the 11th House, the 11th Lord in the "
    "Ascendant and, Venus in the 10th, the combination makes the native a "
    "possessor of precious stones."
)

RULE_JSON = {
    "id": "BPHS.WEALTH.10L11H.0001",
    "assertion": "assert_claim",
    "school": "school.parashari",
    "domains": {"domain.wealth": 0.95},
    "confidence": 0.82,
    "source": {
        "quote": "If the 10th Lord is situated in the 11th House",
    },
    "when": [
        {"occupies_bhava": {"subject": "10th lord", "bhava": 11}},
        {"occupies_bhava": {"subject": "Venus", "bhava": 10}},
    ],
    "indicates": {
        "claim": "wealth.accumulation",
        "polarity": "positive",
        "magnitude": "strong",
        "text": "a possessor of precious stones",
    },
}


class ScriptedClient:
    """Replays canned responses and records exactly what it was asked."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, *, system, prompt, temperature=0.0, json_schema=None, model=""):
        self.calls.append(
            {"system": system, "prompt": prompt, "temperature": temperature, "model": model}
        )
        if not self.responses:
            raise AssertionError("the pipeline made more calls than were scripted")
        response = self.responses.pop(0)
        return response if isinstance(response, str) else json.dumps(response)


def passage(text=PASSAGE_TEXT):
    return Passage(
        passage_id="bphs:23:13", text=text, book_id="bphs",
        edition_id="bphs-gcsharma-vol1", locator="ch23.v13",
    )


def full_script(rule=None, *, proposals=(), disagreements=(), verdicts=()):
    rule = rule or RULE_JSON
    extraction = {"rules": [rule], "proposals": list(proposals)}
    return [
        {"is_rule_bearing": True, "assertion_kinds": ["assert_claim"]},   # classify
        extraction,                                                       # extract 0.0
        extraction,                                                       # extract 0.4
        {"rules": [rule], "proposals": list(proposals),
         "material_disagreements": list(disagreements)},                  # reconcile
        {"verdicts": list(verdicts)},                                     # verify
        "The tenth lord in the eleventh and Venus in the tenth give wealth.",
    ]


@pytest.fixture
def registry():
    return seed_registry()


class TestSequencing:
    def test_six_calls_for_one_rule_bearing_passage(self, registry):
        client = ScriptedClient(full_script())
        result = Extractor(client, registry).process(passage())
        assert result.usage.calls == 6
        assert result.usage.by_stage == {
            "classify": 1, "extract@0.0": 1, "extract@0.4": 1,
            "reconcile": 1, "verify": 1, "back_translate": 1,
        }

    def test_the_two_extractions_run_at_different_temperatures(self, registry):
        client = ScriptedClient(full_script())
        Extractor(client, registry).process(passage())
        temps = [c["temperature"] for c in client.calls if "PASSAGE" in c["prompt"]]
        assert set(EXTRACTION_TEMPERATURES) <= set(temps)

    def test_a_non_rule_bearing_passage_costs_one_call(self, registry):
        """Invocation and framing are roughly a sixth of a classical text.
        Paying six calls to extract nothing from them is the easiest waste in
        the pipeline to avoid."""
        client = ScriptedClient([{"is_rule_bearing": False}])
        result = Extractor(client, registry).process(
            passage("Maitreya said: O Brahmin, tell me of the effects of houses.")
        )
        assert result.usage.calls == 1
        assert result.skipped == "not rule-bearing"
        assert result.candidates == []

    def test_skip_dual_drops_to_four_calls(self, registry):
        script = full_script()
        del script[2:4]  # no second extraction, no reconcile
        client = ScriptedClient(script)
        result = Extractor(client, registry).process(passage(), skip_dual=True)
        assert result.usage.calls == 4


class TestBlindness:
    """Two stages are deliberately deprived of information. Both matter."""

    def test_the_verifier_never_sees_the_extractors_reasoning(self, registry):
        client = ScriptedClient(full_script())
        Extractor(client, registry).process(passage())
        verify_call = next(c for c in client.calls if "Assume this extraction is WRONG" in c["system"])
        payload = json.loads(verify_call["prompt"])
        assert set(payload) == {"passage", "extracted"}
        assert "reasoning" not in verify_call["prompt"]

    def test_the_back_translator_never_sees_the_passage(self, registry):
        """If it can see the verse it will reproduce the verse, and the check
        stops testing anything."""
        client = ScriptedClient(full_script())
        Extractor(client, registry).process(passage())
        bt_call = client.calls[-1]
        assert "Render this structured rule" in bt_call["system"]
        assert PASSAGE_TEXT not in bt_call["prompt"]

    def test_the_extractor_is_told_proposing_is_correct(self, registry):
        client = ScriptedClient(full_script())
        Extractor(client, registry).process(passage())
        extract_call = client.calls[1]
        assert "CORRECT AND EXPECTED OUTCOME" in extract_call["system"]


class TestCandidates:
    def test_a_clean_extraction_becomes_a_candidate(self, registry):
        result = Extractor(ScriptedClient(full_script()), registry).process(passage())
        assert len(result.candidates) == 1
        candidate = result.candidates[0]
        assert candidate.rule.rule_id == "BPHS.WEALTH.10L11H.0001"
        assert candidate.flags.confidence == 0.82

    def test_source_metadata_is_filled_from_the_passage(self, registry):
        result = Extractor(ScriptedClient(full_script()), registry).process(passage())
        provenance = result.candidates[0].rule.provenance
        assert provenance.book_id == "bphs"
        assert provenance.locator == "ch23.v13"

    def test_an_extraction_that_will_not_parse_is_dropped_not_queued(self, registry):
        """A reviewer should not spend time reaching a conclusion the parser
        already reached."""
        broken = dict(RULE_JSON, when=[{"occupies_bhava": {"subject": "Proserpina", "bhava": 11}}])
        result = Extractor(ScriptedClient(full_script(broken)), registry).process(passage())
        assert result.candidates == []

    def test_extractions_are_always_candidates_never_production(self, registry):
        result = Extractor(ScriptedClient(full_script()), registry).process(passage())
        assert result.candidates[0].rule.status == "candidate"


class TestValidationIsApplied:
    def test_a_fabricated_quote_blocks_the_candidate(self, registry):
        fabricated = dict(RULE_JSON, source={"quote": "Jupiter in the 5th gives sons."})
        result = Extractor(ScriptedClient(full_script(fabricated)), registry).process(passage())
        assert result.blocked == ["BPHS.WEALTH.10L11H.0001"]

    def test_a_verifier_rejection_blocks_the_candidate(self, registry):
        verdicts = [{
            "rule_id": "BPHS.WEALTH.10L11H.0001",
            "verdict": "REJECT",
            "findings": [{"category": "dropped_condition", "severity": "error",
                          "message": "the 11th lord in the Ascendant is missing"}],
        }]
        result = Extractor(
            ScriptedClient(full_script(verdicts=verdicts)), registry
        ).process(passage())
        assert result.blocked == ["BPHS.WEALTH.10L11H.0001"]

    def test_an_accepting_verifier_leaves_the_candidate_clean(self, registry):
        verdicts = [{"rule_id": "BPHS.WEALTH.10L11H.0001", "verdict": "ACCEPT", "findings": []}]
        result = Extractor(
            ScriptedClient(full_script(verdicts=verdicts)), registry
        ).process(passage())
        assert result.blocked == []


class TestDisagreement:
    def test_material_disagreements_are_surfaced_not_resolved(self, registry):
        """Where the two runs differ materially is exactly where a human is
        needed. The pipeline's job is to say so, not to pick."""
        result = Extractor(
            ScriptedClient(full_script(disagreements=["run B dropped the Venus condition"])),
            registry,
        ).process(passage())
        assert result.disagreements == ["run B dropped the Venus condition"]


class TestProposals:
    def test_proposals_travel_with_the_candidate(self, registry):
        proposal = {
            "proposal_id": "p1",
            "registry": "predicate",
            "proposed_id": "occupies_bhava_from_arudha",
            "evidence_passages": ["bphs:23:13"],
            "why_insufficient": "The Arudha is not a reference point we can express.",
            "proposed_by": "extractor@test",
        }
        result = Extractor(
            ScriptedClient(full_script(proposals=[proposal])), registry
        ).process(passage())
        assert result.proposals[0].proposed_id == "occupies_bhava_from_arudha"
        assert result.candidates[0].proposals == result.proposals


class TestCorpusSignals:
    def test_approximation_rate_must_be_zero(self, registry):
        result = Extractor(ScriptedClient(full_script()), registry).process(passage())
        assert approximation_rate([result]) == 0.0

    def test_approximation_is_detected_when_it_happens(self, registry):
        approximated = dict(RULE_JSON, approximated=True)
        result = Extractor(
            ScriptedClient(full_script(approximated)), registry
        ).process(passage())
        assert approximation_rate([result]) == 1.0

    def test_form_distribution_projects_t_codes(self, registry):
        """A cheap regression signal: 5% lordship or 30% named yoga means the
        prompt or the OCR broke, and this catches it faster than reading rules."""
        result = Extractor(ScriptedClient(full_script()), registry).process(passage())
        assert form_distribution([result]) == {"T5_conjunctive": 1.0}

    def test_the_review_queue_is_ordered(self, registry):
        result = Extractor(ScriptedClient(full_script()), registry).process(passage())
        queue = result.queue()
        assert len(queue) == 1
        assert queue[0][0] >= 0


class TestJsonTolerance:
    def test_fenced_json_is_accepted(self, registry):
        """Models fence JSON whatever the instructions say."""
        script = full_script()
        script[0] = "```json\n" + json.dumps(script[0]) + "\n```"
        result = Extractor(ScriptedClient(script), registry).process(passage())
        assert result.candidates
