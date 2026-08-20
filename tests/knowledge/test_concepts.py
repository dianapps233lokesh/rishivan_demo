"""What a rule is ABOUT, read off its own condition atoms.

Every fixture is a real condition from the BPHS vol 1 whole-book run, because the
distinction these tests pin decides which rules reach a user. `lord_of_house_in_house`
carries two houses and they are not interchangeable: in "the 7th lord in the 2nd" the
rule's subject is the 7th house -- marriage -- and the 2nd is only where its lord sits.
Treating both as equal is what let a 9th-house rule about the querent's father surface
on a question about marriage.
"""

from rishivan.knowledge.concepts import concepts_of


def test_the_lord_is_the_subject_not_where_it_sits():
    """BPHS 26.74: "If the 7th Lord is placed in the 2nd House..." -- a marriage rule."""
    c = concepts_of({"atoms": [
        {"type": "lord_of_house_in_house", "lord_of": 7, "house": 2}
    ]})
    assert c.subject_houses == frozenset({7})
    assert c.other_houses == frozenset({2})


def test_the_fathers_rule_is_about_the_ninth_not_the_tenth():
    """BPHS 22.6 "the native's father will be a king". Tagged `father` by the
    extractor, which is why a domain tag routed it to a marriage question. Its subject
    is the 9th."""
    c = concepts_of({"atoms": [
        {"type": "lord_of_house_in_house", "lord_of": 9, "house": 10},
        {"type": "lord_of_house_in_house", "lord_of": 9, "houses": [1, 4, 7, 10]},
    ]})
    assert c.subject_houses == frozenset({9})
    assert 7 in c.other_houses  # present, but only as a location


def test_a_planet_in_a_house_is_about_that_house():
    """BPHS 20.9: "If Saturn is there [the 7th], his wife will be sickly" -- the house
    is the life area the rule speaks about, and the planet is the agent."""
    c = concepts_of({"atoms": [
        {"type": "planet_in_house", "planet": "saturn", "house": 7}
    ]})
    assert c.subject_houses == frozenset({7})
    assert c.planets == frozenset({"saturn"})


def test_an_aspect_target_is_a_house_and_a_factor():
    """BPHS 46.25-31: `aspected_by{planet: mars, target: "3"}`. The target arrives as a
    string from the extractor and must still read as house 3."""
    c = concepts_of({"atoms": [
        {"type": "aspected_by", "planet": "mars", "target": "3"}
    ]})
    assert c.subject_houses == frozenset({3})
    assert c.planets == frozenset({"mars"})
    assert "aspect" in c.factors


def test_a_house_set_keeps_every_member():
    """BPHS 12.4: the Ascendant lord in a kendra -- one atom, four locations."""
    c = concepts_of({"atoms": [
        {"type": "lord_of_house_in_house", "lord_of": 1, "houses": [1, 4, 7, 10]}
    ]})
    assert c.subject_houses == frozenset({1})
    assert c.other_houses == frozenset({1, 4, 7, 10})


def test_a_dignity_rule_has_no_house_at_all():
    """`dignity_is{planet: sun, dignity: exalted}` names no house, so house overlap
    cannot judge it and the planet has to."""
    c = concepts_of({"atoms": [
        {"type": "dignity_is", "planet": "sun", "dignity": "exalted"}
    ]})
    assert c.subject_houses == frozenset()
    assert c.planets == frozenset({"sun"})
    assert "dignity" in c.factors


def test_a_conjunction_names_both_planets():
    c = concepts_of({"atoms": [
        {"type": "conjunct", "planet": "venus", "other": "saturn"}
    ]})
    assert c.planets == frozenset({"venus", "saturn"})
    assert "conjunction" in c.factors


def test_a_divisional_scope_is_recorded_as_a_varga():
    c = concepts_of({"atoms": [
        {"type": "planet_in_house", "planet": "venus", "house": 7, "scope": "d9."}
    ]})
    assert c.vargas == frozenset({"D9"})


def test_a_relative_frame_is_not_a_varga():
    """`from_sun.` re-counts the same chart; it is not a divisional chart."""
    c = concepts_of({"atoms": [
        {"type": "planet_in_house", "planet": "moon", "house": 10, "scope": "from_sun."}
    ]})
    assert c.vargas == frozenset()


def test_the_none_list_counts_too():
    """A negated atom still tells you what the rule is about."""
    c = concepts_of({"none": [
        {"type": "lord_of_house_in_house", "lord_of": 5, "houses": [6, 8, 12]}
    ]})
    assert c.subject_houses == frozenset({5})


def test_an_empty_condition_yields_nothing():
    assert concepts_of({}).subject_houses == frozenset()
    assert concepts_of(None).planets == frozenset()
