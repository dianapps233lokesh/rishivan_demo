"""Extraction-stage checks: everything that needs the source passage in hand.

The quote-fidelity test is the one to read first. It is string matching, it
costs nothing, and it is the difference between a product that cites verses and
a product that appears to.
"""

import pytest

from rishivan.koonji.validate import (
    ExtractionCandidate,
    ExtractionFlags,
    check_quote_fidelity,
    check_reference_point,
    check_restriction,
    check_scope_inflation,
    is_blocked,
    review_priority,
    review_queue,
    validate_candidate,
)
from rishivan.koonji.urf import (
    Antecedent,
    AssertionKind,
    BoolExpr,
    ClaimConsequent,
    ExtensionProposal,
    Modality,
    PredicateCall,
    Provenance,
    Qualifiers,
    RegistryKind,
    Restriction,
    Rule,
)

PASSAGE = (
    "13. If the 10th Lord is situated in the 11th House, the 11th Lord in the "
    "Ascendant and, Venus in the 10th, the combination makes the native a "
    "possessor of precious stones."
)


def leaf(predicate, **args):
    return BoolExpr(op="leaf", leaf=PredicateCall(predicate=predicate, args=args))


def rule(
    *,
    quote=PASSAGE,
    expr=None,
    claim="wealth.accumulation",
    restriction=Restriction.OPEN,
    modality=Modality.ASSERT,
    domains=None,
):
    return Rule(
        rule_id="BPHS.TEST.0001",
        registry_version="1.0.0",
        school="school.parashari",
        domains=domains if domains is not None else {"domain.wealth": 0.9},
        antecedent=Antecedent(
            expr=expr or leaf("occupies_bhava", subject="lord.bhava.10", bhava="bhava.11")
        ),
        assertion=AssertionKind.ASSERT_CLAIM,
        consequent=ClaimConsequent(
            claim_id=claim, polarity="positive", magnitude="strong", literal_text="…"
        ),
        qualifiers=Qualifiers(
            restriction=restriction,
            modality=modality,
            targets_rule="X" if modality is Modality.CANCEL else None,
        ),
        provenance=Provenance(
            book_id="bphs", edition_id="bphs-gcsharma-vol1",
            locator="ch23.v13", quoted_text=quote,
        ),
    )


def candidate(passage=PASSAGE, **kw):
    flags = kw.pop("flags", ExtractionFlags(confidence=0.8))
    proposals = kw.pop("proposals", [])
    return ExtractionCandidate(
        passage_id="bphs:23:13",
        passage_text=passage,
        rule=rule(**kw),
        flags=flags,
        proposals=proposals,
    )


def proposal(**kw):
    base = dict(
        proposal_id="p1",
        registry=RegistryKind.PREDICATE,
        proposed_id="occupies_bhava_from_arudha",
        evidence_passages=["bphs:23:13"],
        why_insufficient="The Arudha is not a reference point the registry has.",
        proposed_by="extractor@test",
    )
    base.update(kw)
    return ExtensionProposal(**base)


