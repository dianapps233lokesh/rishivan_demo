"""The bundle is the reproducibility primitive.

Pin its hash on an inference run and the answer can be rebuilt years later:
same rules, same registry, same index, same evidence graph. That trace is the
whole defensible position - anyone can wire a model to an ephemeris in a month,
and none of them can say why a rule fired in 2026.

Which makes two properties non-negotiable, and both are tested here: identity
must depend on the corpus and not the clock, and a bundle must refuse to load
against a registry it was not compiled with.
"""

import textwrap
from datetime import datetime, timezone

import pytest
import yaml

from rishivan.koonji.bundle import Bundle, BundleMismatch
from rishivan.koonji.compiler import compile_rules
from rishivan.koonji.registry import Registry, seed_registry
from rishivan.koonji.urf import RegistryKind

WEALTH = """
    id: PAR.WEALTH.2L11H.0001
    version: 1.0.0
    status: production
    school: school.parashari
    assertion: assert_claim
    domains: {domain.wealth: 0.95}
    source:
      book: bphs
      edition: bphs.gcs1984.en
      locator: ch34.v12
      quote: "If the lord of the 2nd is in the 11th, wealth accrues."
      review: {reviewer: RB-001, reviewed_at: 2026-08-23}
    when:
      all:
        - occupies_bhava: {subject: 2nd lord, bhava: 11}
    indicates: {claim: wealth.accumulation, polarity: positive, magnitude: strong, text: w}
"""

RESTATEMENT = """
    id: SAR.WEALTH.0044
    version: 1.0.0
    status: production
    school: school.parashari
    assertion: assert_claim
    domains: {domain.wealth: 0.9}
    source:
      book: saravali
      edition: saravali.santhanam.en
      locator: ch10.v3
      quote: "The second lord placed in the eleventh confers riches."
      review: {reviewer: RB-001, reviewed_at: 2026-08-23}
      restates: [PAR.WEALTH.2L11H.0001]
    when:
      all:
        - occupies_bhava: {subject: 2nd lord, bhava: 11}
    indicates: {claim: wealth.accumulation, polarity: positive, magnitude: strong, text: w}
"""

FIXED_TIME = datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc)


def build(registry, sources=(WEALTH,), **kw):
    docs = [yaml.safe_load(textwrap.dedent(s)) for s in sources]
    result = compile_rules(docs, registry).raise_for_errors()
    return Bundle.build(result.rules, registry, result.index, **kw)


@pytest.fixture
def registry():
    return seed_registry()


