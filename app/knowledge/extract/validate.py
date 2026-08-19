"""S6 — deterministic validation of extracted atoms. The LLM proposes; this decides.

This is the stage the whole architecture leans on. `response_schema` cannot express
"if type is lord_of_house_in_house then house is required" -- Gemini supports no
`oneOf`/`if-then`, and a per-type schema would exceed the 160-leaf-field budget. So
the atom schema is a flat union, and the model demonstrably leaks: on a real BPHS 26.85
call it returned

    {"type": "lord_of_house_in_house", "lord_of": 8, "level": "maha", "scope": ""}

which is schema-valid and useless -- `level` belongs to `dasha_of`, and the missing
`house` means the atom never says where the 8th lord sits. Unvalidated, that compiles
to a rule that matches nothing while looking perfectly well-formed.

So validation is not a safety net bolted on; it is where correctness actually lives.
Every rejection carries a reason, and rejected rules are retried once with wider
context before being filed `unparsed` -- degraded, never dropped.
"""

from dataclasses import dataclass, field

from app.astro.vocab import (
    CONDITION_TOKEN_TEMPLATES,
    EMITTED_SCOPES,
    PLANET_TOKEN_NAME,
)
from app.knowledge.extract.prompt import CONDITION_ARGUMENTS

PLANET_NAMES = frozenset(PLANET_TOKEN_NAME.values())
VALID_SCOPES = frozenset(EMITTED_SCOPES)
TIMING_TYPES = frozenset({"dasha_of", "transit_over"})
"""Atoms that describe *when*, not *what is promised*. Their presence in `formation`
is the violation the client states as absolute: timing cannot manufacture a promise."""

OPTIONAL_ARGUMENTS = frozenset({"scope"})

_SET_FORM = {"house": "houses", "sign": "signs"}
"""A required scalar field may instead be supplied as its set form -- `houses: [6,8,12]`
in place of `house: 6`. Both satisfy the requirement; supplying both is contradictory."""


@dataclass
class AtomProblem:
    index: int
    atom_type: str
    reason: str

    def __str__(self) -> str:
        return f"atom[{self.index}] {self.atom_type}: {self.reason}"


@dataclass
class ValidationResult:
    problems: list[AtomProblem] = field(default_factory=list)
    timing_atoms_moved: int = 0
    atoms_merged: int = 0
    stripped_atoms: int = 0
    declined: bool = False
    """The model said it cannot express this verse. Not a defect -- a routing decision:
    the unit belongs in destination B with its reason, and must never be counted as a
    failed rule. Scoring declines as invalid rules is what put the first graded sample
    at 29%: 13 of its 22 "failures" were the extractor correctly refusing."""

    @property
    def ok(self) -> bool:
        return not self.problems

    def __str__(self) -> str:
        return "; ".join(str(p) for p in self.problems) or "ok"


