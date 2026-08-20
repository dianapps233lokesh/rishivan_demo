"""Decide which rules a chart satisfies.

Two stages. `rule_atom` gives SQL a cheap way to cut the rule base down to candidates
whose tokens the chart even mentions; `satisfies` then evaluates the rule's `condition`
JSONB exactly, because the atom table cannot express a combinator, a negation or a set.

The rule governing every branch below: **an unknown token never matches.** A missing
fact is not a satisfied one, and a matcher that reads absence as agreement produces
confidently wrong readings rather than quiet ones.
"""

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from rishivan.knowledge.compile.atoms import OBJECT_FIELD, atom_to_fact_token
from rishivan.models.knowledge.rule import MATCHABLE_PREDICATE, Rule, RuleAtom

_SET_FORM = {"house": "houses", "sign": "signs"}


@dataclass
class MatchedRule:
    rule_key: str
    condition: dict
    effects: list[dict]
    source: dict
    life_domains: list[str] = field(default_factory=list)
    rishi_affinity: dict[str, float] = field(default_factory=dict)
    withheld_because: list[str] = field(default_factory=list)
    """Non-empty when the condition held but the source cancels it for this chart."""


def _asserted_values(atom: dict, object_field: str) -> list:
    plural = _SET_FORM.get(object_field)
    if plural and atom.get(plural):
        return list(atom[plural])
    value = atom.get(object_field)
    return [] if value is None else [value]


def _same(left, right) -> bool:
    """Compare a chart value with an asserted one, tolerating case and numeric strings.

    The extractor emits `sign: "Aries"` where the chart emits `"aries"`, and `target: "4"`
    where a house is an int. Neither difference should decide a match.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) is bool(right)
    if isinstance(left, str) or isinstance(right, str):
        return str(left).strip().lower() == str(right).strip().lower()
    return left == right


def _atom_holds(atom: dict, tokens: dict) -> bool:
    object_field = OBJECT_FIELD.get(atom.get("type"))
    if object_field is None:
        return False
    try:
        token = atom_to_fact_token(atom, scope=atom.get("scope") or "")
    except ValueError:
        # Reachable in production: rules loaded as `unparsed` carry atoms like
        # `conjunct{planet: "7th lord"}`. They must be inert, not explosive.
        return False
    if token not in tokens:
        return False

    actual = tokens[token]
    if atom.get("type") == "house_is_empty":
        # The token is an occupant count and the atom asserts emptiness, so the
        # comparison is against zero rather than against the house number.
        return actual == 0

    values = _asserted_values(atom, object_field)
    if not values:
        return False
    return any(_same(actual, value) for value in values)


CANCELLING_KINDS = frozenset({"cancel"})
"""Modifier kinds that stop a rule applying rather than colouring it. `strengthen` and
`weaken` belong in the answer's wording; `cancel` is how Neecha Bhanga is expressed."""


def blockers(rule: dict, tokens: dict) -> list[str]:
    """Reasons this rule must not apply, despite its condition holding.

    Exceptions and `cancel` modifiers both count. BPHS 8.1's "bereft of bodily
    pleasures" does not hold for Aries or Libra ascendants, and a rule that fires where
    the book cancels it asserts what the source explicitly denies.

    Returns the reasons rather than a bool, so a caller can say *why* it was withheld.
    """
    reasons: list[str] = []
    for exception in rule.get("exceptions") or []:
        if satisfies(exception.get("condition"), tokens):
            reasons.append(
                exception.get("statement")
                or "an exception recorded for this rule holds for this chart"
            )
    for modifier in rule.get("modifiers") or []:
        if modifier.get("kind") in CANCELLING_KINDS and satisfies(
            modifier.get("condition"), tokens
        ):
            reasons.append(
                modifier.get("statement") or "a cancelling modifier holds for this chart"
            )
    return reasons


def applies(rule: dict, tokens: dict) -> bool:
    """Condition holds AND nothing cancels it. Prefer this over `satisfies` when
    deciding whether to show a rule to a user."""
    if not satisfies(rule.get("condition") or rule.get("formation"), tokens):
        return False
    return not blockers(rule, tokens)


def satisfies(condition: dict | None, tokens: dict) -> bool:
    """Whether this chart satisfies this condition exactly. The condition only —
    exceptions and cancelling modifiers are `applies`."""
    if not condition:
        return False
    atoms = condition.get("atoms") or []
    blocked = condition.get("none") or []
    if not atoms and not blocked:
        # A conditionless rule would fire on every chart ever cast.
        return False

    if atoms:
        combinator = (condition.get("combinator") or "all").lower()
        results = [_atom_holds(atom, tokens) for atom in atoms]
        # Default `all`. The extractor omits the combinator on single-atom conditions
        # where the two agree, so defaulting to `any` would quietly make every
        # multi-atom rule more permissive than the verse it came from.
        if not (any(results) if combinator == "any" else all(results)):
            return False

    return not any(_atom_holds(atom, tokens) for atom in blocked)


async def match_chart(
    session: AsyncSession, *, tokens: dict, limit: int = 40
) -> list[MatchedRule]:
    """Approved rules this chart satisfies.

    Uses `MATCHABLE_PREDICATE` verbatim — the one definition of "may reach a user" — so
    an unapproved rule cannot leak through a hand-written filter. Negated atoms are
    skipped: a rule should not become a candidate on the strength of a token it forbids.
    """
    if not tokens:
        return []

    # Two statements rather than a join: `MATCHABLE_PREDICATE` is raw SQL over
    # unqualified names, and both `rule` and `rule_atom` have a `deleted_at`, so joining
    # makes it ambiguous and Postgres refuses the query. Qualifying it here would mean a
    # second copy of that one definition, so it is applied where only `rule` is in scope.
    candidate_ids = (
        select(RuleAtom.rule_id)
        .where(RuleAtom.fact_token.in_(list(tokens)), RuleAtom.negate.is_(False))
        .distinct()
    )
    rules = (
        await session.execute(
            select(Rule).where(Rule.id.in_(candidate_ids), text(MATCHABLE_PREDICATE))
        )
    ).scalars()

    matched = []
    for rule in rules:
        if not satisfies(rule.condition, tokens):
            continue
        effect = rule.effect or {}
        withheld = blockers(
            {
                "exceptions": effect.get("exceptions") or [],
                "modifiers": effect.get("modifiers") or [],
            },
            tokens,
        )
        if withheld:
            continue
        matched.append(
            MatchedRule(
                rule_key=rule.rule_key,
                condition=rule.condition or {},
                effects=effect.get("effects") or [],
                source=rule.source or {},
                life_domains=rule.life_domains or [],
                rishi_affinity=effect.get("rishi_affinity") or {},
            )
        )
        if len(matched) >= limit:
            break
    return matched