class TestIdentity:
    def test_identity_is_the_corpus_not_the_clock(self, registry):
        """Rebuilding an unchanged corpus must give the same id, or every build
        looks like a change and a real change stops being visible."""
        a = build(registry, built_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        b = build(registry, built_at=datetime(2027, 6, 30, tzinfo=timezone.utc))
        assert a.manifest.bundle_id == b.manifest.bundle_id

    def test_changing_a_rule_changes_the_id(self, registry):
        changed = WEALTH.replace("bhava: 11", "bhava: 10")
        assert build(registry).manifest.bundle_id != build(
            registry, (changed,)
        ).manifest.bundle_id

    def test_adding_a_rule_changes_the_id(self, registry):
        assert build(registry).manifest.bundle_id != build(
            registry, (WEALTH, RESTATEMENT)
        ).manifest.bundle_id

    def test_rule_order_does_not_change_the_id(self, registry):
        a = build(registry, (WEALTH, RESTATEMENT))
        b = build(registry, (RESTATEMENT, WEALTH))
        assert a.manifest.bundle_id == b.manifest.bundle_id


class TestManifest:
    def test_manifest_counts_what_is_in_the_bundle(self, registry):
        bundle = build(registry, (WEALTH, RESTATEMENT))
        assert bundle.manifest.rule_count == 2
        assert bundle.manifest.variant_count == 2
        assert bundle.manifest.atom_count >= 1

    def test_manifest_records_the_registry_fingerprint(self, registry):
        bundle = build(registry)
        assert bundle.manifest.registry_fingerprint == registry.fingerprint()

    def test_manifest_lists_the_books(self, registry):
        bundle = build(registry, (WEALTH, RESTATEMENT))
        assert bundle.manifest.source_books == ["bphs", "saravali"]


class TestLineage:
    def test_restatements_are_recorded(self, registry):
        """Saravali and BPHS saying the same thing is one piece of evidence.
        The bundle is where that fact has to survive to."""
        bundle = build(registry, (WEALTH, RESTATEMENT))
        assert bundle.lineage["SAR.WEALTH.0044"] == ["PAR.WEALTH.2L11H.0001"]

    def test_independent_rules_carry_no_lineage(self, registry):
        assert build(registry).lineage == {}


class TestRoundTrip:
    def test_save_and_load_preserves_the_corpus(self, registry, tmp_path):
        original = build(registry, (WEALTH, RESTATEMENT))
        path = original.save(tmp_path / "kb.bundle")
        loaded = Bundle.load(path, registry)

        assert loaded.manifest.bundle_id == original.manifest.bundle_id
        assert [r.rule_id for r in loaded.rules] == [r.rule_id for r in original.rules]
        assert loaded.lineage == original.lineage

    def test_a_loaded_index_retrieves_identically(self, registry, tmp_path):
        from rishivan.chart.ephemeris import BirthData, compute_chart

        chart = compute_chart(BirthData(
            year=1990, month=1, day=1, hour=12, minute=0,
            tz_offset_hours=5.5, lat=28.6139, lon=77.2090,
        ))
        original = build(registry, (WEALTH, RESTATEMENT))
        loaded = Bundle.load(original.save(tmp_path / "kb.bundle"), registry)

        when = datetime(2026, 8, 23, 12, 0)
        assert original.index.query(
            original.index.facts_for(chart, when=when)
        ) == loaded.index.query(loaded.index.facts_for(chart, when=when))

    def test_the_file_is_compressed(self, registry, tmp_path):
        path = build(registry).save(tmp_path / "kb.bundle")
        assert path.read_bytes()[:2] == b"\x1f\x8b"


class TestLoadGuards:
    def test_loading_against_a_moved_registry_is_refused(self, registry, tmp_path):
        """A predicate whose signature moved changes the meaning of every rule
        that used it. A store that means something different than it did is
        worse than one that will not load."""
        path = build(registry).save(tmp_path / "kb.bundle")

        drifted = seed_registry()
        drifted.add_symbol(RegistryKind.CLAIM, "wealth.windfall")

        with pytest.raises(BundleMismatch, match="signature has moved"):
            Bundle.load(path, drifted)

    def test_a_future_format_is_refused(self, registry, tmp_path):
        bundle = build(registry)
        payload = bundle.to_payload()
        payload["manifest"]["format"] = 99
        with pytest.raises(BundleMismatch, match="format"):
            Bundle.from_payload(payload, registry)

    def test_a_frame_change_is_refused(self, registry):
        bundle = build(registry)
        payload = bundle.to_payload()
        payload["manifest"]["frame_version"] = "4.0.0"
        with pytest.raises(BundleMismatch, match="frame"):
            Bundle.from_payload(payload, registry)


class TestKillSwitch:
    def test_a_rule_can_be_denied_without_a_rebuild(self, registry):
        """You will need this at three in the morning at least once."""
        bundle = build(registry, (WEALTH, RESTATEMENT))
        before = bundle.manifest.bundle_id
        bundle.deny("SAR.WEALTH.0044")
        assert "SAR.WEALTH.0044" in bundle.denied
        assert bundle.manifest.bundle_id == before, "denying is not a corpus change"


class TestReads:
    def test_lookup_by_id(self, registry):
        bundle = build(registry, (WEALTH, RESTATEMENT))
        assert bundle.rule("SAR.WEALTH.0044").provenance.book_id == "saravali"
        assert bundle.rule("NOPE") is None