def validate_atom(atom: dict, index: int = 0) -> list[AtomProblem]:
    """Every way a single atom can be wrong, with a reason for each."""
    problems: list[AtomProblem] = []
    atom_type = atom.get("type") or "<missing>"

    def bad(reason: str) -> None:
        problems.append(AtomProblem(index, atom_type, reason))

    if atom_type not in CONDITION_ARGUMENTS:
        bad(
            "unknown condition type"
            if atom_type != "<missing>"
            else "no condition type given"
        )
        return problems

    allowed = set(CONDITION_ARGUMENTS[atom_type])
    required = allowed - OPTIONAL_ARGUMENTS
    supplied = {k for k, v in atom.items() if k != "type" and v not in (None, "", [])}

    # A set form satisfies its scalar requirement: `houses: [6,8,12]` says where the
    # lord may sit just as `house: 6` does, and it is how a disjunction is expressed.
    for scalar, plural in _SET_FORM.items():
        if scalar in allowed:
            allowed.add(plural)
            if plural in supplied and scalar in supplied:
                bad(f"supply either {scalar!r} or {plural!r}, not both")
            elif plural in supplied:
                required.discard(scalar)

    for extra in sorted(supplied - allowed):
        bad(f"field {extra!r} does not belong to this condition type")
    for missing in sorted(required - supplied):
        bad(f"required field {missing!r} is missing")

    if (planet := atom.get("planet")) and planet not in PLANET_NAMES:
        bad(
            f"planet {planet!r} is not a token name "
            f"(use e.g. 'saturn', never the book's 'Sa')"
        )
    if (other := atom.get("other")) and other not in PLANET_NAMES:
        bad(f"planet {other!r} is not a token name")
    if (scope := atom.get("scope")) and scope not in VALID_SCOPES:
        bad(f"scope {scope!r} is not emitted by the fact engine")
    for key in ("house", "lord_of"):
        if (value := atom.get(key)) is not None and not 1 <= int(value) <= 12:
            bad(f"{key} must be 1-12, got {value!r}")
    for house in atom.get("houses") or []:
        if not 1 <= int(house) <= 12:
            bad(f"houses contains {house!r}, must be 1-12")
    return problems


# A planet occupies exactly one house and one sign. Two such atoms about the same
# planet, ANDed together, describe a chart that cannot exist.
_EXCLUSIVE_BY: dict[str, tuple[str, str]] = {
    "planet_in_house": ("planet", "house"),
    "planet_in_sign": ("planet", "sign"),
    "lord_of_house_in_house": ("lord_of", "house"),
    "lord_of_house_in_sign": ("lord_of", "sign"),
    "planet_in_nakshatra": ("planet", "nakshatra"),
}


def impossible_conjunctions(condition: dict) -> list[AtomProblem]:
    """Atoms that cannot all hold at once.

    This check exists because the model produced them. Asked to express "Mars in any
    of the kendras or the 8th", and given no disjunction (`any_groups` was cut to stay
    inside the 160-leaf-field schema budget), it emitted Mars in houses 1, 4, 7, 8 and
    10 joined by `all`. That is schema-valid, passes every per-atom check, and matches
    no chart that has ever existed -- a rule guaranteed never to fire, which is exactly
    the silent failure the whole pipeline is built to prevent.

    Flattening a disjunction into a conjunction is the model's most damaging habit
    here, so it is caught mechanically rather than trusted away.
    """
    if (condition.get("combinator") or "all") != "all":
        return []
    problems: list[AtomProblem] = []
    seen: dict[tuple[str, str, str], str] = {}
    for index, atom in enumerate(condition.get("atoms") or []):
        atom_type = atom.get("type")
        if atom_type not in _EXCLUSIVE_BY:
            continue
        subject_key, value_key = _EXCLUSIVE_BY[atom_type]
        subject, value = atom.get(subject_key), atom.get(value_key)
        if subject is None or value is None:
            continue
        if atom.get(_SET_FORM.get(value_key, "")):
            continue  # already a disjunction; nothing to contradict
        key = (atom_type, subject_key, str(subject))
        previous = seen.get(key)
        if previous is not None and previous != str(value):
            problems.append(
                AtomProblem(
                    index,
                    atom_type,
                    f"impossible conjunction: {subject_key}={subject} cannot have "
                    f"{value_key} {previous} AND {value} simultaneously "
                    f"(a disjunction was flattened into `all`)",
                )
            )
        else:
            seen[key] = str(value)
    return problems


def _required_for(atom_type: str) -> frozenset[str]:
    return frozenset(
        name
        for name in CONDITION_ARGUMENTS.get(atom_type, {})
        if name not in OPTIONAL_ARGUMENTS
    )


def _supplied(atom: dict, atom_type: str) -> frozenset[str]:
    """Which required fields this atom actually provides, set forms included."""
    supplied = set()
    for name in _required_for(atom_type):
        if atom.get(name) is not None or atom.get(_SET_FORM.get(name, "")):
            supplied.add(name)
    return frozenset(supplied)


