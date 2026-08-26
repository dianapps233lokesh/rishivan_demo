"""Rules back out to YAML, and the round trip that keeps the two in step.

`emit_doc` is the inverse of `parse_rule`, and an inverse that is only
approximately an inverse is worse than none: reviewers would edit files meaning
one thing while the engine executed another, and the drift would surface months
later as rules that quietly stopped firing.

So the property under test throughout is

    parse_rule(emit_doc(rule)) == rule

by content hash, on every assertion kind and on every rule in the corpus.
"""

from pathlib import Path

import pytest
import yaml

from rishivan.koonji.compiler import compile_path, compile_rules, parse_rule
from rishivan.koonji.emit import (
    dump_rules,
    emit_doc,
    emit_expr,
    group_by_domain,
    quote_sha256,
    round_trips,
    write_grouped,
    write_rules,
)
from rishivan.koonji.engine import DEFAULT_RULES_DIR
from rishivan.koonji.registry import seed_registry

SEED_RULES = DEFAULT_RULES_DIR / "parashari"


@pytest.fixture(scope="module")
def registry():
    return seed_registry()


@pytest.fixture(scope="module")
def seed(registry):
    return compile_path(SEED_RULES, registry).raise_for_errors().rules


class TestRoundTrip:
    def test_every_hand_written_rule_survives(self, seed, registry):
        """The eight rules a person typed cover six of the seven assertion
        kinds between them. If the emitter can reproduce those it can reproduce
        anything the extractor will produce."""
        for rule in seed:
            ok, why = round_trips(rule, registry)
            assert ok, f"{rule.rule_id}: {why}"

    def test_the_content_hash_is_what_is_compared(self, seed, registry):
        """Not equality of the dumped text. Two documents can differ in key
        order and mean the same rule; only the hash knows that."""
        rule = seed[0]
        again = parse_rule(emit_doc(rule), registry)
        assert again.content_hash() == rule.content_hash()

    def test_emitted_yaml_parses_as_yaml(self, seed):
        docs = yaml.safe_load(dump_rules(seed))
        assert len(docs) == len(seed)
        assert docs[0]["id"] == seed[0].rule_id

    def test_a_whole_file_recompiles_from_disk(self, seed, registry, tmp_path):
        """The end of the pipeline: write it out, read it back, get the same
        rules. Anything less and the files on disk are decoration."""
        write_rules(seed, tmp_path / "out.yaml")
        again = compile_path(tmp_path, registry).raise_for_errors().rules
        assert {r.content_hash() for r in again} == {r.content_hash() for r in seed}


class TestExpressions:
    def test_a_conjunction(self):
        doc = {"all": [{"combust": {"subject": "graha.sun"}},
                       {"retrograde": {"subject": "graha.mars"}}]}
        assert emit_expr(_expr(doc)) == doc

    def test_a_disjunction(self):
        doc = {"any": [{"combust": {"subject": "graha.sun"}},
                       {"combust": {"subject": "graha.moon"}}]}
        assert emit_expr(_expr(doc)) == doc

    def test_a_negation(self):
        doc = {"not": {"combust": {"subject": "graha.sun"}}}
        assert emit_expr(_expr(doc)) == doc

    def test_an_inline_negation_stays_inline(self):
        """`negated: true` on a call and a `not:` wrapper are different shapes
        that mean the same thing. Emitting one as the other still round-trips,
        but it churns every generated file on an unrelated change."""
        doc = {"combust": {"subject": "graha.sun", "negated": True}}
        assert emit_expr(_expr(doc)) == doc

    def test_a_count(self):
        doc = {"count": {"of": [{"in_kendra": {"subject": "graha.jupiter"}},
                                {"in_kendra": {"subject": "graha.venus"}}],
                         "n": 2}}
        assert emit_expr(_expr(doc)) == doc

    def test_a_count_with_a_non_default_operator_keeps_it(self):
        doc = {"count": {"of": [{"in_kendra": {"subject": "graha.jupiter"}}],
                         "n": 1, "op": "lte"}}
        assert emit_expr(_expr(doc)) == doc

    def test_the_default_count_operator_is_omitted(self):
        """`gte` is the default. Spelling it out on every rule hides the ones
        that differ."""
        emitted = emit_expr(_expr({"count": {"of": [{"in_kendra": {"subject": "graha.sun"}}],
                                             "n": 1, "op": "gte"}}))
        assert "op" not in emitted["count"]


