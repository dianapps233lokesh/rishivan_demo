"""koonji.evidence - firings become claims, with restatements discounted.

One idea in this module does more work than everything else in the engine put
together: **three rules that trace to the same verse are one piece of evidence,
not three.**

BPHS says a thing. Saravali says it again. Jataka Parijata paraphrases both. An
engine that counts those as three corroborating sources will report high
confidence on a single classical assertion, and it will do that everywhere,
systematically, on every claim it makes. That is exactly why astrology products
sound certain about everything: they count paraphrases as corroboration.

So every support edge carries an independence factor, computed from the
`restates` lineage the extractor recorded and the identical-logic clusters the
compiler detected. A restatement keeps a fraction of its weight. A genuinely
independent source - a different school, deriving the same conclusion by a
different doctrine - keeps all of it, and is worth more than three paraphrases.

The second idea, smaller but not optional: **counter-evidence is surfaced, never
suppressed.** A rule that fires against the claim goes into the graph, gets
reported, and lowers the confidence. Every product on the market drops these
because they make the answer messier. Including them is the entire credibility
play, and it costs nothing but nerve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from rishivan.koonji.urf import ClaimConsequent, Corroboration, Rule, iter_leaves
from rishivan.koonji.vm import Firing, Outcome

#: How much a restatement cluster may exceed its strongest member. Not zero - a
#: second author choosing to repeat a statement is weak evidence the tradition
#: took it seriously - but it is a bonus paid ONCE, however many times the verse
#: is repeated.
#:
#: Discounting each restatement individually is not enough, and getting this
#: wrong is subtle: ten paraphrases at 35% each still accumulate to 0.92 under
#: any additive or noisy-OR combination. The tenth repetition of one verse must
#: add exactly nothing, because it is not evidence - it is the same evidence.
INDEPENDENCE_DISCOUNT = 0.35

#: Nothing in this domain is certain, so no arithmetic here may report that it
#: is. A ceiling below 1.0 is not a numerical convenience; it is the claim the
#: system is willing to stand behind.
MAX_CONFIDENCE = 0.97

#: How much a claim's stated force contributes before any adjustment.
MAGNITUDE_WEIGHT = {"slight": 0.15, "moderate": 0.30, "strong": 0.45, "extreme": 0.60}

#: Source authority. S0 is a primary classical text in a scholarly edition;
#: lower tiers are commentaries, popularisations and secondary compilations.
AUTHORITY_WEIGHT = {"S0": 1.0, "S1": 0.85, "S2": 0.70, "S3": 0.50}

#: Predicate -> the kind of evidence a rule using it rests on. Anything unlisted
#: is a D1 statement about houses and grahas, which is the overwhelming majority
#: of the corpus and the right default.
#:
#: Read off the antecedent rather than stored on the rule, because the rule
#: dialect has no tier field - and adding one would mean re-extracting 1,117
#: rules to populate something already derivable from what they say.
TIER_PREDICATES: dict[str, str] = {
    "varga_occupies": "varga",
    "varga_dignity": "varga",
    "dasha_active": "dasha",
    "chara_karaka": "jaimini",
    "rashi_aspects": "jaimini",
}

#: Weakest last. `tier_of` returns the weakest tier a rule touches, so a claim
#: resting partly on a D9 placement is graded as a D9 claim however many D1
#: conditions sit beside it. Taking the strongest instead would let a single
#: house predicate launder every divisional claim in the corpus.
_TIER_ORDER = ("house", "jaimini", "dasha", "varga", "transit")


def tier_of(rule: Rule) -> str:
    """Which kind of evidence this rule is.

    The other half of blueprint §12: the hierarchy table says a varga
    confirmation is worth 0.55 of a house placement, and this is what decides
    which of those a given firing is.
    """
    found = {"house"}
    for call in iter_leaves(rule.antecedent.expr):
        tier = TIER_PREDICATES.get(call.predicate)
        if tier:
            found.add(tier)
    return max(found, key=_TIER_ORDER.index)


#: Certainty language must track the number. A 0.6-confidence claim may not be
#: phrased with certainty, and "will definitely" is not in the vocabulary at all.
BANDS = (
    (0.40, "some_indications", "some indications suggest"),
    (0.65, "moderately_supported", "moderately supported"),
    (0.85, "strongly_indicated", "strongly indicated"),
    (1.01, "consistently_supported", "consistently supported across methods"),
)

#: Below this, the honest answer is that the classical material does not speak
#: clearly to the question. Saying so is a better answer than a confident
#: paragraph, and over months it is what makes the confident answers worth
#: anything.
INSUFFICIENT_BELOW = 0.35


def band_for(confidence: float) -> tuple[str, str]:
    for ceiling, band, phrasing in BANDS:
        if confidence < ceiling:
            return band, phrasing
    return BANDS[-1][1], BANDS[-1][2]


@dataclass(slots=True)
class Support:
    """One rule's contribution to one claim."""

    rule_id: str
    version: str
    school: str
    book: str
    locator: str
    quote: str
    authority_tier: str

    raw_weight: float
    effective_weight: float
    independent: bool
    cluster: str
    """The restatement cluster this rule belongs to. Rules sharing a cluster are
    one piece of evidence between them."""

    tier: str = "house"
    """house | varga | dasha | transit | jaimini.

    Recorded as well as applied. Discounting a divisional claim silently is
    only half the fix - a reader shown a claim has to be able to see that it
    rests on a D9 rather than on the D1 placement it is confirming."""

    polarity: str = "positive"
    against: bool = False
    """Whether this rule denies the claim.
    See the note on polarity in `build_evidence`."""

    @property
    def citation(self) -> str:
        return f"{self.book} {self.locator}".strip()