def merge_split_atoms(condition: dict | None, key: str = "atoms") -> int:
    """Rejoin one atom the model split in half. Returns how many merges were made.

    The flat atom schema has no way to say "these fields belong together", and the model
    exploits that: asked for "the 5th lord in the 6th house" it returned
    `{lord_of: 5}` and `{house: 6}` as two `lord_of_house_in_house` atoms. Neither half
    is a claim -- one says the 5th lord is somewhere, the other says some lord is in the
    6th -- and under `all` the pair means something the verse never said. It happened on
    3 of 18 rule-destined verses in the graded sample, always this same shape.

    So it is repaired rather than rejected, on the same reasoning as moving a misplaced
    timing atom: the intent is unambiguous and the fix is mechanical. The merge is
    deliberately conservative -- it fires only when a type has exactly two incomplete
    atoms, they supply disjoint fields, and the union is complete -- because a wrong
    merge would fabricate a condition, which is the one thing worse than rejecting one.
    Anything less clear-cut still fails validation with its fields missing.
    """
    if not condition:
        return 0
    atoms = condition.get(key) or []
    merged = 0
    for atom_type in {atom.get("type") for atom in atoms}:
        if atom_type not in CONDITION_ARGUMENTS:
            continue
        required = _required_for(atom_type)
        partial = [
            atom
            for atom in atoms
            if atom.get("type") == atom_type and _supplied(atom, atom_type) != required
        ]
        if len(partial) != 2:
            continue
        left, right = partial
        left_has, right_has = _supplied(left, atom_type), _supplied(right, atom_type)
        if left_has & right_has or left_has | right_has != required:
            continue
        for key, value in right.items():
            left.setdefault(key, value)
        atoms.remove(right)
        merged += 1
    if merged:
        condition[key] = atoms
    return merged


def validate_condition(condition: dict | None, *, label: str) -> list[AtomProblem]:
    problems: list[AtomProblem] = []
    if not condition:
        return problems
    for slot in ("atoms", "none"):
        for i, atom in enumerate(condition.get(slot) or []):
            for problem in validate_atom(atom, i):
                problem.reason = f"{label}.{slot}: {problem.reason}"
                problems.append(problem)
    for problem in impossible_conjunctions(condition):
        problem.reason = f"{label}: {problem.reason}"
        problems.append(problem)
    return problems


PLANET_SYNONYMS: dict[str, tuple[str, ...]] = {
    "sun": ("sun", "surya", "ravi", "aditya"),
    "moon": ("moon", "chandra", "soma", "sasi"),
    "mars": ("mars", "kuja", "mangal", "angaraka"),
    "mercury": ("mercury", "budha"),
    "jupiter": ("jupiter", "guru", "brihaspati", "jeeva"),
    "venus": ("venus", "shukra", "sukra", "bhrigu"),
    "saturn": ("saturn", "shani", "sani"),
    "rahu": ("rahu",),
    "ketu": ("ketu",),
}
"""Book spellings for each token name, so grounding does not fail on transliteration."""


SIGN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "aries": ("aries", "mesha", "mesa"),
    "taurus": ("taurus", "vrishabha", "vrisha", "vrsabha"),
    "gemini": ("gemini", "mithuna"),
    "cancer": ("cancer", "karka", "kataka"),
    "leo": ("leo", "simha"),
    "virgo": ("virgo", "kanya"),
    "libra": ("libra", "tula"),
    "scorpio": ("scorpio", "vrischika", "vrscika"),
    "sagittarius": ("sagittarius", "dhanu"),
    "capricorn": ("capricorn", "makara"),
    "aquarius": ("aquarius", "kumbha"),
    "pisces": ("pisces", "meena", "mina"),
}

