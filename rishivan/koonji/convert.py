"""The already-extracted corpus, converted into the frame - no model calls.

Three thousand units were extracted from eleven books by the earlier pipeline
and sit in `koonji/*.jsonl` in a schema the engine cannot read: `rule_key`,
`formation.atoms`, `effects`, `life_domains`. That work is paid for. This
converts what can be converted, deterministically, and reports precisely what it
could not.

    formation.atoms  ->  BoolExpr over registry predicates
    effects[]        ->  ClaimConsequent (one rule per effect)
    life_domains     ->  domain tags
    translation      ->  the quoted verse and its sha256

**The rule that shapes everything here: an atom that will not map kills the
whole rule, not just the atom.** Dropping a condition makes the rule fire on
charts the verse never described - it widens silently, produces confident
output, and there is nothing downstream that can detect it. A dropped rule is
visible in the report and costs nothing but coverage.

Everything emitted is `status: candidate`. A machine-converted rule that no
Jyotish reviewer has read is not production material, and the serving default
excludes it until somebody says otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from rishivan.koonji.corpus import SCHOOL_BY_BOOK, Unit
from rishivan.koonji.emit import quote_sha256
from rishivan.koonji.registry import Registry, UnresolvedSymbol, resolve_symbol
from rishivan.koonji.urf import RegistryKind

CONVERTER_VERSION = "1.0.0"


class Unmappable(ValueError):
    """This atom has no faithful expression in the registry vocabulary.

    Raised rather than returned so that a mapper cannot forget to check. The
    message is the payload - it becomes a line in the report and, in aggregate,
    the registry-extension queue.
    """


# ==========================================================================
# Claims
#
# `life_domain` in the old schema is free text: "wealth", "Wealth", "fortune",
# "comforts", and 1,841 effects with none at all. It is mapped to the registry's
# closed claim vocabulary here, and anything unmapped drops.
#
# `family` is deliberately absent. The registry distinguishes family.father,
# family.mother and family.siblings; the old tag says only "family", and picking
# one would attribute a verse about a mother to a father. Ambiguity is a reason
# to drop, not to guess.
# ==========================================================================

CLAIM_MAP: dict[str, tuple[str, Optional[str]]] = {
    # life_domain (lowercased) -> (claim id, domain tag or None)
    "wealth": ("wealth.accumulation", "domain.wealth"),
    "money": ("wealth.accumulation", "domain.wealth"),
    "finance": ("wealth.accumulation", "domain.wealth"),
    "fortune": ("wealth.accumulation", "domain.wealth"),
    "prosperity": ("wealth.accumulation", "domain.wealth"),
    "income": ("wealth.income_flow", "domain.wealth"),
    "gains": ("wealth.income_flow", "domain.wealth"),
    "loss": ("wealth.loss", "domain.wealth"),
    "poverty": ("wealth.loss", "domain.wealth"),

    "career": ("career.stability_and_authority", "domain.career"),
    "profession": ("career.stability_and_authority", "domain.career"),
    "work": ("livelihood.means", "domain.career"),
    "livelihood": ("livelihood.means", "domain.career"),
    "occupation": ("livelihood.means", "domain.career"),

    "status": ("status.recognition", "domain.status"),
    "reputation": ("status.recognition", "domain.status"),
    "fame": ("status.recognition", "domain.status"),
    "honour": ("status.recognition", "domain.status"),
    "honor": ("status.recognition", "domain.status"),
    "authority": ("status.recognition", "domain.status"),
    "power": ("status.recognition", "domain.status"),

    "health": ("health.vitality", "domain.health"),
    "disease": ("health.affliction", "domain.health"),
    "illness": ("health.affliction", "domain.health"),
    "vitality": ("health.vitality", "domain.health"),
    "longevity": ("longevity.span", "domain.longevity"),
    "lifespan": ("longevity.span", "domain.longevity"),

    "relationships": ("relationship.harmony", "domain.relationship"),
    "relationship": ("relationship.harmony", "domain.relationship"),
    "marriage": ("relationship.harmony", "domain.relationship"),
    "spouse": ("relationship.harmony", "domain.relationship"),
    "love": ("relationship.harmony", "domain.relationship"),

    "children": ("progeny.children", "domain.progeny"),
    "progeny": ("progeny.children", "domain.progeny"),
    "offspring": ("progeny.children", "domain.progeny"),

    "father": ("family.father", "domain.status"),
    "mother": ("family.mother", "domain.status"),
    "siblings": ("family.siblings", "domain.status"),
    "brothers": ("family.siblings", "domain.status"),

    "education": ("education.learning", "domain.education"),
    "learning": ("education.learning", "domain.education"),
    "knowledge": ("education.learning", "domain.education"),
    "intelligence": ("education.learning", "domain.education"),

    "character": ("temperament.disposition", "domain.temperament"),
    "temperament": ("temperament.disposition", "domain.temperament"),
    "mind": ("temperament.disposition", "domain.temperament"),
    "nature": ("temperament.disposition", "domain.temperament"),
    "personality": ("temperament.disposition", "domain.temperament"),

    "spirituality": ("spiritual.inclination", "domain.spiritual"),
    "spiritual": ("spiritual.inclination", "domain.spiritual"),
    "dharma": ("spiritual.inclination", "domain.spiritual"),
    "religion": ("spiritual.inclination", "domain.spiritual"),

    "travel": ("travel.relocation", "domain.travel"),
    "journey": ("travel.relocation", "domain.travel"),
    "foreign": ("travel.relocation", "domain.travel"),

    "property": ("property.land_and_home", "domain.property"),
    "land": ("property.land_and_home", "domain.property"),
    "home": ("property.land_and_home", "domain.property"),
    "vehicles": ("property.land_and_home", "domain.property"),
    "comforts": ("property.land_and_home", "domain.property"),

    # Untagged in the registry on purpose: these say something true about a life
    # without saying which part of it. The index treats a rule with no domain
    # tag as reachable from every domain filter, which is the right behaviour
    # for a general protective or obstructive yoga.
    "general": ("general.protection", None),
    "happiness": ("general.protection", None),
    "safety": ("general.protection", None),
    "protection": ("general.protection", None),
    "obstacles": ("obstacle.general", None),
    "difficulties": ("obstacle.general", None),
    "struggles": ("obstacle.general", None),
}

MAGNITUDE_MAP = {"weak": "slight", "moderate": "moderate", "strong": "strong",
                 "extreme": "extreme"}
POLARITIES = {"positive", "negative", "mixed", "neutral"}

DOMAIN_WEIGHT = 0.7
"""What a converted rule's domain tag is worth.