@dataclass(slots=True)
class Claim:
    claim_id: str
    polarity: str
    support: list[Support] = field(default_factory=list)
    against: list[Support] = field(default_factory=list)
    confidence: float = 0.0
    band: str = "some_indications"
    phrasing: str = "some indications suggest"

    independent_sources: int = 0
    corroboration_required: Optional[int] = None
    corroboration_met: bool = True

    requires_activation: bool = False
    """A promise is not an event. True when every supporting rule says the
    result manifests only in a particular period."""

    def citations(self) -> list[str]:
        seen: list[str] = []
        for s in self.support + self.against:
            c = s.citation
            if c and c not in seen:
                seen.append(c)
        return seen

    @property
    def has_counterevidence(self) -> bool:
        return bool(self.against)


@dataclass(slots=True)
class EvidenceGraph:
    claims: list[Claim] = field(default_factory=list)

    fired: list[str] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)
    indeterminate: list[str] = field(default_factory=list)
    withheld: list[str] = field(default_factory=list)
    not_applicable: list[str] = field(default_factory=list)

    @property
    def max_confidence(self) -> float:
        return max((c.confidence for c in self.claims), default=0.0)

    def insufficient(self) -> bool:
        """The path most products get wrong.

        No evidence, or nothing above the floor, is a real answer and must be
        given as one - naming what was examined and why it was inconclusive. It
        is also not a billable interaction.
        """
        return not self.claims or self.max_confidence < INSUFFICIENT_BELOW

    def ranked(self) -> list[Claim]:
        return sorted(self.claims, key=lambda c: -c.confidence)

    def summary(self) -> dict[str, int]:
        return {
            "claims": len(self.claims),
            "fired": len(self.fired),
            "cancelled": len(self.cancelled),
            "indeterminate": len(self.indeterminate),
            "withheld": len(self.withheld),
            "not_applicable": len(self.not_applicable),
        }


# ==========================================================================
# Independence clustering
# ==========================================================================


def cluster_restatements(
    rules: Iterable[Rule], lineage: Optional[dict[str, list[str]]] = None
) -> dict[str, str]:
    """rule id -> cluster id, over the union of two signals.

    A rule is a restatement of another when the extractor recorded it as one, or
    when the compiler finds their logic identical. The second catches what the
    first misses: two independently extracted rules from two books with the same
    condition core and the same claim are the same statement, whether or not
    anybody noticed.
    """
    rules = list(rules)
    parent: dict[str, str] = {r.rule_id: r.rule_id for r in rules}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            # Lower id wins, so cluster names are stable across builds.
            lo, hi = sorted((ra, rb))
            parent[hi] = lo

    known = {r.rule_id for r in rules}

    for rule in rules:
        for other in rule.provenance.restates:
            if other in known:
                union(rule.rule_id, other)
    for rule_id, restates in (lineage or {}).items():
        if rule_id not in known:
            continue
        for other in restates:
            if other in known:
                union(rule_id, other)

    # Identical logic within one school is a restatement even when nobody said
    # so. Across schools it is not: two doctrines reaching the same condition by
    # different reasoning is real corroboration, and the most valuable kind.
    by_logic: dict[tuple[str, str], list[str]] = {}
    for rule in rules:
        by_logic.setdefault((rule.school, rule.content_hash()), []).append(rule.rule_id)
    for group in by_logic.values():
        for other in group[1:]:
            union(group[0], other)

    return {r.rule_id: find(r.rule_id) for r in rules}