SIGN_CLASSES: dict[str, tuple[str, ...]] = {
    "aries": ("movable", "moveable", "chara", "cardinal", "fiery"),
    "cancer": ("movable", "moveable", "chara", "cardinal", "watery"),
    "libra": ("movable", "moveable", "chara", "cardinal", "airy"),
    "capricorn": ("movable", "moveable", "chara", "cardinal", "earthy"),
    "taurus": ("fixed", "sthira", "immovable", "earthy"),
    "leo": ("fixed", "sthira", "immovable", "fiery"),
    "scorpio": ("fixed", "sthira", "immovable", "watery"),
    "aquarius": ("fixed", "sthira", "immovable", "airy"),
    "gemini": ("dual", "common", "dvisvabhava", "mutable", "airy"),
    "virgo": ("dual", "common", "dvisvabhava", "mutable", "earthy"),
    "sagittarius": ("dual", "common", "dvisvabhava", "mutable", "fiery"),
    "pisces": ("dual", "common", "dvisvabhava", "mutable", "watery"),
}
"""Sign classes whose membership is fixed, so naming the class grounds the members.

The distinction this table draws is the whole point of it. "The Sun in a movable sign"
(BPHS 10.8) determines four signs and nothing else -- Aries, Cancer, Libra, Capricorn,
always, for every chart and every planet -- so expanding it invents nothing, and
rejecting the expansion threw away three correct rules in the first graded sample.
"Exalted" looks similar and is not: it is a *different* sign per planet, so expanding it
to a sign list is the fabrication `ungrounded_values` exists to catch.

The test is whether the class alone fixes the members. Movable/fixed/dual and the
elemental triplicities pass it; every dignity fails it.

Only the adjectival element forms are listed. Matching is by substring, and BPHS 10.8 --
the very verse this table was built for -- opens with "the situation of the earthen
lamp", which would ground Capricorn on the bare word "earth". `odd`/`even` are omitted
for the same reason: "even" hides inside seven, eleven and evening.
"""

DIGNITY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "exalted": ("exalt", "uchcha", "uccha"),
    "debilitated": ("debilit", "neecha", "nica", "fall"),
    "moolatrikona": ("moolatrikona", "mooltrikona", "trikona"),
    "own_sign": ("own sign", "own house", "swakshetra", "sva"),
}


def members_of(class_word: str) -> frozenset[str]:
    """Every sign belonging to a class word, e.g. "movable" -> the four chara signs."""
    return frozenset(
        sign for sign, words in SIGN_CLASSES.items() if class_word in words
    )


def ungrounded_values(rule: dict, source_text: str) -> list[AtomProblem]:
    """Signs and dignities the rule names that the verse never names.

    This exists because of BPHS 24.2. The verse says the 11th lord "is exalted"; the
    extractor wrote `lord_of_house_in_sign{lord_of: 11, sign: "aries"}`. Exaltation is
    Aries only for the Sun -- which sign it is depends entirely on which planet happens
    to be the 11th lord -- so that atom is a specific, checkable, false claim. It passed
    every structural check and the planet-grounding check, because no planet was named.

    Grounding a *value* is the same idea as grounding a planet: if the text does not say
    "Aries", the rule may not claim Aries.
    """
    if not source_text:
        return []
    text = source_text.lower()
    problems: list[AtomProblem] = []
    condition = rule.get("formation") or {}
    atoms = (condition.get("atoms") or []) + (condition.get("none") or [])
    # The class-completeness check below needs the whole disjunction, not one atom.
    # A verse's "movable sign" is expressible two equivalent ways -- one atom carrying
    # `signs: [aries, cancer, libra, capricorn]`, or four `any`-combined atoms each
    # carrying one -- and rejecting the second form threw away three correct rules.
    asserted = {
        str(sign).lower()
        for atom in atoms
        for sign in ([atom.get("sign")] if atom.get("sign") else atom.get("signs") or [])
    }
    for index, atom in enumerate(atoms):
        atom_type = atom.get("type") or "?"
        named = atom.get("sign")
        signs = [named] if named else list(atom.get("signs") or [])
        for sign in signs:
            key = str(sign).lower()
            if any(word in text for word in SIGN_SYNONYMS.get(key, (key,))):
                continue
            licensed_by = [
                word for word in SIGN_CLASSES.get(key, ()) if word in text
            ]
            if licensed_by and any(
                members_of(word) <= asserted for word in licensed_by
            ):
                continue
            if licensed_by:
                problems.append(
                    AtomProblem(
                        index,
                        atom_type,
                        f"sign={sign!r} is licensed only by the class "
                        f"{licensed_by[0]!r}, but the atom names part of that class "
                        f"instead of all of it: {sorted(asserted)}. A class must be "
                        f"expanded whole or not at all",
                    )
                )
                continue
            problems.append(
                AtomProblem(
                    index,
                    atom_type,
                    f"sign={sign!r} is never named in the verse -- a specific sign was "
                    f"invented for a general statement (e.g. 'exalted' is not 'aries'; "
                    f"which sign depends on which planet)",
                )
            )
        dignity = atom.get("dignity")
        if dignity and not any(
            word in text for word in DIGNITY_SYNONYMS.get(str(dignity), (str(dignity),))
        ):
            problems.append(
                AtomProblem(
                    index,
                    atom_type,
                    f"dignity={dignity!r} is never stated in the verse",
                )
            )
    return problems