Below the hand-authored rules' 0.9-0.95 and above the incidental-tag threshold
of 0.5, because the tag came from a single free-text field rather than from a
reviewer weighing the verse. It is good enough to route on and not good enough
to outrank reviewed material.
"""


# ==========================================================================
# Atoms
# ==========================================================================


def _graha(token: Any) -> str:
    sym = resolve_symbol(str(token))
    if not sym.startswith(("graha.", "lord.bhava.")):
        raise Unmappable(f"{token!r} is not a graha or a house lord")
    return sym


def _bhava(token: Any) -> str:
    sym = resolve_symbol(str(token))
    if not sym.startswith("bhava."):
        raise Unmappable(f"{token!r} is not a bhava")
    return sym


def _rashi(token: Any) -> str:
    # "sign": "2" appears in the corpus. `resolve_symbol` turns it into
    # bhava.02, which would type-check as a house and silently mean the wrong
    # thing, so the result is checked rather than trusted.
    sym = resolve_symbol(str(token))
    if not sym.startswith("rashi."):
        raise Unmappable(f"{token!r} is not a rashi")
    return sym


def _lord(atom: dict) -> str:
    house = atom.get("lord_of")
    if house is None:
        raise Unmappable("lord_of_* atom with no `lord_of`")
    n = int(house)
    if not 1 <= n <= 12:
        raise Unmappable(f"house {house!r} out of range")
    return f"lord.bhava.{n:02d}"


def _houses(atom: dict) -> list[str]:
    if atom.get("houses"):
        return [_bhava(h) for h in atom["houses"]]
    if atom.get("house") is not None:
        return [_bhava(atom["house"])]
    raise Unmappable("no `house` or `houses`")


def _any_of(nodes: list[Any]) -> Any:
    return nodes[0] if len(nodes) == 1 else {"any": nodes}


def _all_of(nodes: list[Any]) -> Any:
    return nodes[0] if len(nodes) == 1 else {"all": nodes}


def _m_planet_in_house(atom: dict) -> Any:
    subject = _graha(atom.get("planet") or _unmapped("planet_in_house without a planet"))
    return _any_of([{"occupies_bhava": {"subject": subject, "bhava": b}}
                    for b in _houses(atom)])


def _m_lord_in_house(atom: dict) -> Any:
    # A list of houses here reads as "the 10th lord in the 10th, 11th, 4th or
    # 5th" - the verse enumerating alternatives. Disjunction.
    subject = _lord(atom)
    return _any_of([{"occupies_bhava": {"subject": subject, "bhava": b}}
                    for b in _houses(atom)])


def _m_planet_in_sign(atom: dict) -> Any:
    subject = _graha(atom.get("planet") or _unmapped("planet_in_sign without a planet"))
    return {"occupies_rashi": {"subject": subject, "rashi": _rashi(atom["sign"])}} \
        if atom.get("sign") is not None else _unmapped("planet_in_sign without a sign")


def _m_lord_in_sign(atom: dict) -> Any:
    if atom.get("sign") is None:
        raise Unmappable("lord_of_house_in_sign without a sign")
    return {"occupies_rashi": {"subject": _lord(atom), "rashi": _rashi(atom["sign"])}}


def _m_conjunct(atom: dict) -> Any:
    a = atom.get("planet")
    b = atom.get("other") or atom.get("target") or atom.get("with")
    if not a or not b:
        raise Unmappable("conjunct needs two grahas")
    return {"conjunct": {"subject": _graha(a), "other": _graha(b)}}


def _m_aspected_by(atom: dict) -> Any:
    # `aspects(subject, target)` - the aspecting graha is the subject. The old
    # atom names the aspecting body in `target` and the aspected one in
    # `planet`, so the two swap on the way in.
    aspector = atom.get("target")
    aspected = atom.get("planet") or atom.get("house")
    if not aspector:
        raise Unmappable("aspected_by with no aspecting graha")
    if aspected is None:
        # "aspected by Jupiter" with no stated subject. The referent is in the
        # prose, not in the atom, and guessing it is how a rule ends up about
        # the wrong planet.
        raise Unmappable("aspected_by with no subject - unresolved anaphora")
    subject = _graha(aspector)
    resolved = resolve_symbol(str(aspected))
    if not resolved.startswith(("graha.", "lord.bhava.", "bhava.")):
        raise Unmappable(f"{aspected!r} is not an aspectable target")
    return {"aspects": {"subject": subject, "target": resolved}}


def _m_dignity(atom: dict) -> Any:
    planet, dignity = atom.get("planet"), atom.get("dignity")
    if not planet or not dignity:
        raise Unmappable("dignity_is needs a planet and a dignity")
    sym = resolve_symbol(str(dignity))
    if not sym.startswith("dignity."):
        raise Unmappable(f"{dignity!r} is not a dignity")
    return {"dignity": {"subject": _graha(planet), "dignity": sym}}


def _m_house_empty(atom: dict) -> Any:
    # A list here reads as "the kendras are empty" - every one of them, not any
    # one of them. The opposite of `lord_of_house_in_house`, and the reason the
    # two are separate mappers rather than a shared helper.
    return _all_of([{"occupant_count": {"bhava": b, "op": "eq", "n": 0}}
                    for b in _houses(atom)])


def _m_nakshatra(atom: dict) -> Any:
    if atom.get("pada") is not None:
        # The registry has no pada argument. Dropping the pada would make the
        # rule fire on all four quarters of the nakshatra when the verse names
        # one - a fourfold widening, invisible in the output.
        raise Unmappable("nakshatra pada has no registry predicate")
    planet, nak = atom.get("planet"), atom.get("nakshatra")
    if not planet or not nak:
        raise Unmappable("planet_in_nakshatra needs a planet and a nakshatra")
    sym = resolve_symbol(str(nak))
    if not sym.startswith("nakshatra."):
        raise Unmappable(f"{nak!r} is not a nakshatra")
    return {"in_nakshatra": {"subject": _graha(planet), "nakshatra": sym}}


def _unmapped(reason: str):
    raise Unmappable(reason)


ATOM_MAPPERS = {
    "planet_in_house": _m_planet_in_house,
    "lord_of_house_in_house": _m_lord_in_house,
    "planet_in_sign": _m_planet_in_sign,
    "lord_of_house_in_sign": _m_lord_in_sign,
    "conjunct": _m_conjunct,
    "aspected_by": _m_aspected_by,
    "dignity_is": _m_dignity,
    "house_is_empty": _m_house_empty,
    "planet_in_nakshatra": _m_nakshatra,
}


def map_atom(atom: dict) -> Any:
    kind = atom.get("type")
    mapper = ATOM_MAPPERS.get(kind)
    if mapper is None:
        raise Unmappable(f"no mapping for atom type {kind!r}")
    try:
        return mapper(atom)
    except Unmappable:
        raise
    except (UnresolvedSymbol, KeyError, ValueError, TypeError) as exc:
        raise Unmappable(f"{kind}: {exc}") from exc


def map_formation(formation: dict) -> Any:
    """The whole `when` expression, or nothing."""
    atoms = formation.get("atoms") or []
    if not atoms:
        raise Unmappable("no formation atoms - the rule would fire on every chart")

    nodes = [map_atom(a) for a in atoms]
    combinator = formation.get("combinator") or "all"
    if combinator not in ("all", "any"):
        raise Unmappable(f"unknown combinator {combinator!r}")
    expr = nodes[0] if len(nodes) == 1 else {combinator: nodes}

    negated = [map_atom(a) for a in formation.get("none") or []]
    if negated:
        expr = {"all": [expr] + [{"not": n} for n in negated]}
    return expr


# ==========================================================================
# Units
# ==========================================================================

_ID_CLEAN = re.compile(r"[^A-Z0-9]+")


def rule_id_for(unit: Unit, claim: str, index: int) -> str:
    """Stable across runs, unique within a unit, readable in a trace.

    Derived from the citation rather than from a counter, so re-running the
    converter produces the same ids and a diff shows what actually changed.
    """
    book = _ID_CLEAN.sub("", unit.book_id.upper())
    where = _ID_CLEAN.sub("", unit.locator.upper())
    topic = _ID_CLEAN.sub("", claim.split(".")[0].upper())
    return f"{book}.{topic}.{where}.{index:04d}"


@dataclass(slots=True)
class Converted:
    unit: Unit
    docs: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    """Why each effect of this unit did not become a rule. Empty when all did."""


def convert_unit(unit: Unit) -> Converted:
    """One corpus unit into zero or more rule documents.

    One rule per effect, not one per verse. A verse saying "the native is wealthy
    and long-lived" is two claims with two different evidence weights, and
    filing them as one rule means neither can be cited on its own.
    """
    out = Converted(unit=unit)
    extracted = unit.extracted

    if not extracted.get("expressible", False):
        out.skipped.append("marked not expressible by the extractor")
        return out

    school = SCHOOL_BY_BOOK.get(unit.book_id)
    if school is None:
        out.skipped.append(f"no school mapped for book {unit.book_id!r}")
        return out

    try:
        when = map_formation(extracted.get("formation") or {})
    except Unmappable as exc:
        out.skipped.append(f"formation: {exc}")
        return out

    effects = extracted.get("effects") or []
    if not effects:
        out.skipped.append("no effects - nothing is claimed")
        return out

    quote = unit.translation
    timing = (extracted.get("rule_category") == "timing")

    for i, effect in enumerate(effects, start=1):
        raw_domain = (effect.get("life_domain") or "").strip().lower()
        mapped = CLAIM_MAP.get(raw_domain)
        if mapped is None:
            out.skipped.append(
                f"effect {i}: life_domain {raw_domain or '(none)'!r} has no claim"
            )
            continue
        claim, domain = mapped

        polarity = (effect.get("polarity") or "positive").lower()
        if polarity not in POLARITIES:
            out.skipped.append(f"effect {i}: unknown polarity {polarity!r}")
            continue

        magnitude = MAGNITUDE_MAP.get((effect.get("strength") or "moderate").lower())
        if magnitude is None:
            out.skipped.append(f"effect {i}: unknown strength {effect.get('strength')!r}")
            continue

        doc: dict[str, Any] = {
            "id": rule_id_for(unit, claim, i),
            "version": "1.0.0",
            # Never production. Nobody has read this.
            "status": "candidate",
            "school": school,
            "assertion": "assert_claim",
            "source": {
                "book": unit.book_id,
                "edition": unit.edition_id,
                "locator": unit.locator,
                "quote": quote,
                "quote_sha256": quote_sha256(quote),
                "authority_tier": "S0",
                "extraction": {
                    "method": "converted",
                    "converter": CONVERTER_VERSION,
                    "from_rule_key": extracted.get("rule_key", ""),
                },
                "review": {"state": "unreviewed"},
            },
            "when": when,
            "indicates": {
                "claim": claim,
                "polarity": polarity,
                "magnitude": magnitude,
                "text": (effect.get("statement") or "").strip(),
            },
        }
        if domain:
            doc["domains"] = {domain: DOMAIN_WEIGHT}
        if timing:
            doc["timing"] = {"requires_activation": True}
        out.docs.append(doc)

    return out


# ==========================================================================
# The corpus
# ==========================================================================


@dataclass(slots=True)
class ConversionReport:
    units: int = 0
    converted_units: int = 0
    docs: list[dict] = field(default_factory=list)
    reasons: dict[str, int] = field(default_factory=dict)
    unmapped_atoms: dict[str, int] = field(default_factory=dict)
    unmapped_domains: dict[str, int] = field(default_factory=dict)
    by_book: dict[str, int] = field(default_factory=dict)

    def note(self, reason: str) -> None:
        # Collapse the variable part so the report is a census rather than a log.
        key = reason.split(" - ")[0][:80]
        self.reasons[key] = self.reasons.get(key, 0) + 1

    def __str__(self) -> str:
        lines = [
            f"{self.units} units -> {len(self.docs)} rule documents "
            f"from {self.converted_units} units"
        ]
        if self.by_book:
            lines.append("\nby book:")
            for book, n in sorted(self.by_book.items(), key=lambda kv: -kv[1]):
                lines.append(f"  {book:24} {n:5}")
        if self.reasons:
            lines.append("\nwhy units and effects were dropped:")
            for reason, n in sorted(self.reasons.items(), key=lambda kv: -kv[1])[:18]:
                lines.append(f"  {n:5}  {reason}")
        if self.unmapped_atoms:
            lines.append("\nunmapped atom shapes (the registry-extension queue):")
            for atom, n in sorted(self.unmapped_atoms.items(), key=lambda kv: -kv[1])[:12]:
                lines.append(f"  {n:5}  {atom}")
        if self.unmapped_domains:
            lines.append("\nunmapped life_domains (the claim-vocabulary queue):")
            for d, n in sorted(self.unmapped_domains.items(), key=lambda kv: -kv[1])[:15]:
                lines.append(f"  {n:5}  {d}")
        return "\n".join(lines)


_ATOM_REASON = re.compile(r"^formation: (?:(\w+): )?(.*)$")
_DOMAIN_REASON = re.compile(r"^effect \d+: life_domain '(.*)' has no claim$")


def convert_corpus(units: Iterable[Unit]) -> ConversionReport:
    """Every unit, with a census of what did not make it.

    The census is the point. A converter that reports "1,037 rules" and nothing
    else tells you it worked; one that also reports which atom shapes and which
    life-domain tags it could not express tells you what to build next.
    """
    report = ConversionReport()
    seen_ids: dict[str, int] = {}

    for unit in units:
        report.units += 1
        result = convert_unit(unit)

        for doc in result.docs:
            # Two effects of one verse can map to the same claim, and two verses
            # can share a locator after a bridge merge. Either way a duplicate id
            # would compile twice and read as two independent sources agreeing.
            base = doc["id"]
            n = seen_ids.get(base, 0)
            seen_ids[base] = n + 1
            if n:
                doc["id"] = f"{base}.{n:02d}"
            report.docs.append(doc)

        if result.docs:
            report.converted_units += 1
            report.by_book[unit.book_id] = (
                report.by_book.get(unit.book_id, 0) + len(result.docs)
            )

        for reason in result.skipped:
            report.note(reason)
            m = _ATOM_REASON.match(reason)
            if m and "no mapping for atom type" in reason:
                report.unmapped_atoms[m.group(2)] = (
                    report.unmapped_atoms.get(m.group(2), 0) + 1
                )
            elif m and m.group(1):
                key = f"{m.group(1)}: {m.group(2)[:60]}"
                report.unmapped_atoms[key] = report.unmapped_atoms.get(key, 0) + 1
            d = _DOMAIN_REASON.match(reason)
            if d:
                report.unmapped_domains[d.group(1)] = (
                    report.unmapped_domains.get(d.group(1), 0) + 1
                )

    return report


def unknown_claims(docs: Iterable[dict], registry: Registry) -> set[str]:
    """Claim ids the registry does not hold.

    A guard on `CLAIM_MAP` itself: a typo there produces rules that fail the
    compiler's closure check hundreds at a time, and the failure names the rule
    rather than the mapping that caused it.
    """
    known = registry.symbols(RegistryKind.CLAIM)
    return {
        d["indicates"]["claim"] for d in docs
        if d.get("indicates", {}).get("claim") not in known
    }