class TestQuoteFidelity:
    """The cheapest check in the pipeline, and the one that matters most."""

    def test_a_verbatim_quote_passes(self):
        assert check_quote_fidelity(candidate()) == []

    def test_a_substring_of_the_passage_passes(self):
        assert check_quote_fidelity(
            candidate(quote="the 11th Lord in the Ascendant")
        ) == []

    def test_a_fabricated_quote_is_blocking(self):
        findings = check_quote_fidelity(
            candidate(quote="Jupiter in the 5th confers many sons.")
        )
        assert is_blocked(findings)
        assert findings[0].code == "quote_not_in_passage"

    def test_a_missing_quote_is_blocking(self):
        assert is_blocked(check_quote_fidelity(candidate(quote="   ")))

    def test_whitespace_and_case_are_forgiven(self):
        assert check_quote_fidelity(
            candidate(quote="  IF THE 10TH LORD IS SITUATED\n  IN THE 11TH HOUSE  ")
        ) == []

    def test_typographic_quotes_are_forgiven(self):
        passage = "The native's wealth increases."
        findings = check_quote_fidelity(
            candidate(passage=passage, quote="The native’s wealth increases.")
        )
        assert findings == []

    def test_punctuation_drift_warns_but_does_not_block(self):
        findings = check_quote_fidelity(
            candidate(quote="If the 10th Lord is situated in the 11th House")
        )
        # exact substring, so clean
        assert findings == []
        findings = check_quote_fidelity(
            candidate(quote="If the 10th Lord is situated in the 11th House!!!")
        )
        assert findings and not is_blocked(findings)

    def test_a_plausible_paraphrase_still_fails(self):
        """This is the whole point. A paraphrase reads correctly and is not what
        the book says."""
        findings = check_quote_fidelity(
            candidate(quote="The tenth lord in the eleventh brings gems.")
        )
        assert is_blocked(findings)


class TestApproximation:
    def test_approximation_is_blocking(self):
        c = candidate(flags=ExtractionFlags(confidence=0.9, approximated=True))
        findings = validate_candidate(c)
        assert is_blocked(findings)
        assert any(f.code == "approximated" for f in findings)

    def test_a_proposal_instead_of_an_approximation_is_fine(self):
        c = candidate(proposals=[proposal()])
        assert not any(f.code == "approximated" for f in validate_candidate(c))


class TestReferencePoint:
    """The single most damaging extraction error, because it never looks wrong."""

    MOON = (
        "If the lord of the 7th from the Moon is placed in the 11th, the native "
        "gains through partnership."
    )

    def test_a_dropped_moon_reference_is_blocking(self):
        c = candidate(passage=self.MOON, quote="the lord of the 7th from the Moon")
        findings = check_reference_point(c)
        assert is_blocked(findings)
        assert "from-Lagna" in findings[0].message

    def test_stating_the_reference_passes(self):
        c = candidate(
            passage=self.MOON,
            quote="the lord of the 7th from the Moon",
            expr=leaf(
                "occupies_bhava_from",
                subject="lord.bhava.07", bhava="bhava.11", reference="ref.moon",
            ),
        )
        assert check_reference_point(c) == []

    def test_a_sun_reference_is_caught_too(self):
        passage = "When Jupiter is in the 9th from the Sun, the native is learned."
        c = candidate(passage=passage, quote="in the 9th from the Sun")
        assert is_blocked(check_reference_point(c))

    def test_an_inexpressible_reference_needs_a_proposal(self):
        passage = "If the 7th from the Arudha Lagna is occupied by a benefic…"
        c = candidate(passage=passage, quote="the 7th from the Arudha Lagna")
        findings = check_reference_point(c)
        assert any(f.code == "reference_point_unsupported" for f in findings)

    def test_a_proposal_satisfies_the_inexpressible_case(self):
        passage = "If the 7th from the Arudha Lagna is occupied by a benefic…"
        c = candidate(
            passage=passage, quote="the 7th from the Arudha Lagna",
            proposals=[proposal()],
        )
        assert not any(
            f.code == "reference_point_unsupported" for f in check_reference_point(c)
        )

    def test_a_self_declared_ambiguity_warns(self):
        c = candidate(flags=ExtractionFlags(
            confidence=0.6, ambiguous_reference_point=True
        ))
        findings = check_reference_point(c)
        assert findings and not is_blocked(findings)

    def test_a_plain_lagna_passage_is_untouched(self):
        assert check_reference_point(candidate()) == []