def ungrounded_planets(rule: dict, source_text: str) -> list[AtomProblem]:
    """Planets the rule names that the verse never mentions.

    This catches the single most dangerous error the pipeline can make, and it caught a
    real one: BPHS 27.2 is about **Dhuma**, an upagraha computed from the Sun's
    longitude and absent from the fact vocabulary. Rather than declaring it
    inexpressible, the model emitted `planet_in_house{planet: rahu, house: 1}` -- a
    different body entirely. That rule is schema-valid, passes every per-atom check,
    cites a real verse in a real chapter, and asserts something the text does not say.

    Substitution is invisible to structural validation, so it needs its own check.
    """
    if not source_text:
        return []
    text = source_text.lower()
    problems: list[AtomProblem] = []
    formation = rule.get("formation") or {}
    timing = (rule.get("timing") or {}).get("activation_factors") or {}
    # Timing atoms need grounding just as much as formation atoms, and originally did
    # not get it. BPHS 46.15-21 says "the Dasa of the 6th Lord" and passed as VALID
    # carrying `dasha_of{planet: sun}` -- the Sun substituted for a house lord, in the
    # one place nothing was looking. Only 1 of vol 1's 376 valid rules was affected, but
    # vol 2 devotes chapters 54, 61, 63, 64 and 66 to dasha results.
    atoms = (
        (formation.get("atoms") or [])
        + (formation.get("none") or [])
        + (timing.get("atoms") or [])
        + (timing.get("none") or [])
    )
    for index, atom in enumerate(atoms):
        for key in ("planet", "other"):
            name = atom.get(key)
            if not name:
                continue
            if not any(word in text for word in PLANET_SYNONYMS.get(name, (name,))):
                problems.append(
                    AtomProblem(
                        index,
                        atom.get("type") or "?",
                        f"{key}={name!r} is never mentioned in the verse -- a planet "
                        f"was substituted for something the vocabulary cannot express",
                    )
                )
    return problems


