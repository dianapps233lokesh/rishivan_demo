"""Render a rule's condition in plain language, so a reader can see WHY it matched.

Written because the panel was unreadable without it. An enumeration verse like BPHS 46.25-31
holds eight condition/effect branches in one paragraph, and three of them were true of a test
chart -- so the panel printed the same thousand-character verse three times, six irrelevant
branches included, and the reader had no way to tell which clause had actually fired.

The condition is the answer to "why am I being shown this", and it is already stored
structurally. It only needed saying in words.
"""

ORDINALS = {
    1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th",
    7: "7th", 8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th",
}

FRAMES = {
    "from_moon.": " from the Moon",
    "from_sun.": " from the Sun",
}


def _houses(atom: dict) -> str:
    values = atom.get("houses") or ([atom["house"]] if atom.get("house") else [])
    names = [ORDINALS.get(int(v), str(v)) for v in values]
    if not names:
        return "?"
    if len(names) == 1:
        return f"the {names[0]} house"
    return "the " + ", ".join(names[:-1]) + f" or {names[-1]} house"


def _signs(atom: dict) -> str:
    values = atom.get("signs") or ([atom["sign"]] if atom.get("sign") else [])
    names = [str(v).title() for v in values]
    if not names:
        return "?"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" or {names[-1]}"


def describe_atom(atom: dict) -> str:
    """One atom as a clause. Unknown types fall back to the raw type rather than being
    dropped: a reader seeing "conjunct" learns more than a reader seeing nothing."""
    kind = atom.get("type")
    frame = FRAMES.get(atom.get("scope") or "", "")
    planet = str(atom.get("planet") or "").title()
    other = str(atom.get("other") or "").title()

    if kind == "planet_in_house":
        return f"{planet} is in {_houses(atom)}{frame}"
    if kind == "planet_in_sign":
        return f"{planet} is in {_signs(atom)}"
    if kind == "lord_of_house_in_house":
        lord = ORDINALS.get(int(atom["lord_of"]), "?") if atom.get("lord_of") else "?"
        return f"the {lord} lord is in {_houses(atom)}{frame}"
    if kind == "lord_of_house_in_sign":
        lord = ORDINALS.get(int(atom["lord_of"]), "?") if atom.get("lord_of") else "?"
        return f"the {lord} lord is in {_signs(atom)}"
    if kind == "conjunct":
        return f"{planet} is with {other}"
    if kind == "aspected_by":
        target = str(atom.get("target") or "")
        where = (
            f"{ORDINALS.get(int(target), target)} house"
            if target.isdigit()
            else target.title()
        )
        return f"{planet} aspects the {where}"
    if kind == "dignity_is":
        return f"{planet} is {str(atom.get('dignity') or '').replace('_', ' ')}"
    if kind == "house_is_empty":
        return f"{_houses(atom)} is empty"
    if kind == "planet_in_nakshatra":
        return f"{planet} is in {str(atom.get('nakshatra') or '').title()} nakshatra"
    if kind == "dasha_of":
        return f"the {atom.get('level')} period of {planet} is running"
    if kind == "transit_over":
        return f"{planet} transits {_houses(atom)}"
    return str(kind)


def describe_condition(condition: dict) -> str:
    """The whole condition as a sentence -- what had to be true for this rule to fire."""
    if not condition:
        return ""
    atoms = condition.get("atoms") or []
    joiner = " or " if (condition.get("combinator") or "all").lower() == "any" else " and "
    clauses = joiner.join(describe_atom(atom) for atom in atoms)
    blocked = condition.get("none") or []
    if blocked:
        unless = " and ".join(describe_atom(atom) for atom in blocked)
        clauses = f"{clauses}, unless {unless}" if clauses else f"not: {unless}"
    return clauses