class TestDocumentShape:
    def test_defaults_are_omitted(self, seed):
        """A file where every rule spells out `binding: literal` is a file where
        the one rule that differs is invisible."""
        doc = emit_doc(seed[0])
        assert "binding" not in doc
        assert "restriction" not in doc
        assert "observables" not in doc

    def test_a_non_default_modality_is_written(self, seed):
        cancel = next(r for r in seed if r.qualifiers.targets_rule)
        doc = emit_doc(cancel)
        assert doc["modality"] == "cancel"
        assert doc["targets"] == cancel.qualifiers.targets_rule

    def test_the_quote_hash_is_always_present(self, seed):
        """Stored even where the licence forbids storing the quote. It is what
        ties a claim to a verse in an edition we may not reproduce."""
        for rule in seed:
            doc = emit_doc(rule)
            assert doc["source"]["quote_sha256"]

    def test_the_hash_is_of_the_quote(self, seed):
        doc = emit_doc(seed[0])
        assert doc["source"]["quote_sha256"] == quote_sha256(doc["source"]["quote"])

    def test_review_state_is_never_silently_dropped(self, seed):
        for rule in seed:
            assert emit_doc(rule)["source"]["review"]


class TestFiles:
    def test_no_yaml_anchors(self, seed):
        """Two rules from one verse share a quote object. `safe_dump` would
        emit `&id001`/`*id001` and hand the reviewer a puzzle."""
        text = dump_rules(seed)
        assert "&id0" not in text
        assert "*id0" not in text

    def test_a_header_is_commented(self, seed):
        text = dump_rules(seed[:1], header="GENERATED\ndo not edit")
        assert text.startswith("# GENERATED\n# do not edit\n")
        assert yaml.safe_load(text)

    def test_grouping_is_by_heaviest_domain(self):
        """How a reviewer looks for a rule - "show me the marriage rules" - not
        by which book it came from."""
        docs = [
            _doc("A", {"domain.wealth": 0.9, "domain.career": 0.3}),
            _doc("B", {"domain.career": 0.9}),
        ]
        rules = compile_rules(docs, seed_registry()).raise_for_errors().rules
        grouped = group_by_domain(rules)
        assert [r.rule_id for r in grouped["wealth"]] == ["A"]
        assert [r.rule_id for r in grouped["career"]] == ["B"]

    def test_an_untagged_rule_lands_somewhere_visible(self):
        rules = compile_rules([_doc("C", {})], seed_registry()).raise_for_errors().rules
        assert "general" in group_by_domain(rules)

    def test_write_grouped_produces_one_file_per_domain(self, seed, tmp_path):
        written = write_grouped(seed, tmp_path)
        assert written
        assert all(p.suffix == ".yaml" for p in written)
        assert {p.parent for p in written} == {tmp_path}

    def test_writing_overwrites_rather_than_appends(self, seed, tmp_path):
        """These are generated artefacts. Appending would grow duplicates on
        every run, and a duplicated rule fires twice - which reads as two
        independent sources agreeing."""
        path = tmp_path / "out.yaml"
        write_rules(seed, path)
        first = path.read_text()
        write_rules(seed, path)
        assert path.read_text() == first


class TestRegressions:
    def test_a_reference_symbol_resolves_to_itself(self):
        """`resolve_symbol("from_lagna")` returns `ref.lagna`, which the
        resolver then could not read back - so a rule using
        `occupies_bhava_from` emitted fine and would not recompile. Idempotence
        of the resolver is what the whole round trip rests on."""
        from rishivan.koonji.registry import resolve_symbol

        for canonical in ("ref.lagna", "ref.moon", "ref.sun"):
            assert resolve_symbol(canonical) == canonical

    def test_a_rule_using_a_reference_round_trips(self, registry):
        doc = _doc("REF", {"domain.wealth": 0.9})
        doc["when"] = {"occupies_bhava_from": {
            "subject": "graha.jupiter", "bhava": 5, "reference": "from_moon"}}
        rule = parse_rule(doc, registry)
        ok, why = round_trips(rule, registry)
        assert ok, why


# -- helpers ---------------------------------------------------------------


def _expr(node):
    from rishivan.koonji.compiler import _parse_expr

    return _parse_expr(node, "T")


def _doc(rule_id: str, domains: dict) -> dict:
    return {
        "id": rule_id,
        "status": "candidate",
        "school": "school.parashari",
        "assertion": "assert_claim",
        "domains": domains,
        "source": {"book": "bphs", "edition": "bphs-gcsharma-vol1",
                   "locator": "ch1.v1", "quote": "a verse"},
        # Not the Sun: pass 7 rejects "the Sun is combust itself", which is
        # the realizability check doing its job on a lazy fixture.
        "when": {"combust": {"subject": "graha.mars"}},
        "indicates": {"claim": "wealth.accumulation", "polarity": "positive",
                      "magnitude": "moderate", "text": "wealth"},
    }
