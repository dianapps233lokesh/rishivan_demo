"""Decide which rules a chart satisfies.

Two stages, for two different reasons. `rule_atom` gives SQL a cheap way to reduce the
whole rule base to a handful of candidates whose tokens the chart even mentions.
`satisfies` then evaluates the rule's `condition` JSONB exactly, because the atom table
cannot express a combinator, a negation or a set -- it was never meant to.

The rule that governs every branch below: **an unknown token never matches.** BPHS vol 1
has 9 valid rules using `dignity_is`, `conjunct` or `aspected_by`, which the chart engine
does not yet compute. Those rules must be inert -- not exceptions, and above all not
passes. A missing fact is not a satisfied one, and a matcher that treats absence as
agreement produces confidently wrong readings rather than quiet ones.
"""

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.compile.atoms import OBJECT_FIELD, atom_to_fact_token
from app.models.knowledge.rule import MATCHABLE_PREDICATE, Rule, RuleAtom

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
    """Non-empty when the condition held but the source cancels it for this chart. Kept
    rather than dropped so a reviewer can see the near-miss and a UI can explain it."""


def _asserted_values(atom: dict, object_field: str) -> list:
    plural = _SET_FORM.get(object_field)
    if plural and atom.get(plural):
        return list(atom[plural])
    value = atom.get(object_field)
    return [] if value is None else [value]


def _same(left, right) -> bool:
    """Compare a chart value with an asserted one, tolerating case and numeric strings.

    The extractor has emitted `sign: "Aries"` where the chart emits `"aries"`, and
    `target: "4"` where a house is an int. Neither difference should decide a match.
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
        # An incomplete or unknown atom cannot be shown to hold. This is reachable in
        # production: 22 rules loaded as `unparsed` carry atoms like
        # `conjunct{planet: "7th lord"}`, and they must be inert rather than explosive.
        return False
    if token not in tokens:
        return False

    actual = tokens[token]
    if atom.get("type") == "house_is_empty":
        # The token is an occupant count, and the atom asserts emptiness rather than a
        # value, so the comparison is against zero rather than against the house number.
        return actual == 0

    values = _asserted_values(atom, object_field)
    if not values:
        return False
    return any(_same(actual, value) for value in values)


CANCELLING_KINDS = frozenset({"cancel"})
"""Modifier kinds that stop a rule applying rather than colouring it.

`strengthen` and `weaken` change how strongly the effect is stated and belong in the
answer, not in the match. `cancel` is how Neecha Bhanga is expressed -- a debilitation
undone -- and a rule whose cancellation holds must not fire at all.
"""


def blockers(rule: dict, tokens: dict) -> list[str]:
    """Reasons this rule must not apply to this chart, despite its condition holding.

    Two sources, and neither was consulted until now:

    **Exceptions.** BPHS 8.1's "if the 8th lord is in the Ascendant the native is bereft
    of bodily pleasures" carries a commentary exception -- in Aries and Libra ascendants
    it does not apply, because Mars and Venus become the 8th lord and their moolatrikona
    is the Ascendant. Worked Example 1 of the extraction prompt exists to capture exactly
    that, and the matcher ignored it. A rule that fires where the book cancels it is worse
    than a rule that never fires: it asserts something the source explicitly denies.

    **Cancelling modifiers.** Same logic, expressed as `kind: cancel`.

    Returns the human-readable reasons rather than a bool, so the caller can say *why* a
    rule was withheld instead of silently dropping it.
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
    """Whether the whole rule applies: condition holds AND nothing cancels it.

    `satisfies` answers only the condition. Callers deciding whether to show a rule to a
    user want this instead -- the difference is a rule the source cancels.
    """
    if not satisfies(rule.get("condition") or rule.get("formation"), tokens):
        return False
    return not blockers(rule, tokens)


def satisfies(condition: dict | None, tokens: dict) -> bool:
    """Whether this chart satisfies this condition, exactly.

    The condition ONLY. Exceptions and cancelling modifiers are separate -- see `applies`.
    """
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
        # Default to `all`. The extractor omits the combinator on single-atom conditions,
        # where the two are equivalent, so defaulting to `any` would silently make every
        # multi-atom rule far more permissive than the verse it came from.
        if not (any(results) if combinator == "any" else all(results)):
            return False

    return not any(_atom_holds(atom, tokens) for atom in blocked)


async def match_chart(
    session: AsyncSession, *, tokens: dict, limit: int = 40
) -> list[MatchedRule]:
    """Approved rules this chart satisfies.

    The SQL stage uses `MATCHABLE_PREDICATE` verbatim -- the one definition of "may reach
    a user" -- so an unapproved or unparsed rule cannot leak through a hand-written
    filter. It also skips negated atoms: a rule whose only mentioned token is the one it
    forbids should not become a candidate on that basis.
    """
    if not tokens:
        return []

    # Two statements rather than one join, because `MATCHABLE_PREDICATE` is raw SQL over
    # unqualified column names -- `status`, `approved_at`, `deleted_at` -- and `rule` and
    # `rule_atom` both have a `deleted_at`. Joining them makes the predicate ambiguous and
    # Postgres refuses the query outright. Qualifying it here would mean keeping a second
    # copy of the one definition of "may reach a user", so instead the predicate is
    # applied where only `rule` is in scope.
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
        # An exception or a cancelling modifier that holds means the source itself denies
        # this rule for this chart, so it must not be presented as applying.
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
