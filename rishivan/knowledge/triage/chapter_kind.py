"""Classify a chapter from its printed title — free, and it settles whole chapters.

BPHS devotes entire chapters to non-rule content: "PROPITIATION OF PLANETS" is 77 verses
of remedy, "ASHTAKAVARGA" is computation. Deciding once per chapter removes hundreds of
paid classifier calls and is more consistent than per-verse guessing — a chapter cannot
be half remedy.

Titles come from the book's own table of contents, so this reads the author's structure
rather than imposing one. Unmatched returns None and falls through to per-verse
classification.
"""

import re

from rishivan.models.knowledge.item import ItemKind

NOT_EXPRESSIBLE_SUBJECTS: tuple[tuple[str, str], ...] = (
    # (title pattern, the capability the fact engine is missing)
    (r"karakamsa|karakamsha|chara\s*dasa|jaimini", "jaimini: chara karakas, karakamsha"),
    (r"non[\s-]*luminous|upagraha|dhuma|gulika|mandi", "upagrahas (Dhuma, Gulika, ...)"),
    (r"\bpada[s]?\b|arudha|upa\s*pada", "arudha / upapada"),
    (r"argala", "argala (planetary intervention)"),
    (r"ashtakavarga|ashtaka\s*varga", "ashtakavarga bindus"),
    (r"kalachakra", "kalachakra dasa (non-Vimshottari)"),
    (r"\bbala[s]?\b|shadbala|evaluation of strength|planetary ray", "shadbala / strength model"),
    (r"sudarshana", "sudarshana chakra"),
    (r"special ascendant|bhava lagna|hora lagna|ghati lagna", "special ascendants"),
    (r"nabhasa", "quantifier over all planets (nabhasa yogas)"),
    (r"horary|prashna|prasna", "prashna (horary) time model"),
    (r"panchabhuta|guna", "panchabhuta / guna classification"),
    (r"lost horoscop", "birth-time rectification"),
    # Measured on the vol 1 whole-book run: chapter 47 "AVASTHAS OF PLANETS" produced
    # 161 declines and zero rules -- 28% of every decline in the book, and 161 AI calls
    # spent to be told what the title already said. Avastha (deepta, cheshta, sleeping,
    # awake) is a planetary-state model the vocabulary has no atom for.
    (r"avastha|cheshta|deepta|shayana|sleeping state", "avastha (planetary states)"),
)
"""Chapters whose *subject* the fact vocabulary cannot express, with the gap named.

These produced the worst extraction errors. Faced with Dhuma — an upagraha absent from
the vocabulary — the model did not decline; it emitted `planet_in_house{planet: rahu}`,
a different body entirely, in a rule that was schema-valid and cited a real verse.

The model always produces the nearest expressible thing rather than nothing, so the fix
is to stop asking. These route to destination B with the gap recorded in
`vocabulary_gap`, turning 361 units of unusable extraction into a ranked backlog.

Checked BEFORE the effects/results escape hatch below: "EFFECTS OF KARAKAMSA" is
predictive in form and inexpressible in substance, and the substance decides.
"""


def missing_capability(title: str | None) -> str | None:
    """The vocabulary gap this chapter's subject depends on, if any."""
    if not title:
        return None
    text = title.lower()
    for pattern, capability in NOT_EXPRESSIBLE_SUBJECTS:
        if re.search(pattern, text):
            return capability
    return None

_TITLE_RULES: tuple[tuple[str, ItemKind], ...] = (
    # Remedial chapters: whole chapters of propitiation, never predictions.
    (r"propitiat|remedial|remedies|shanti|pacificat", ItemKind.remedy),
    # Computation chapters. Ashtakavarga and shadbala chapters state how to compute a
    # quantity; they are the specification for facts, not rules over them.
    (r"ashtakavarga|shadbala|sodasa ?varga|calculat|computat|how to (?:find|cast)"
     r"|arithmetic|ayanamsa|reduction", ItemKind.formula),
    # Reference matrices: aspect strengths, varga lords, seasons, dasha year lengths.
    (r"\baspects? of\b|table|years? of the|lords? of the (?:signs?|vargas?)"
     r"|division(?:s)? of a sign|measure of", ItemKind.reference_table),
    # Descriptive chapters: what a planet or sign *is*, not what it causes.
    (r"described|description|characters?(?: and description)?|nature of"
     r"|significations?|nomenclature|definitions?", ItemKind.classification),
    # Cosmology and devotional framing.
    (r"creation|incarnation|salutation|invocation|benedict", ItemKind.narrative),
)


def kind_for_title(title: str | None) -> ItemKind | None:
    """The destination-B kind this whole chapter belongs to, or None to fall through.

    None is the safe answer: it means "decide per verse", which is what happens for
    every predictive chapter (house effects, yogas, dasha results).
    """
    if not title:
        return None
    text = title.lower()
    # Substance before form: a chapter can be phrased as prediction and still be about
    # something the engine cannot represent.
    if missing_capability(title):
        return ItemKind.out_of_domain
    # A chapter about the *effects* of something is predictive no matter what other
    # words it contains -- "EFFECTS OF THE ASPECTS" is rules, not a reference table.
    if re.search(r"\beffects?\b|\bresults?\b|\byoga", text):
        return None
    for pattern, kind in _TITLE_RULES:
        if re.search(pattern, text):
            return kind
    return None
