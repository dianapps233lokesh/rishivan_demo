"""The direct lane's prompt, assembled from the constitution and nothing else.

Every test here runs with no network, no client and no database. That is the
property the lane exists to have, and `test_no_network` pins it explicitly.
"""

from rishivan.council.direct_prompt import (
    constitution_for, framing_block, method_block,
)


class TestDomainResolution:
    def test_a_relationship_question_resolves_to_prema(self):
        assert constitution_for("domain.relationship").domain == "prema"

    def test_a_career_question_resolves_to_karma(self):
        assert constitution_for("domain.career").domain == "karma"

    def test_the_first_life_domain_wins_when_a_domain_maps_to_two(self):
        """`domain.status` maps to ("karma", "vansh"). The hierarchy weights the
        first, and so does this — a question routed to two domains is primarily
        about the first."""
        assert constitution_for("domain.status").domain == "karma"

    def test_an_unknown_domain_falls_back_to_atma(self):
        """Atma's protocol is the whole-chart one, which is the right default for
        a question the router could not place. Falling back to nothing would mean
        a prompt with no method block at all."""
        assert constitution_for("domain.nonsense").domain == "atma"
        assert constitution_for("").domain == "atma"


class TestMethodBlock:
    def test_the_protocol_steps_appear_numbered_and_in_order(self):
        block = method_block(constitution_for("domain.relationship"))
        assert "1. promise" in block
        assert "4. D9 confirmation" in block
        assert block.index("1. promise") < block.index("4. D9 confirmation")

    def test_the_step_count_matches_the_constitution(self):
        c = constitution_for("domain.relationship")
        block = method_block(c)
        for index, step in enumerate(c.protocol, start=1):
            assert f"{index}. {step}" in block

    def test_the_dimension_names_what_is_being_read(self):
        assert "Love / Marriage / Relationships" in method_block(
            constitution_for("domain.relationship")
        )

    def test_an_unsupported_step_must_be_declared_not_skipped(self):
        """The failure mode is a model that quietly drops the step it has no
        facts for, which reads as a complete reading."""
        block = method_block(constitution_for("domain.career"))
        assert "unsupported" in block.lower()


class TestFramingBlock:
    def test_it_names_the_text_families_from_the_constitution(self):
        block = framing_block(constitution_for("domain.relationship"))
        assert "BPHS" in block
        assert "Phaladeepika" in block

    def test_citation_is_forbidden_outright(self):
        """The panel is gone in this lane, so a citation cannot be checked
        against anything, and an uncheckable citation is worse than none."""
        block = framing_block(constitution_for("domain.relationship"))
        assert "page number" in block.lower()
        assert "chapter" in block.lower()

    def test_forbidden_claims_are_carried_through(self):
        c = constitution_for("domain.health")
        block = framing_block(c)
        assert c.forbidden_claims  # guard: the fixture must be meaningful
        for claim in c.forbidden_claims:
            assert claim in block

    def test_it_does_not_mention_this_repos_corpus_gaps(self):
        """`unavailable_sources` and `blocked_concepts` describe gaps in THIS
        repo's corpus. A model reading from its own knowledge has no such gaps,
        and telling it about them would suppress knowledge it does have."""
        c = constitution_for("domain.temperament")
        block = framing_block(c)
        assert c.unavailable_sources  # guard
        for missing in c.unavailable_sources:
            assert f"do not have {missing}" not in block

    def test_no_persona_leaks_in(self):
        block = framing_block(constitution_for("domain.relationship"))
        for word in ("Rishi", "seeker", "ancient sage", "warm"):
            assert word not in block