class TestScopeInflation:
    def test_a_condition_naming_a_planet_absent_from_the_passage_warns(self):
        """'Jupiter in Cancer in the 5th' becoming 'Jupiter in the 5th' widens
        the rule twelvefold, and direct comparison misses it."""
        c = candidate(
            expr=leaf("occupies_bhava", subject="graha.saturn", bhava="bhava.11")
        )
        findings = check_scope_inflation(c)
        assert any(f.code == "scope_inflation" for f in findings)

    def test_a_planet_present_in_the_passage_is_fine(self):
        c = candidate(
            expr=leaf("occupies_bhava", subject="graha.venus", bhava="bhava.10")
        )
        assert check_scope_inflation(c) == []

    def test_lord_references_are_not_flagged(self):
        """`lord.bhava.10` names no planet, so there is nothing to compare."""
        assert check_scope_inflation(candidate()) == []


class TestRestriction:
    def test_a_longevity_claim_must_be_restricted_at_extraction(self):
        c = candidate(claim="longevity.span")
        findings = check_restriction(c)
        assert is_blocked(findings)

    def test_a_restricted_longevity_claim_passes(self):
        c = candidate(claim="longevity.span", restriction=Restriction.NEVER_USER_FACING)
        assert check_restriction(c) == []

    def test_ordinary_claims_need_no_restriction(self):
        assert check_restriction(candidate()) == []


class TestProposals:
    def test_a_proposal_with_no_rationale_is_blocking(self):
        c = candidate(proposals=[proposal(why_insufficient="  ")])
        assert is_blocked(validate_candidate(c))


class TestReviewPriority:
    """Reviewer throughput is the schedule. The order of this queue is a
    scheduling decision, not a nicety."""

    def test_low_confidence_outranks_high(self):
        low = candidate(flags=ExtractionFlags(confidence=0.2))
        high = candidate(flags=ExtractionFlags(confidence=0.95))
        assert review_priority(low) > review_priority(high)

    def test_a_health_domain_rule_outranks_a_wealth_one(self):
        health = candidate(
            flags=ExtractionFlags(confidence=0.5), domains={"domain.health": 0.9}
        )
        wealth = candidate(flags=ExtractionFlags(confidence=0.5))
        assert review_priority(health) > review_priority(wealth)

    def test_a_cancellation_outranks_a_plain_claim(self):
        cancel = candidate(
            flags=ExtractionFlags(confidence=0.5), modality=Modality.CANCEL
        )
        plain = candidate(flags=ExtractionFlags(confidence=0.5))
        assert review_priority(cancel) > review_priority(plain)

    def test_an_extension_proposal_raises_priority(self):
        with_proposal = candidate(
            flags=ExtractionFlags(confidence=0.5), proposals=[proposal()]
        )
        without = candidate(flags=ExtractionFlags(confidence=0.5))
        assert review_priority(with_proposal) > review_priority(without)

    def test_blocked_items_jump_the_queue(self):
        """Waiting will not fix them."""
        blocked = candidate(
            quote="not in the passage at all",
            flags=ExtractionFlags(confidence=0.99),
        )
        confident_and_fine = candidate(flags=ExtractionFlags(confidence=0.05))
        queue = review_queue([confident_and_fine, blocked])
        assert queue[0][1] is blocked

    def test_the_queue_is_sorted_and_carries_its_findings(self):
        queue = review_queue([
            candidate(flags=ExtractionFlags(confidence=0.9)),
            candidate(flags=ExtractionFlags(confidence=0.1)),
        ])
        assert queue[0][0] >= queue[1][0]
        assert all(isinstance(findings, list) for _, _, findings in queue)


class TestWholeCandidate:
    def test_a_clean_extraction_produces_nothing(self):
        assert validate_candidate(candidate()) == []

    def test_findings_accumulate_rather_than_short_circuit(self):
        """One reviewer pass should see everything wrong with a candidate, not
        the first thing wrong with it."""
        c = candidate(
            quote="entirely fabricated",
            claim="longevity.span",
            flags=ExtractionFlags(confidence=0.4, approximated=True),
        )
        codes = {f.code for f in validate_candidate(c)}
        assert {"quote_not_in_passage", "approximated", "restriction_missing"} <= codes
