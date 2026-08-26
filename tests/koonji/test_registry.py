"""The registry is additive only. That is the whole contract.

The moment an entry can be redefined in place, every rule extracted before the
redefinition means something different than it did, silently, and no test in
the suite catches it. So the refusal to overwrite is tested first.
"""

import pytest

from rishivan.koonji.registry import (
    CAPTURABLE_OBSERVABLES,
    DuplicateEntry,
    NEVER_USER_FACING_CLAIMS,
    ProposalQueue,
    Registry,
    SEED_PREDICATES,
    seed_registry,
)
from rishivan.koonji.urf import ExtensionProposal, RegistryEntry, RegistryKind


def proposal(pid="p1", proposed="prashna.observes_touch", passages=("prasnamarga:2:26",), **kw):
    base = dict(
        proposal_id=pid,
        registry=RegistryKind.PREDICATE,
        proposed_id=proposed,
        signature={"subject": "querent", "object": "body_part", "returns": "bool"},
        evidence_passages=list(passages),
        occurrences=len(passages),
        nearest_existing="occupies_bhava",
        why_insufficient=(
            "The antecedent is a physical observation of the querent at query "
            "time, not a property of any chart."
        ),
        proposed_by="extractor@test",
    )
    base.update(kw)
    return ExtensionProposal(**base)


class TestAdditiveOnly:
    def test_redefining_a_symbol_is_refused(self):
        reg = Registry()
        reg.add_symbol(RegistryKind.CLAIM, "wealth.gain", label="original")
        with pytest.raises(DuplicateEntry, match="supersede it, never edit it"):
            reg.add(
                RegistryEntry(
                    registry=RegistryKind.CLAIM,
                    entry_id="wealth.gain",
                    label="quietly different",
                    introduced_in="1.0.0",
                    introduced_by="seed",
                )
            )

    def test_republishing_the_identical_entry_is_fine(self):
        """Idempotent loads must not blow up; only *changes* are refused."""
        reg = Registry()
        reg.add_symbol(RegistryKind.CLAIM, "wealth.gain", label="same")
        reg.add_symbol(RegistryKind.CLAIM, "wealth.gain", label="same")
        assert len(reg.symbols(RegistryKind.CLAIM)) == 1

    def test_changing_a_predicate_signature_is_refused(self):
        """Changing a signature changes the meaning of every rule that used it."""
        from rishivan.koonji.registry import ArgSpec, PredicateSpec

        reg = Registry()
        reg.add_predicate(
            PredicateSpec(
                entry_id="occupies_bhava",
                args=[ArgSpec(name="subject", kinds=("graha_ref",))],
            )
        )
        with pytest.raises(DuplicateEntry, match="different"):
            reg.add_predicate(
                PredicateSpec(
                    entry_id="occupies_bhava",
                    args=[
                        ArgSpec(name="subject", kinds=("graha_ref",)),
                        ArgSpec(name="bhava", kinds=("bhava",)),
                    ],
                )
            )


class TestSeed:
    def test_seed_is_self_consistent(self):
        reg = seed_registry()
        assert reg.symbols(RegistryKind.PREDICATE) == {p.entry_id for p in SEED_PREDICATES}

    def test_derived_predicates_declare_a_tier(self):
        """A derived fact at tier 0 would run before the facts it reads."""
        reg = seed_registry()
        for name, spec in reg.derived_predicates().items():
            assert spec.tier >= 1, f"{name} is derived but sits at tier 0"

    def test_jaimini_predicates_are_school_scoped(self):
        """Unscoped, a Parashari rule could name chara_karaka and nothing would
        object until an astrologer read the output."""
        reg = seed_registry()
        assert reg.predicate("chara_karaka").schools == ("school.jaimini",)
        assert reg.predicate("rashi_aspects").schools == ("school.jaimini",)
        assert reg.predicate("occupies_bhava").schools == ()

    def test_comparative_and_numeric_predicates_are_not_indexable(self):
        """Indexing them would build a core the fact set can never satisfy,
        which is a false negative - the one error class the index forbids."""
        reg = seed_registry()
        for name in ("strength", "stronger_than", "occupant_count"):
            assert reg.predicate(name).indexable is False

    def test_uncapturable_observables_are_still_registered(self):
        """Prasna's breath and touch are registered so those rules can be
        extracted honestly and then withheld, rather than approximated into
        chart conditions or silently dropped."""
        reg = seed_registry()
        observables = reg.symbols(RegistryKind.OBSERVABLE)
        assert {"breath", "touch", "omen"} <= observables
        assert {"breath", "touch", "omen"}.isdisjoint(CAPTURABLE_OBSERVABLES)

    def test_longevity_claim_is_flagged_never_user_facing(self):
        assert "longevity.span" in NEVER_USER_FACING_CLAIMS

    def test_fingerprint_moves_when_a_signature_moves(self):
        """The bundle manifest pins this, so a bundle can never load against a
        registry it was not compiled with."""
        a = seed_registry()
        before = a.fingerprint()
        a.add_symbol(RegistryKind.CLAIM, "wealth.windfall")
        assert a.fingerprint() != before

    def test_fingerprint_is_stable_across_builds(self):
        assert seed_registry().fingerprint() == seed_registry().fingerprint()


class TestProposalQueue:
    def test_a_single_sighting_does_not_reach_a_reviewer(self):
        """Proposed once, it is usually an extraction artefact."""
        q = ProposalQueue()
        q.submit(proposal())
        assert q.ready_for_review() == []

    def test_repeated_sightings_surface(self):
        q = ProposalQueue()
        for i in range(3):
            q.submit(proposal(pid=f"p{i}", passages=(f"prasnamarga:2:{26 + i}",)))
        ready = q.ready_for_review()
        assert len(ready) == 1
        assert ready[0].occurrences == 3

    def test_clustering_is_by_signature_not_by_name(self):
        """Two extractors will invent two names for the same missing concept."""
        q = ProposalQueue()
        q.submit(proposal(pid="a", proposed="prashna.observes_touch", passages=("p:1",)))
        q.submit(proposal(pid="b", proposed="querent_touches_part", passages=("p:2",)))
        assert len(q) == 1

    def test_parked_passages_are_never_lost(self):
        """A gap can be slow to surface. It can never be silently dropped."""
        q = ProposalQueue()
        q.submit(proposal(passages=("p:1", "p:2")))
        assert q.parked_passages() == {"p:1", "p:2"}

    def test_resolved_proposals_release_their_passages_for_rerun(self):
        q = ProposalQueue()
        p = q.submit(proposal(passages=("p:1",)))
        p.status = "approved"
        assert q.parked_passages() == set()

    def test_review_queue_is_ordered_by_frequency(self):
        q = ProposalQueue()
        for i in range(3):
            q.submit(proposal(pid=f"a{i}", proposed="rare", passages=(f"x:{i}",)))
        for i in range(8):
            q.submit(
                proposal(
                    pid=f"b{i}",
                    proposed="common",
                    signature={"subject": "querent", "returns": "direction"},
                    passages=(f"y:{i}",),
                )
            )
        ready = q.ready_for_review()
        assert [p.occurrences for p in ready] == [8, 3]
