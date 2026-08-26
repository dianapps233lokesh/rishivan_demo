"""A URF condition in plain language, so a reader can see WHY a rule fired.

`rag/describe.py` does this for the old extractor's atoms. The Koonji engine
writes conditions in the frame's own vocabulary instead -- registry symbols and
a nested boolean tree rather than a flat list of typed dicts:

    old   {"atoms": [{"type": "planet_in_sign", "planet": "moon", "sign": "aries"}]}
    URF   {"all": [{"occupies_rashi": {"subject": "graha.moon", "rashi": "rashi.aries"}}]}

Both mean "the Moon is in Aries", and the panel has to be able to say so
whichever engine matched the rule.

Two rules of the house, both borrowed from `rag/describe.py` because they were
right there:

  * **An unknown predicate degrades to its own name, never to nothing.** A
    reader shown "strength_band" learns more than a reader shown an empty
    string, and the vocabulary grows faster than this file will.
  * **Nesting is rendered, not flattened.** `any` inside `all` is a different
    rule from the flattened version, and a panel that hides the difference
    invites someone to read the wrong condition and approve it.
"""

from __future__ import annotations

from typing import Any

ORDINALS = {
    1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th",
    7: "7th", 8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th",
}

OPERATORS = ("all", "any", "not", "count", "compare")

HOUSE_GROUP_NAMES = {
    "in_kendra": "an angle (1st, 4th, 7th or 10th)",
    "in_trikona": "a trine (1st, 5th or 9th)",
    "in_dusthana": "a difficult house (6th, 8th or 12th)",
    "in_upachaya": "a growing house (3rd, 6th, 10th or 11th)",
}


def _term(symbol: Any) -> str:
    """A registry symbol as a reader would say it.

    `graha.moon` is the Moon, `bhava.07` is the 7th house, `lord.bhava.09` is
    the 9th lord. A bare variable like `?x` is left alone: it means the rule is
    quantified and inventing a name for it would misdescribe the rule.
    """
    # A bare integer is a house. `occupies_bhava` carries `bhava: 11` as often
    # as `bhava: "bhava.11"`, and rendering the first as "11" produced
    # "Saturn is in 12" in the panel.
    if isinstance(symbol, int):
        return f"the {ORDINALS.get(symbol, symbol)} house"
    text = str(symbol or "")
    if not text or text.startswith("?"):
        return text or "?"
    if text.isdigit():
        return f"the {ORDINALS.get(int(text), text)} house"
    if text.startswith("lord.bhava."):
        number = text.rsplit(".", 1)[-1].lstrip("0") or "0"
        return f"the {ORDINALS.get(int(number), number)} lord" if number.isdigit() else text
    for prefix, render in (
        ("graha.", lambda v: v.title()),
        ("rashi.", lambda v: v.title()),
        ("nakshatra.", lambda v: f"{v.title()} nakshatra"),
    ):
        if text.startswith(prefix):
            return render(text[len(prefix):].replace("_", " "))
    if text.startswith("bhava."):
        number = text.rsplit(".", 1)[-1].lstrip("0") or "0"
        return (f"the {ORDINALS.get(int(number), number)} house"
                if number.isdigit() else text)
    return text.rsplit(".", 1)[-1].replace("_", " ")


def describe_predicate(name: str, args: dict) -> str:
    """One predicate call as a clause."""
    args = args or {}
    subject = _term(args.get("subject"))

    if name == "occupies_bhava":
        return f"{subject} is in {_term(args.get('bhava'))}"
    if name == "occupies_rashi":
        return f"{subject} is in {_term(args.get('rashi'))}"
    if name == "occupies_nakshatra":
        return f"{subject} is in {_term(args.get('nakshatra'))}"
    if name == "occupies_bhava_from":
        return (f"{subject} is in {_term(args.get('bhava'))} "
                f"counted from {_term(args.get('reference'))}")
    if name == "varga_occupies":
        varga = str(args.get("varga") or "?").rsplit(".", 1)[-1].upper()
        return (f"{subject} is in {_term(args.get('rashi') or args.get('bhava'))} "
                f"of the {varga} chart")
    if name in HOUSE_GROUP_NAMES:
        return f"{subject} is in {HOUSE_GROUP_NAMES[name]}"
    if name == "conjunct":
        return f"{subject} is with {_term(args.get('target') or args.get('other'))}"
    if name == "aspects":
        return f"{subject} aspects {_term(args.get('target'))}"
    if name == "same_bhava":
        other = args.get("other") or args.get("target")
        return f"{subject} and {_term(other)} share a house"
    if name == "bhava_in_rashi":
        return f"{_term(args.get('bhava'))} falls in {_term(args.get('rashi'))}"
    if name == "dignity":
        return f"{subject} is {_term(args.get('dignity'))}"
    if name == "combust":
        return f"{subject} is combust"
    if name == "occupant_count":
        op = {"eq": "exactly", "gte": "at least", "lte": "at most"}.get(
            str(args.get("op", "eq")), "exactly")
        n = args.get("n", "?")
        where = _term(args.get("bhava"))
        return (f"{where} is empty" if op == "exactly" and n == 0
                else f"{where} holds {op} {n} planets")
    if name == "strength_band":
        return f"{subject} is {_term(args.get('band'))} in strength"
    if name == "dasha_active":
        level = _term(args.get("level")) or "period"
        return f"the {level} period of {subject} is running"
    if name == "transits_bhava":
        return f"{subject} is transiting {_term(args.get('bhava'))}"

    # Unknown predicate. Its own name, plus whatever it was given, because a
    # reader can still tell whether it looks relevant.
    values = ", ".join(_term(v) for v in args.values() if v is not None)
    readable = name.replace("_", " ")
    return f"{readable} ({values})" if values else readable


def describe_condition(condition: Any) -> str:
    """A whole URF condition tree as one sentence.

    Returns "" for an empty condition rather than a placeholder: the caller
    prints the citation alone in that case, and "no condition" on screen reads
    like a finding when it is an absence.
    """
    if not condition:
        return ""
    if isinstance(condition, list):
        return " and ".join(x for x in (describe_condition(c) for c in condition) if x)
    if not isinstance(condition, dict):
        return str(condition)

    parts: list[str] = []
    for key, value in condition.items():
        if key == "all":
            parts.append(_join(value, " and "))
        elif key == "any":
            inner = _join(value, " or ")
            # Parenthesised so `A and (B or C)` cannot be misread as
            # `(A and B) or C`. The two are different rules.
            parts.append(f"({inner})" if inner and len(value or []) > 1 else inner)
        elif key == "not":
            inner = describe_condition(value)
            parts.append(f"it is not the case that {inner}" if inner else "")
        elif key == "count":
            of = value.get("of") if isinstance(value, dict) else None
            inner = describe_condition(of)
            op = {"gte": "at least", "lte": "at most", "eq": "exactly"}.get(
                (value or {}).get("op", "gte"), "at least")
            parts.append(f"{op} {(value or {}).get('n', '?')} of: {inner}")
        elif key == "compare":
            parts.append("a comparison holds")
        else:
            parts.append(describe_predicate(key, value if isinstance(value, dict) else {}))
    return ", ".join(p for p in parts if p)


def _join(nodes: Any, joiner: str) -> str:
    if not isinstance(nodes, list):
        return describe_condition(nodes)
    return joiner.join(x for x in (describe_condition(n) for n in nodes) if x)
