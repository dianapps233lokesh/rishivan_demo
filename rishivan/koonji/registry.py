"""koonji.registry - the open half of the frame.

The frame is closed; this grows forever. Every symbol a rule can name lives
here, and the one rule that governs it is: **additive only**. An entry is never
edited and never deleted, only superseded. A rule extracted under registry v14
must execute identically under v40, or historical answers stop reproducing and
the prediction ledger becomes fiction.

This module is also the tightest coupling in the engine. The predicate registry
is simultaneously:

  * the vocabulary the fact compiler emits atoms in    (facts.py)
  * the vocabulary the rule VM evaluates               (vm.py)
  * the vocabulary the extractor is allowed to use     (extract.py)

A rule naming a predicate this module does not describe matches no chart and
raises nothing - it degrades silently, which is the failure mode the whole
extension protocol exists to prevent. So closure is checked as a hard compiler
error, never a warning.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Iterable, Literal, Optional

from pydantic import BaseModel, Field

from rishivan.koonji.urf import (
    REVIEW_THRESHOLD,
    ExtensionProposal,
    RegistryEntry,
    RegistryKind,
)

REGISTRY_VERSION = "1.0.0"


# ==========================================================================
# Entity kinds - the type system the compiler's type-check pass uses
# ==========================================================================

#: A term that resolves to a graha at fact-compile time. Four forms:
#:   graha.saturn        a literal body
#:   lord.bhava.10       the lord of the tenth house
#:   karaka.putra        the natural significator for children
#:   chara.amatyakaraka  a Jaimini variable significator (derived, tier 3)
GRAHA_REF = "graha_ref"

BHAVA = "bhava"
RASHI = "rashi"
NAKSHATRA = "nakshatra"
DIGNITY = "dignity"
BAND = "band"
VARGA = "varga"
DASHA_SYSTEM = "dasha_system"
DASHA_LEVEL = "dasha_level"
NATURE = "nature"
FRIENDSHIP = "friendship"
NUMBER = "number"
OPERATOR = "operator"
DISTANCE = "distance"
REFERENCE = "reference"


class ArgSpec(BaseModel):
    name: str
    kinds: tuple[str, ...]
    optional: bool = False


class PredicateSpec(BaseModel):
    """One predicate. The signature is load-bearing in three places at once."""

    entry_id: str
    args: list[ArgSpec]
    evaluation: Literal["atom", "numeric", "count"] = "atom"
    indexable: bool = Field(
        default=True,
        description="False for predicates whose truth cannot be decided by set "
        "membership. Non-indexable predicates never gate retrieval; "
        "they are evaluated after the candidate set is built, which "
        "is what preserves the no-false-negatives invariant.",
    )
    derived: bool = Field(
        default=False,
        description="True when a DERIVE_FACT rule produces this, not the chart "
        "compiler. Contested between schools, so it is sourced and "
        "versioned like any other rule.",
    )
    tier: int = Field(default=0, description="Stratification tier for derived facts.")
    schools: tuple[str, ...] = Field(
        default=(),
        description="Empty means every school. Non-empty restricts it, and a rule "
        "in another school naming it is a cross-school leak - caught "
        "at compile time, not in production.",
    )
    functional: bool = Field(
        default=False,
        description="True when the final argument is uniquely determined by the "
        "earlier ones - a graha occupies exactly one bhava, holds "
        "exactly one dignity. The contradiction pass uses this: two "
        "different values for the same subject inside one conjunct is "
        "unsatisfiable, and a rule that can never fire is dead weight "
        "you will never notice, because you cannot see a rule's absence.",
    )
    label: str = ""

    def arity(self) -> int:
        return len(self.args)


# ==========================================================================
# Seed entities
# ==========================================================================

GRAHAS = (
    "sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn", "rahu", "ketu",
)

RASHIS = (
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
)

NAKSHATRAS = (
    "ashwini", "bharani", "krittika", "rohini", "mrigashira", "ardra",
    "punarvasu", "pushya", "ashlesha", "magha", "purva_phalguni",
    "uttara_phalguni", "hasta", "chitra", "swati", "vishakha", "anuradha",
    "jyeshtha", "mula", "purva_ashadha", "uttara_ashadha", "shravana",
    "dhanishta", "shatabhisha", "purva_bhadrapada", "uttara_bhadrapada", "revati",
)

DIGNITIES = ("exalted", "moolatrikona", "own_sign", "friendly", "neutral", "inimical", "debilitated")

BANDS = ("very_weak", "weak", "moderate", "strong", "very_strong")
"""Continuous strength is bucketed into these for the index, and the exact
value is kept in a side table for the VM. The index yields a superset; the
executor prunes it with exact arithmetic. False positives are free, false
negatives are not."""

VARGAS = ("d1", "d2", "d3", "d7", "d9", "d10", "d12", "d16", "d20", "d24", "d27", "d30", "d40", "d45", "d60")

DASHA_SYSTEMS = ("vimshottari", "ashtottari", "yogini", "chara", "kalachakra")
DASHA_LEVELS = ("maha", "antar", "pratyantar", "sookshma", "prana")

NATURES = ("benefic", "malefic", "neutral")
FRIENDSHIPS = ("great_friend", "friend", "neutral", "enemy", "great_enemy",
               "temporary_friend", "temporary_enemy")

#: Natural significators. A rule saying "the karaka for children" must resolve
#: to a body, and which body is a doctrinal statement, so it is named here
#: rather than left to the extractor.
KARAKAS = {
    "atma": "sun", "manas": "moon", "bhratru": "mars", "buddhi": "mercury",
    "putra": "jupiter", "dhana": "jupiter", "guru": "jupiter",
    "kalatra": "venus", "ayu": "saturn", "karma": "saturn", "pitru": "sun",
    "matru": "moon",
}

CHARA_KARAKAS = (
    "atmakaraka", "amatyakaraka", "bhratrukaraka", "matrukaraka",
    "putrakaraka", "gnatikaraka", "darakaraka",
)

BHAVAS = tuple(f"{n:02d}" for n in range(1, 13))
REFERENCES = ("lagna", "moon", "sun")
"""Reference points a house can be counted from.

