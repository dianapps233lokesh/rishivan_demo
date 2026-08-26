"""The prompt and the parser have to describe the same thing.

This file exists because they did not, and nothing caught it. The prompts
described the rule shape in prose; the model produced a reasonable dialect of
its own - `assertion_kind`, `when.all_of`, a bare top-level array - and
`parse_rule` rejected every document. Every extractor test passed throughout,
because a scripted client returns whatever the test author wrote, and the test
author wrote what the parser wanted.

So the example in the prompt is compiled here, by the real compiler. If the
frame changes and the prompt is not updated, this fails - which is the only
mechanism that keeps the two in step.
"""

import json

import pytest

from rishivan.koonji import prompts
from rishivan.koonji.compiler import parse_rule
from rishivan.koonji.registry import seed_registry
from rishivan.koonji.urf import AssertionKind, RegistryKind


@pytest.fixture(scope="module")
def registry():
    return seed_registry()


def _document() -> dict:
    """The prompt's example, as `extract.py` will hand it to the compiler."""
    return {
        k: v for k, v in prompts.RULE_SHAPE.items()
        if k not in prompts.EXTRACTOR_FLAG_KEYS
    }


class TestTheExampleIsReal:
    def test_the_prompt_example_compiles(self, registry):
        """The whole point of this file."""
        rule = parse_rule(_document(), registry)
        assert rule.assertion is AssertionKind.ASSERT_CLAIM

    def test_its_predicates_exist(self, registry):
        from rishivan.koonji.urf import iter_leaves

        rule = parse_rule(_document(), registry)
        for call in iter_leaves(rule.antecedent.expr):
            assert registry.predicate(call.predicate), call.predicate

    def test_its_claim_exists(self, registry):
        rule = parse_rule(_document(), registry)
        assert rule.consequent.claim_id in registry.symbols(RegistryKind.CLAIM)

    def test_its_domains_exist(self, registry):
        rule = parse_rule(_document(), registry)
        known = registry.symbols(RegistryKind.DOMAIN) if hasattr(
            RegistryKind, "DOMAIN") else None
        if known is not None:
            assert set(rule.domains) <= known

    def test_it_round_trips_like_any_other_rule(self, registry):
        """A rule the extractor produces has to survive being written to a file
        and read back, same as a hand-authored one."""
        from rishivan.koonji.emit import round_trips

        ok, why = round_trips(parse_rule(_document(), registry), registry)
        assert ok, why


class TestTheContractSaysWhatTheCodeDoes:
    def test_the_envelope_key_is_named(self):
        """`extract_once` reads `rules`. The model was returning a bare array
        and `reconciled_rules`, because nothing told it otherwise."""
        assert "`rules`" in prompts.OUTPUT_CONTRACT
        assert "Not a bare array" in prompts.OUTPUT_CONTRACT

    def test_the_singular_assertion_key_is_spelled_out(self):
        assert "Not `assertion_kind`" in prompts.OUTPUT_CONTRACT

    def test_the_boolean_operators_are_spelled_out(self):
        assert "not `all_of`" in prompts.OUTPUT_CONTRACT

    def test_the_contract_is_in_the_extractor_prompt(self, registry):
        system = prompts.extractor_system(registry)
        assert prompts.OUTPUT_CONTRACT in system

    def test_the_reconciler_is_told_the_same_key(self):
        assert "`rules`" in prompts.RECONCILER_SYSTEM
        assert "Not `reconciled_rules`" in prompts.RECONCILER_SYSTEM

    def test_the_verifier_is_told_its_envelope(self):
        assert "verdicts" in prompts.VERIFIER_SYSTEM

    def test_the_example_renders_into_the_contract(self):
        """A contract describing a shape it does not show is a contract nobody
        follows."""
        assert json.dumps(prompts.RULE_SHAPE, indent=2)[:40] in prompts.OUTPUT_CONTRACT


class TestClosedVocabularies:
    """Values written out, not described. Each was a discarded extraction."""

    def test_the_magnitude_values_match_the_frame(self):
        import typing

        from rishivan.koonji.urf import ClaimConsequent

        for value in typing.get_args(
            ClaimConsequent.model_fields["magnitude"].annotation
        ):
            assert repr(value) in prompts.OUTPUT_CONTRACT

    def test_the_polarity_values_match_the_frame(self):
        import typing

        from rishivan.koonji.urf import ClaimConsequent

        for value in typing.get_args(
            ClaimConsequent.model_fields["polarity"].annotation
        ):
            assert repr(value) in prompts.OUTPUT_CONTRACT

    def test_the_domain_slot_is_explained(self):
        """The extractor put a claim id there and the rule became unreachable."""
        assert "is NOT a domain" in prompts.OUTPUT_CONTRACT


class TestFlagKeys:
    def test_the_flag_list_is_shared_not_duplicated(self):
        """Three places have to agree: the prompt, the pop in `_to_candidate`,
        and this test. One name, imported."""
        assert "confidence" in prompts.EXTRACTOR_FLAG_KEYS

    def test_flags_are_stripped_before_the_document_is_parsed(self, registry):
        """`confidence` on a rule means something else entirely - the compiler
        expects a mapping there, and a float raises."""
        with pytest.raises(Exception):
            parse_rule(dict(prompts.RULE_SHAPE), registry)

    def test_every_flag_key_maps_to_an_extraction_flag(self):
        from rishivan.koonji.validate import ExtractionFlags

        assert prompts.EXTRACTOR_FLAG_KEYS <= set(ExtractionFlags.model_fields)


class TestClassifierSchema:
    def test_the_gate_field_is_required(self, registry):
        """Everything downstream is gated on `is_rule_bearing`. A classifier
        that omits it means the passage is never read, and the run reports it as
        "not rule bearing" rather than as a failure."""
        assert "is_rule_bearing" in prompts.CLASSIFIER_SCHEMA["required"]

    def test_the_schema_covers_what_the_prompt_asks_for(self):
        described = {
            "assertion_kinds", "is_rule_bearing", "continues_previous",
            "has_unresolved_pronoun", "reference_points",
            "estimated_rule_count", "note",
        }
        assert described == set(prompts.CLASSIFIER_SCHEMA["properties"])


class TestJsonIsRequestedNotHopedFor:
    def test_every_parsing_stage_asks_for_json(self):
        """The original bug in one assertion: four stages parsed JSON and none
        of them asked for it."""
        import inspect

        from rishivan.koonji.extract import Extractor

        for stage in ("classify", "extract_once", "reconcile", "verify"):
            source = inspect.getsource(getattr(Extractor, stage))
            assert "json_schema=" in source, stage

    def test_the_back_translator_does_not(self):
        """It returns a sentence for a human to read. Forcing JSON there would
        wrap prose in quotes for no reason."""
        import inspect

        from rishivan.koonji.extract import Extractor

        assert "json_schema=" not in inspect.getsource(Extractor.back_translate)