def validate_rule(rule: dict, *, source_text: str = "") -> ValidationResult:
    """Validate one extracted rule and enforce the promise/timing split.

    Timing atoms found in `formation` are **moved** rather than rejected: the model
    misplacing one is an expected, mechanically fixable error, and moving it makes
    "timing cannot manufacture a natal promise" structural instead of advisory. If the
    move empties `formation`, the rule is legitimately `timing`-category -- common in
    BPHS's dasha-result chapters -- not a defective `formation` rule.

    A rule with `expressible: false` is *declined*, not invalid. It carries no atoms out
    of here -- whatever it asserted is stripped, because "I cannot express this" plus a
    partial condition is the worst of both -- and it is valid exactly when it names the
    concept it is missing. The caller routes it to destination B.
    """
    result = ValidationResult()
    formation = rule.get("formation") or {}
    timing = rule.setdefault("timing", {}).setdefault(
        "activation_factors", {"atoms": []}
    )
    timing.setdefault("atoms", [])

    if rule.get("expressible") is False:
        result.declined = True
        # BPHS 15.1 says "a benefic in the 2nd House gives wealth"; the model set
        # expressible=false and still wrote `planet_in_house{jupiter, 2}`. Stripping is
        # not leniency -- the atoms are the fabrication, and the decline is the correct
        # part of the answer. `stripped_atoms` keeps the substitution visible in the run
        # summary instead of failing a decision that was right.
        result.stripped_atoms = len(formation.get("atoms") or []) + len(
            formation.get("none") or []
        )
        formation["atoms"] = []
        formation["none"] = []
        if not rule.get("out_of_scope_reason"):
            result.problems.append(
                AtomProblem(-1, "rule", "expressible=false without out_of_scope_reason")
            )
        return result

    # `none` splits the same way `atoms` does -- BPHS 18.1-3's negated 5th-lord clause
    # arrived as two halves there, and a fix that only covered `atoms` would leave the
    # identical fault standing on the other list.
    result.atoms_merged = merge_split_atoms(formation) + merge_split_atoms(
        formation, "none"
    )
    # "kendra or trikona" arrives as [1,4,7,10,1,5,9] -- house 1 is in both sets. Left
    # alone it becomes two identical `rule_atom` rows for one condition.
    for atom in formation.get("atoms") or []:
        for key in ("houses", "signs"):
            if atom.get(key):
                atom[key] = list(dict.fromkeys(atom[key]))

    keep = []
    for atom in formation.get("atoms") or []:
        if atom.get("type") in TIMING_TYPES:
            timing["atoms"].append(atom)
            result.timing_atoms_moved += 1
        else:
            keep.append(atom)
    if formation:
        formation["atoms"] = keep

    # Only a rule that actually has timing atoms is a timing rule. Relabelling every
    # empty formation as `timing` laundered non-rules into valid-looking rules: BPHS's
    # Tribhaga Bala, Pada-calculation and Argala-formation verses all arrived with no
    # atoms at all and passed, because the "no condition" check was satisfied by the
    # very label this line had just invented.
    has_timing = bool(timing.get("atoms"))
    if not keep and not (formation.get("none") or []):
        if has_timing:
            rule["rule_category"] = "timing"
        else:
            result.problems.append(
                AtomProblem(
                    -1,
                    "rule",
                    "no condition at all: neither a natal atom nor a timing atom, so "
                    "this states something other than a rule (destination B)",
                )
            )

    result.problems += validate_condition(formation, label="formation")
    result.problems += validate_condition(
        rule.get("timing", {}).get("activation_factors"), label="timing"
    )
    for i, modifier in enumerate(rule.get("modifiers") or []):
        result.problems += validate_condition(
            modifier.get("condition"), label=f"modifiers[{i}].{modifier.get('kind')}"
        )
    for i, exception in enumerate(rule.get("exceptions") or []):
        result.problems += validate_condition(
            exception.get("condition"), label=f"exceptions[{i}]"
        )

    if not rule.get("effects"):
        result.problems.append(
            AtomProblem(-1, "rule", "no effects: a rule that predicts nothing")
        )
    result.problems += ungrounded_planets(rule, source_text)
    result.problems += ungrounded_values(rule, source_text)
    return result


assert set(CONDITION_ARGUMENTS) == set(CONDITION_TOKEN_TEMPLATES), (
    "condition argument schemas have drifted from the vocabulary lock"
)