"The 7th house" may mean the 7th from the Lagna, from the Moon, from the Sun,
from a karaka or from the Arudha, and picking wrong produces a rule that fires
on the wrong charts forever without ever looking wrong. So `occupies_bhava`
means from the Lagna BY DEFINITION, and anything else has to say which - which
is what makes the discipline enforceable rather than aspirational."""

DISTANCES = tuple(f"{n:02d}" for n in range(1, 13))
"""Relative house counts, 1..12, counted inclusively from the subject -
the convention every classical text uses."""

KENDRAS = (1, 4, 7, 10)
TRIKONAS = (1, 5, 9)
DUSTHANAS = (6, 8, 12)
UPACHAYAS = (3, 6, 10, 11)
MARAKAS = (2, 7)


# ==========================================================================
# Seed predicates
#
# Chosen so the five hand-written M0 rules and the derivation tiers can be
# expressed without a single approximation. Anything a real verse needs beyond
# this is an ExtensionProposal, never a near-miss substitution.
# ==========================================================================

def _p(entry_id: str, *args: ArgSpec, **kw) -> PredicateSpec:
    return PredicateSpec(entry_id=entry_id, args=list(args), **kw)


def _a(name: str, *kinds: str, optional: bool = False) -> ArgSpec:
    return ArgSpec(name=name, kinds=tuple(kinds), optional=optional)


SEED_PREDICATES: tuple[PredicateSpec, ...] = (
    # -- placement ---------------------------------------------------------
    _p("occupies_bhava", _a("subject", GRAHA_REF), _a("bhava", BHAVA),
       functional=True, label="subject sits in this house"),
    _p("occupies_rashi", _a("subject", GRAHA_REF), _a("rashi", RASHI),
       functional=True, label="subject sits in this sign"),
    _p("in_nakshatra", _a("subject", GRAHA_REF), _a("nakshatra", NAKSHATRA),
       functional=True),
    _p("in_kendra", _a("subject", GRAHA_REF), label="in an angle: 1, 4, 7, 10"),
    _p("in_trikona", _a("subject", GRAHA_REF), label="in a trine: 1, 5, 9"),
    _p("in_dusthana", _a("subject", GRAHA_REF), label="in 6, 8 or 12"),
    _p("in_upachaya", _a("subject", GRAHA_REF), label="in 3, 6, 10 or 11"),

    # -- condition ---------------------------------------------------------
    _p("dignity", _a("subject", GRAHA_REF), _a("dignity", DIGNITY), functional=True),
    _p("retrograde", _a("subject", GRAHA_REF)),
    _p("combust", _a("subject", GRAHA_REF)),
    _p("vargottama", _a("subject", GRAHA_REF),
       label="same sign in D1 and D9"),

    # -- relation ----------------------------------------------------------
    _p("conjunct", _a("subject", GRAHA_REF), _a("other", GRAHA_REF),
       label="same rashi - whole-sign, not an orb"),
    _p("aspects", _a("subject", GRAHA_REF), _a("target", GRAHA_REF, BHAVA),
       label="Parashari graha drishti"),
    _p("exchange", _a("subject", GRAHA_REF), _a("other", GRAHA_REF),
       label="parivartana - each in the other's sign"),
    _p("same_bhava", _a("subject", GRAHA_REF), _a("other", GRAHA_REF)),
    _p("house_distance", _a("subject", GRAHA_REF), _a("other", GRAHA_REF),
       _a("distance", DISTANCE),
       label="other counted from subject, 1..12 inclusive of the start - the "
             "form classical relative-house rules are actually stated in"),
    _p("bhava_in_rashi", _a("bhava", BHAVA), _a("rashi", RASHI), functional=True,
       label="whole-sign: which sign a house falls in. lagna is bhava.01"),
    _p("occupies_bhava_from", _a("subject", GRAHA_REF), _a("bhava", BHAVA),
       _a("reference", REFERENCE), functional=True,
       label="house counted from a stated reference point. `occupies_bhava` is "
             "the from-lagna case and is the only one allowed to leave it "
             "implicit"),

    # -- strength ----------------------------------------------------------
    _p("strength_band", _a("subject", GRAHA_REF), _a("band", BAND),
       functional=True, label="bucketed shadbala - the indexable form"),
    _p("strength", _a("subject", GRAHA_REF), _a("op", OPERATOR), _a("value", NUMBER),
       evaluation="numeric", indexable=False,
       label="exact shadbala comparison, evaluated after retrieval"),
    _p("stronger_than", _a("subject", GRAHA_REF), _a("other", GRAHA_REF),
       indexable=False, label="comparative - depends on both, not indexable"),
    _p("occupant_count", _a("bhava", BHAVA), _a("op", OPERATOR), _a("n", NUMBER),
       evaluation="count", indexable=False),

    # Ashtakavarga. A real, computable support measure and deliberately NOT
    # filed under `strength`: conflating a bindu count with Shadbala would
    # answer a rule that cites one using the other.
    _p("sav_band", _a("bhava", BHAVA), _a("band", BAND), functional=True,
       label="bucketed Sarvashtakavarga bindus for this house"),
    _p("sav_bindu", _a("bhava", BHAVA), _a("op", OPERATOR), _a("n", NUMBER),
       evaluation="numeric", indexable=False,
       label="exact SAV bindu count, evaluated after retrieval"),

    # -- varga -------------------------------------------------------------
    _p("varga_occupies", _a("varga", VARGA), _a("subject", GRAHA_REF), _a("rashi", RASHI)),
    _p("varga_dignity", _a("varga", VARGA), _a("subject", GRAHA_REF), _a("dignity", DIGNITY)),

    # -- timing ------------------------------------------------------------
    _p("dasha_active", _a("system", DASHA_SYSTEM), _a("subject", GRAHA_REF),
       _a("level", DASHA_LEVEL)),

    # -- derived: produced by DERIVE_FACT rules, in tier order -------------
    _p("natural_nature", _a("subject", GRAHA_REF), _a("nature", NATURE),
       derived=True, tier=1,
       label="benefic/malefic before lagna is considered - Moon's waxing "
             "state makes even this contested"),
    _p("natural_friendship", _a("subject", GRAHA_REF), _a("other", GRAHA_REF),
       _a("friendship", FRIENDSHIP), derived=True, tier=1),
    _p("temporal_friendship", _a("subject", GRAHA_REF), _a("other", GRAHA_REF),
       _a("friendship", FRIENDSHIP), derived=True, tier=1),
    _p("composite_friendship", _a("subject", GRAHA_REF), _a("other", GRAHA_REF),
       _a("friendship", FRIENDSHIP), derived=True, tier=2,
       label="five-fold dignity - reads both friendship tiers below it"),
    _p("functional_nature", _a("subject", GRAHA_REF), _a("nature", NATURE),
       derived=True, tier=2,
       label="benefic or malefic FOR THIS LAGNA - the classic contested "
             "derivation, which is why it is a rule and not a constant"),

    # -- Jaimini-only. Naming these from a Parashari rule is a compile error.
    _p("chara_karaka", _a("subject", GRAHA_REF), _a("karaka", NAKSHATRA, BHAVA, RASHI),
       derived=True, tier=3, schools=("school.jaimini",)),
    _p("rashi_aspects", _a("subject", RASHI), _a("target", RASHI),
       schools=("school.jaimini",), label="Jaimini rashi drishti, not graha drishti"),
)


# ==========================================================================
# Seed claims - the consequent vocabulary
#
# Deliberately coarse. A claim id is a routing target and a ledger key, not a
# sentence; the sentence lives in the rule's literal_text with its citation.
# ==========================================================================

SEED_CLAIMS: dict[str, str] = {
    "wealth.accumulation": "Sustained gain, savings, assets",
    "wealth.loss": "Depletion, expense, financial reversal",
    "wealth.income_flow": "Earnings and their regularity",
    "career.stability_and_authority": "Standing, office, recognised position",
    "career.disruption": "Interruption, demotion, forced change",
    "career.independent_work": "Self-directed or unsalaried work",
    "status.recognition": "Public regard, reputation",
    "relationship.marriage_timing": "When union is indicated",
    "relationship.harmony": "Quality of partnership",
    "relationship.discord": "Friction, separation pressure",
    "progeny.children": "Children indicated",
    "education.learning": "Study, scholarship, intellect",
    "health.vitality": "Constitutional resilience",
    "health.affliction": "Classical indications of lowered resilience",
    "longevity.span": "Ayurdaya - length of life",
    "travel.relocation": "Movement, foreign residence",
    "property.land_and_home": "Fixed assets, dwelling",
    "temperament.disposition": "Character and inclination",
    "spiritual.inclination": "Renunciation, practice, dharma",
    "obstacle.general": "Impediment without a named domain",
    "family.father": "The father's circumstances and standing",
    "family.mother": "The mother's circumstances and standing",
    "family.siblings": "Brothers and sisters",
    "general.protection": "Classical mitigation of difficulty as a whole",
    "livelihood.means": "How earnings are come by, as distinct from how much",
}

#: Claims that may exist in the corpus for scholarly completeness but are
#: structurally unreachable from the serving path. Enforced at extraction, not
#: at the output filter - a filter you cannot accidentally remove beats one you
#: have to remember to apply.
NEVER_USER_FACING_CLAIMS = frozenset({"longevity.span"})

SEED_UNITS = ("years", "months", "days", "count", "multiple", "rupas")

SEED_OBSERVABLES: dict[str, str] = {
    "chart": "A natal or event chart cast from time and place",
    "query_time": "The moment a question was asked - prashna",
    # Registered so Prasna rules can be extracted honestly and then withheld,
    # rather than being approximated into chart conditions or silently dropped.
    "breath": "Which nostril the querent is breathing through",
    "touch": "Which part of the body the querent touched",
    "querent_bearing": "The querent's mood, dress and manner",
    "omen": "What occurred or arrived at the moment of the question",
    "palm_image": "An image of the hand - samudrika",
    "name": "The querent's name, for onomantic methods",
}

#: Observables the product can actually capture. A rule requiring anything
#: outside this set is extracted, stored, and never served. An LLM must never
#: improvise the observation - that is fabrication with a classical veneer.
CAPTURABLE_OBSERVABLES = frozenset({"chart", "query_time", "name"})

SEED_NAMESPACES: dict[str, str] = {
    "school.parashari": "Brihat Parashara Hora Shastra and its lineage",
    "school.jaimini": "Jaimini Sutras - chara karakas, rashi drishti",
    "school.prashna": "Kerala horary, Prasna Marga",
    "school.lalkitab": "Lal Kitab - namespaced, never merged into Parashari",
    "school.tajika": "Tajika annual charts",
}

SEED_DOMAINS = (
    "domain.wealth", "domain.career", "domain.status", "domain.relationship",
    "domain.progeny", "domain.education", "domain.health", "domain.longevity",
    "domain.travel", "domain.property", "domain.temperament", "domain.spiritual",
)


# ==========================================================================
# The registry object
# ==========================================================================


class DuplicateEntry(ValueError):
    pass


class Registry:
    """Additive-only symbol store.

    `add` refuses to overwrite. That refusal is the whole point: the moment an
    entry can be redefined in place, every rule extracted before the redefinition
    means something different than it did, silently, and no test catches it.
    """

    def __init__(self, version: str = REGISTRY_VERSION) -> None:
        self.version = version
        self._entries: dict[RegistryKind, dict[str, RegistryEntry]] = defaultdict(dict)
        self._predicates: dict[str, PredicateSpec] = {}

    # -- writes ------------------------------------------------------------

    def add(self, entry: RegistryEntry) -> RegistryEntry:
        bucket = self._entries[entry.registry]
        existing = bucket.get(entry.entry_id)
        if existing is not None and existing != entry:
            raise DuplicateEntry(
                f"{entry.registry.value} {entry.entry_id!r} already published as "
                f"{existing.introduced_in}; supersede it, never edit it"
            )
        bucket[entry.entry_id] = entry
        return entry

    def add_predicate(self, spec: PredicateSpec, *, introduced_by: str = "seed") -> None:
        existing = self._predicates.get(spec.entry_id)
        if existing is not None and existing != spec:
            raise DuplicateEntry(
                f"predicate {spec.entry_id!r} already published with a different "
                f"signature; changing a signature changes the meaning of every "
                f"rule that used it"
            )
        self._predicates[spec.entry_id] = spec
        self.add(
            RegistryEntry(
                registry=RegistryKind.PREDICATE,
                entry_id=spec.entry_id,
                signature=spec.model_dump(mode="json"),
                label=spec.label,
                introduced_in=self.version,
                introduced_by=introduced_by,
            )
        )

    def add_symbol(
        self,
        registry: RegistryKind,
        entry_id: str,
        *,
        label: str = "",
        namespace: str = "",
        introduced_by: str = "seed",
    ) -> None:
        self.add(
            RegistryEntry(
                registry=registry,
                entry_id=entry_id,
                namespace=namespace,
                label=label,
                introduced_in=self.version,
                introduced_by=introduced_by,
            )
        )

    # -- reads -------------------------------------------------------------

    def symbols(self, kind: RegistryKind) -> set[str]:
        return set(self._entries[kind])

    def as_closure(self) -> dict[RegistryKind, set[str]]:
        """The shape `urf.validate_registry_closure` expects."""
        return {kind: set(bucket) for kind, bucket in self._entries.items()}

    def predicate(self, entry_id: str) -> Optional[PredicateSpec]:
        return self._predicates.get(entry_id)

    def predicates(self) -> dict[str, PredicateSpec]:
        return dict(self._predicates)

    def derived_predicates(self) -> dict[str, PredicateSpec]:
        return {k: v for k, v in self._predicates.items() if v.derived}

    def entry(self, kind: RegistryKind, entry_id: str) -> Optional[RegistryEntry]:
        return self._entries[kind].get(entry_id)

    def fingerprint(self) -> str:
        """Content hash over every published symbol.

        Goes into the bundle manifest so a bundle can never be loaded against a
        registry it was not compiled with.
        """
        parts: list[str] = [self.version]
        for kind in sorted(self._entries, key=lambda k: k.value):
            for entry_id in sorted(self._entries[kind]):
                entry = self._entries[kind][entry_id]
                parts.append(f"{kind.value}:{entry_id}:{entry.introduced_in}")
                if kind is RegistryKind.PREDICATE:
                    spec = self._predicates.get(entry_id)
                    if spec:
                        parts.append(
                            ",".join(
                                f"{a.name}={'|'.join(a.kinds)}" for a in spec.args
                            )
                            + f"#{spec.evaluation}#{spec.indexable}#{spec.tier}"
                        )
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]

    def __len__(self) -> int:
        return sum(len(b) for b in self._entries.values())


def seed_registry(version: str = REGISTRY_VERSION) -> Registry:
    """The published v1 vocabulary. Parashari-complete for the seed rules."""
    reg = Registry(version)

    for spec in SEED_PREDICATES:
        reg.add_predicate(spec)

    def sym(kind: RegistryKind, ids: Iterable[str], prefix: str = "", label: str = ""):
        for i in ids:
            reg.add_symbol(kind, f"{prefix}{i}", label=label)

    sym(RegistryKind.ENTITY, GRAHAS, "graha.")
    sym(RegistryKind.ENTITY, RASHIS, "rashi.")
    sym(RegistryKind.ENTITY, BHAVAS, "bhava.")
    sym(RegistryKind.ENTITY, NAKSHATRAS, "nakshatra.")
    sym(RegistryKind.ENTITY, DIGNITIES, "dignity.")
    sym(RegistryKind.ENTITY, BANDS, "band.")
    sym(RegistryKind.ENTITY, VARGAS, "varga.")
    sym(RegistryKind.ENTITY, DASHA_SYSTEMS, "dasha_system.")
    sym(RegistryKind.ENTITY, DASHA_LEVELS, "level.")
    sym(RegistryKind.ENTITY, NATURES, "nature.")
    sym(RegistryKind.ENTITY, FRIENDSHIPS, "friendship.")
    sym(RegistryKind.ENTITY, KARAKAS, "karaka.")
    sym(RegistryKind.ENTITY, CHARA_KARAKAS, "chara.")
    sym(RegistryKind.ENTITY, DISTANCES, "dist.")
    sym(RegistryKind.ENTITY, REFERENCES, "ref.")
    sym(RegistryKind.ENTITY, SEED_DOMAINS)

    for claim_id, label in SEED_CLAIMS.items():
        reg.add_symbol(RegistryKind.CLAIM, claim_id, label=label)
    for unit in SEED_UNITS:
        reg.add_symbol(RegistryKind.UNIT, unit)
    for obs_id, label in SEED_OBSERVABLES.items():
        reg.add_symbol(RegistryKind.OBSERVABLE, obs_id, label=label)
    for ns, label in SEED_NAMESPACES.items():
        reg.add_symbol(RegistryKind.NAMESPACE, ns, label=label)

    return reg


# ==========================================================================
# The proposal queue - how the corpus tells you what is missing
# ==========================================================================


class ProposalQueue:
    """Clusters extension proposals and surfaces only the ones with signal.

    A predicate proposed once is usually an extraction artefact. Proposed forty
    seven times across two chapters, it is a real gap in the vocabulary. The
    threshold is what keeps a reviewer working on signal instead of noise.

    Nothing is dropped in the meantime. Passages that triggered a below-threshold
    proposal are parked and re-run automatically when the count rises, so a gap
    can be slow to surface but can never be silently lost.
    """

    def __init__(self, threshold: int = REVIEW_THRESHOLD) -> None:
        self.threshold = threshold
        self._by_key: dict[tuple[str, str, str], ExtensionProposal] = {}
        self._parked: dict[tuple[str, str, str], set[str]] = defaultdict(set)

    @staticmethod
    def _key(p: ExtensionProposal) -> tuple[str, str, str]:
        # Cluster on signature, not on the proposed name: two extractors will
        # invent two names for the same missing concept.
        sig = ",".join(f"{k}={v}" for k, v in sorted(p.signature.items()))
        return (p.registry.value, p.namespace, sig or p.proposed_id)

    def submit(self, proposal: ExtensionProposal) -> ExtensionProposal:
        key = self._key(proposal)
        existing = self._by_key.get(key)
        if existing is None:
            self._by_key[key] = proposal
            merged = proposal
        else:
            for pid in proposal.evidence_passages:
                if pid not in existing.evidence_passages:
                    existing.evidence_passages.append(pid)
            existing.occurrences = len(existing.evidence_passages)
            existing.status = "clustered"
            merged = existing
        self._parked[key].update(proposal.evidence_passages)
        merged.occurrences = max(merged.occurrences, len(self._parked[key]))
        return merged

    def ready_for_review(self) -> list[ExtensionProposal]:
        """Sorted by frequency - the reviewer works the top of this list."""
        ready = [
            p for k, p in self._by_key.items()
            if p.occurrences >= self.threshold and p.status in ("pending", "clustered")
        ]
        return sorted(ready, key=lambda p: -p.occurrences)

    def parked_passages(self) -> set[str]:
        """Every passage blocked on a proposal. These re-run after a registry
        insert; none of them are lost."""
        out: set[str] = set()
        for key, passages in self._parked.items():
            proposal = self._by_key[key]
            if proposal.status not in ("approved", "rejected"):
                out.update(passages)
        return out

    def __len__(self) -> int:
        return len(self._by_key)


# ==========================================================================
# Aliases - the resolve pass's lookup table
#
# The single largest corpus bug class is an unresolved symbol. A verse says
# "Guru", the extractor writes "Guru", nothing in the engine knows what that is,
# and the rule matches no chart forever. So aliases resolve to canonical ids at
# compile time and an unresolvable symbol is a hard error, never a warning.
# ==========================================================================

_GRAHA_ALIASES: dict[str, str] = {
    "sun": "sun", "surya": "sun", "ravi": "sun", "sol": "sun",
    "moon": "moon", "chandra": "moon", "soma": "moon", "luna": "moon",
    "mars": "mars", "kuja": "mars", "mangala": "mars", "angaraka": "mars",
    "kartikeya": "mars",
    "mercury": "mercury", "budha": "mercury", "budh": "mercury",
    "jupiter": "jupiter", "guru": "jupiter", "brihaspati": "jupiter",
    "brhaspati": "jupiter", "jup": "jupiter", "devaguru": "jupiter",
    "venus": "venus", "shukra": "venus", "sukra": "venus",
    "saturn": "saturn", "shani": "saturn", "sani": "saturn",
    "shanaishchara": "saturn",
    "rahu": "rahu", "dragons_head": "rahu", "north_node": "rahu",
    "ketu": "ketu", "dragons_tail": "ketu", "south_node": "ketu",
}

_ORDINALS: dict[str, int] = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11,
    "twelfth": 12,
    "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6, "7th": 7,
    "8th": 8, "9th": 9, "10th": 10, "11th": 11, "12th": 12,
    "lagna": 1, "ascendant": 1, "tanu": 1, "dhana": 2, "sahaja": 3,
    "bandhu": 4, "putra": 5, "roga": 6, "yuvati": 7, "randhra": 8,
    "dharma": 9, "karma": 10, "labha": 11, "vyaya": 12,
}


_DASHA_LEVEL_ALIASES: dict[str, str] = {
    # A verse says "in the Antardasha of Saturn"; the registry entry is
    # `level.antar`. Every one of these came out of an extraction run that
    # failed on it, which is the only honest way to build an alias table -
    # guessing at aliases up front produces the ones nobody writes.
    "mahadasha": "maha", "maha_dasha": "maha", "dasa": "maha",
    "mahadasa": "maha", "md": "maha",
    "antardasha": "antar", "antar_dasha": "antar", "antardasa": "antar",
    "bhukti": "antar", "bhukthi": "antar", "ad": "antar",
    "pratyantardasha": "pratyantar", "pratyantar_dasha": "pratyantar",
    "pratyantardasa": "pratyantar", "pd": "pratyantar",
    "sookshmadasha": "sookshma", "sukshma": "sookshma",
    "sookshma_dasha": "sookshma", "suksma": "sookshma",
    "pranadasha": "prana", "prana_dasha": "prana",
}
"""Alias -> canonical dasha level.