# ==========================================================================
# Graph assembly
# ==========================================================================


def _raw_weight(rule: Rule, firing: Firing) -> float:
    """How much this firing contributes.

    Deliberately NOT scaled by the rule's domain weights. Those are a relevance
    signal for routing - how much this rule has to say about wealth as opposed
    to career - and multiplying confidence by them conflates "is this about what
    you asked" with "is this well supported". A tangential rule should be
    dropped for irrelevance, not quietly reported as weak evidence.
    """
    consequent = rule.consequent
    assert isinstance(consequent, ClaimConsequent)
    base = MAGNITUDE_WEIGHT.get(consequent.magnitude, 0.30)
    authority = AUTHORITY_WEIGHT.get(rule.provenance.authority_tier, 0.50)
    weight = base * authority * max(firing.strength, 0.0)
    return min(weight, 0.95)


def _by_cluster(edges: Iterable[Support]) -> list[float]:
    """One weight per restatement cluster, so combination cannot double count.

    This is where the property actually holds. Combining per-edge - even with
    every edge discounted - lets repetition accumulate, which is the failure
    mode being designed out.
    """
    totals: dict[str, float] = {}
    for edge in edges:
        totals[edge.cluster] = totals.get(edge.cluster, 0.0) + edge.effective_weight
    return list(totals.values())


def _combine(weights: Iterable[float]) -> float:
    """Noisy-OR. Independent evidence accumulates with diminishing returns and
    never reaches certainty, which is the correct shape for this domain."""
    product = 1.0
    for w in weights:
        product *= 1.0 - min(max(w, 0.0), 0.99)
    return 1.0 - product


def build_evidence(
    firings: Iterable[Firing],
    rules: Iterable[Rule],
    *,
    lineage: Optional[dict[str, list[str]]] = None,
    for_claims: Optional[set[str]] = None,
    tier_weights: Optional[dict[str, float]] = None,
    min_independent: Optional[int] = None,
) -> EvidenceGraph:
    """Assemble the graph. Deterministic - no model is involved at any point.

    `tier_weights` and `min_independent` come from the question's
    `EvidenceHierarchy` (blueprint §12). Both default to None and both must
    leave every existing caller's numbers untouched when unset - that is the
    first thing `test_evidence_tiers.py` asserts.

    Note what is weighted and what is not. A firing's **tier** scales its
    weight, because how directly evidence bears on the question is a statement
    about support. A rule's **domain weights** deliberately do not - see
    `_raw_weight`. Relevance and support are different axes, and multiplying
    one into the other reports a tangential rule as a weak one.
    """
    rules = list(rules)
    by_id = {r.rule_id: r for r in rules}
    clusters = cluster_restatements(rules, lineage)

    graph = EvidenceGraph()
    supports: dict[str, list[Support]] = {}
    polarity: dict[str, str] = {}
    requires: dict[str, list[bool]] = {}
    corroboration: dict[str, list[int]] = {}

    for firing in firings:
        rule = by_id.get(firing.rule_id)
        if rule is None:
            continue

        bucket = {
            Outcome.FIRED: graph.fired,
            Outcome.CANCELLED: graph.cancelled,
            Outcome.INDETERMINATE: graph.indeterminate,
            Outcome.WITHHELD: graph.withheld,
            Outcome.NOT_APPLICABLE: graph.not_applicable,
        }[firing.outcome]
        bucket.append(firing.rule_id)

        # A cancelled rule contributes nothing. The rule that cancelled it
        # contributes its own claim, if it has one - which is how "the yoga is
        # broken" becomes a finding rather than a silence.
        if firing.outcome is not Outcome.FIRED:
            continue
        if not isinstance(rule.consequent, ClaimConsequent):
            continue

        claim_id = rule.consequent.claim_id
        if for_claims is not None and claim_id not in for_claims:
            continue

        # POLARITY IS A STANCE, NOT A VALENCE. `positive` means this rule
        # asserts the claim; `negative` means it denies it. It does not mean the
        # outcome is pleasant. A verse saying "the native has no gain despite
        # effort" asserts `wealth.loss` and is therefore positive on it - reading
        # polarity as valence would file every unwelcome finding as evidence
        # against itself and zero out half the corpus.
        against = rule.consequent.polarity == "negative"
        supports.setdefault(claim_id, []).append(
            Support(
                rule_id=rule.rule_id,
                version=rule.version,
                school=rule.school,
                book=rule.provenance.book_id,
                locator=rule.provenance.locator,
                quote=rule.provenance.quoted_text,
                authority_tier=rule.provenance.authority_tier,
                raw_weight=(
                    _raw_weight(rule, firing)
                    * (tier_weights or {}).get(tier_of(rule), 1.0)
                ),
                effective_weight=0.0,  # filled in below, once clusters are known
                independent=True,
                cluster=clusters.get(rule.rule_id, rule.rule_id),
                tier=tier_of(rule),
                polarity=rule.consequent.polarity,
                against=against,
            )
        )
        polarity.setdefault(claim_id, rule.consequent.polarity)
        requires.setdefault(claim_id, []).append(rule.qualifiers.requires_activation)
        if rule.qualifiers.corroboration is Corroboration.REQUIRES_N:
            corroboration.setdefault(claim_id, []).append(
                rule.qualifiers.corroboration_n or 2
            )

    for claim_id, edges in supports.items():
        # A cluster is one piece of evidence and contributes one weight. The
        # strongest member carries it; the second gets a single repetition
        # bonus; every further restatement contributes nothing at all.
        #
        # Attribution is exact - the edges' effective weights sum to the
        # cluster's weight - so the trace shows a reader precisely where the
        # number came from, including the zeroes.
        seen_cluster: set[str] = set()
        bonus_paid: set[str] = set()
        for edge in sorted(edges, key=lambda e: (-e.raw_weight, e.rule_id)):
            if edge.cluster not in seen_cluster:
                seen_cluster.add(edge.cluster)
                edge.independent = True
                edge.effective_weight = edge.raw_weight
            elif edge.cluster not in bonus_paid:
                bonus_paid.add(edge.cluster)
                edge.independent = False
                edge.effective_weight = edge.raw_weight * INDEPENDENCE_DISCOUNT
            else:
                edge.independent = False
                edge.effective_weight = 0.0

        supporting = [e for e in edges if not e.against]
        opposing = [e for e in edges if e.against]

        # Evidence against something nothing asserted is not a claim, it is a
        # mis-authored polarity. Emitting it would put a zero-confidence claim in
        # front of a reader with counter-evidence and no claim to counter.
        if not supporting:
            continue

        support_score = _combine(_by_cluster(supporting))
        against_score = _combine(_by_cluster(opposing))
        confidence = min(support_score * (1.0 - against_score), MAX_CONFIDENCE)

        independent_sources = len(
            {e.cluster for e in supporting if e.independent}
        )
        # The stricter of the rule author's own requirement and the domain's
        # floor. A hierarchy asking for two sources may not relax a rule that
        # demanded three, and a rule that asked for nothing does not exempt a
        # longevity claim from the floor its domain sets.
        required = max(
            corroboration.get(claim_id, [0]) + [min_independent or 0], default=0
        )
        met = independent_sources >= required if required else True
        if not met:
            # Stated corroboration is a floor the author set deliberately. Not
            # meeting it does not delete the claim; it caps how loudly it may be
            # put, which is what the author was asking for.
            confidence = min(confidence, INSUFFICIENT_BELOW)

        band, phrasing = band_for(confidence)
        graph.claims.append(
            Claim(
                claim_id=claim_id,
                polarity=polarity.get(claim_id, "positive"),
                support=supporting,
                against=opposing,
                confidence=round(confidence, 4),
                band=band,
                phrasing=phrasing,
                independent_sources=independent_sources,
                corroboration_required=required or None,
                corroboration_met=met,
                requires_activation=bool(requires.get(claim_id))
                and all(requires[claim_id]),
            )
        )

    graph.claims.sort(key=lambda c: -c.confidence)
    return graph