Additive, like every registry change. A rule extracted when `antardasha` did not
resolve must execute identically once it does - which it does, because the
canonical id it resolves to has not moved.
"""


class UnresolvedSymbol(ValueError):
    pass


def resolve_symbol(token: str) -> str:
    """Any way a text names something -> the canonical registry id.

    Raises rather than guessing. A guessed symbol produces a rule that fires on
    the wrong charts, forever, and nothing downstream can detect it.
    """
    if not isinstance(token, str):
        raise UnresolvedSymbol(f"expected a symbol, got {token!r}")

    raw = token.strip()
    if raw.startswith("?"):
        return raw

    # already canonical
    # `ref.` belongs here for the same reason as the rest: it is what this
    # function *returns* for "from_lagna". Leaving it out made resolution
    # non-idempotent, so a rule emitted back to YAML could not be recompiled -
    # invisible until something tried to write rules out rather than only read
    # them in.
    for prefix in ("graha.", "rashi.", "bhava.", "nakshatra.", "dignity.",
                   "band.", "varga.", "dasha_system.", "level.", "nature.",
                   "friendship.", "karaka.", "chara.", "dist.", "domain.",
                   "lord.bhava.", "school.", "ref."):
        if raw.startswith(prefix):
            return raw

    key = raw.lower().replace(" ", "_").replace("-", "_")

    if key in _GRAHA_ALIASES:
        return f"graha.{_GRAHA_ALIASES[key]}"

    # "2nd lord", "lord of the 10th", "eleventh lord"
    if "lord" in key:
        stripped = key.replace("lord", "").replace("of", "").replace("the", "")
        stripped = stripped.strip("_ ")
        house = _ORDINALS.get(stripped)
        if house is None and stripped.isdigit():
            house = int(stripped)
        if house is not None and 1 <= house <= 12:
            return f"lord.bhava.{house:02d}"

    if key in ("lagna_ref", "from_lagna", "ascendant_ref"):
        return "ref.lagna"
    if key in ("from_moon", "moon_ref", "chandra_lagna"):
        return "ref.moon"
    if key in ("from_sun", "sun_ref", "surya_lagna"):
        return "ref.sun"
    if key in _ORDINALS:
        return f"bhava.{_ORDINALS[key]:02d}"
    if key.isdigit() and 1 <= int(key) <= 12:
        return f"bhava.{int(key):02d}"

    if key in RASHIS:
        return f"rashi.{key}"
    if key in DIGNITIES:
        return f"dignity.{key}"
    if key in BANDS:
        return f"band.{key}"
    if key in NATURES:
        return f"nature.{key}"
    if key in FRIENDSHIPS:
        return f"friendship.{key}"
    if key in KARAKAS:
        return f"karaka.{key}"
    if key in CHARA_KARAKAS:
        return f"chara.{key}"
    if key in DASHA_LEVELS:
        return f"level.{key}"
    if key in _DASHA_LEVEL_ALIASES:
        return f"level.{_DASHA_LEVEL_ALIASES[key]}"
    if key in DASHA_SYSTEMS:
        return f"dasha_system.{key}"
    if key.endswith("_dasha") and key[:-6] in DASHA_SYSTEMS:
        return f"dasha_system.{key[:-6]}"
    if key.upper() in {v.upper() for v in VARGAS}:
        return f"varga.{key.lower()}"
    nak = key.replace("__", "_")
    if nak in NAKSHATRAS:
        return f"nakshatra.{nak}"

    raise UnresolvedSymbol(
        f"cannot resolve {token!r} to a registry id - add an alias or an "
        f"ExtensionProposal, never a near miss"
    )


#: House sets, for the contradiction pass. These are exact, not heuristic:
#: kendra and dusthana are disjoint, so requiring both is unsatisfiable.
HOUSE_GROUPS: dict[str, frozenset[int]] = {
    "in_kendra": frozenset(KENDRAS),
    "in_trikona": frozenset(TRIKONAS),
    "in_dusthana": frozenset(DUSTHANAS),
    "in_upachaya": frozenset(UPACHAYAS),
}
