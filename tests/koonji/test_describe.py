"""A URF condition in words, for the panel that says WHY a rule fired.

The tests worth having here are the ones about being *wrong* rather than being
absent. An unreadable clause annoys; a clause that reads as a different rule
than the one that fired gets approved by a reviewer who was told something
untrue.
"""

import pathlib

import pytest
import yaml

from rishivan.koonji.describe import describe_condition, describe_predicate


class TestTerms:
    def test_a_graha_is_named(self):
        assert describe_predicate(
            "occupies_rashi", {"subject": "graha.moon", "rashi": "rashi.aries"}
        ) == "Moon is in Aries"

    def test_a_house_lord_reads_as_a_lord_not_a_house(self):
        """`lord.bhava.09` and `bhava.09` differ by one word and describe
        different things; rendering both as "the 9th house" would make a
        lordship rule look like a placement rule."""
        assert describe_predicate(
            "occupies_bhava", {"subject": "lord.bhava.09", "bhava": "bhava.10"}
        ) == "the 9th lord is in the 10th house"

    def test_a_bare_integer_house_is_still_a_house(self):
        """`occupies_bhava` carries `bhava: 11` as often as `bhava: "bhava.11"`.
        Rendering the first literally printed "Saturn is in 12" in the panel."""
        assert describe_predicate(
            "occupies_bhava", {"subject": "graha.saturn", "bhava": 12}
        ) == "Saturn is in the 12th house"

    def test_a_variable_is_left_alone(self):
        """A quantified rule is about "some planet". Naming it would describe a
        rule about one planet, which is a different and narrower claim."""
        assert "?x" in describe_predicate(
            "occupies_bhava", {"subject": "?x", "bhava": "bhava.07"}
        )


class TestStructure:
    def test_all_joins_with_and(self):
        condition = {"all": [
            {"occupies_rashi": {"subject": "graha.moon", "rashi": "rashi.aries"}},
            {"occupies_bhava": {"subject": "graha.mars", "bhava": "bhava.07"}},
        ]}
        assert describe_condition(condition) == (
            "Moon is in Aries and Mars is in the 7th house"
        )

    def test_any_is_parenthesised_inside_all(self):
        """`A and (B or C)` is a different rule from `(A and B) or C`, and a
        reader who cannot see the grouping cannot tell which one fired."""
        condition = {"all": [
            {"occupies_bhava": {"subject": "graha.sun", "bhava": 1}},
            {"any": [
                {"occupies_bhava": {"subject": "graha.mars", "bhava": 6}},
                {"occupies_bhava": {"subject": "graha.mars", "bhava": 8}},
            ]},
        ]}
        rendered = describe_condition(condition)
        assert "(" in rendered and " or " in rendered
        assert rendered.startswith("Sun is in the 1st house and (")

    def test_a_negation_is_never_dropped(self):
        """"unless Jupiter aspects it" reverses the rule. Losing it turns a
        cancelled rule into an asserted one."""
        condition = {"not": {"aspects": {"subject": "graha.jupiter",
                                         "target": "bhava.07"}}}
        assert "not" in describe_condition(condition)

    def test_an_empty_condition_is_empty_not_a_placeholder(self):
        """The caller prints the citation alone. "no condition" on screen reads
        like a finding when it is an absence."""
        assert describe_condition({}) == ""
        assert describe_condition(None) == ""


class TestUnknownPredicates:
    def test_an_unknown_predicate_degrades_to_its_own_name(self):
        """The registry grows faster than this module will. A reader shown
        "shadbala above" learns more than one shown an empty string."""
        rendered = describe_predicate("shadbala_above", {"subject": "graha.sun"})
        assert "shadbala above" in rendered
        assert "Sun" in rendered

    def test_an_unknown_predicate_never_returns_empty(self):
        assert describe_predicate("mystery", {}) != ""


class TestAgainstTheRealCorpus:
    """Every predicate actually on disk renders to something a person can read.

    A unit test can only cover the predicates someone thought of. This walks
    what the corpus really contains, which is how `occupies_bhava`'s bare-integer
    form and `dignity` (not `dignity_is`) were both found.
    """

    @staticmethod
    @pytest.fixture(scope="class")
    def conditions():
        root = pathlib.Path(__file__).resolve().parents[2] / "rishivan/koonji/rules"
        found = []
        for path in root.rglob("*.yaml"):
            for rule in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
                if isinstance(rule, dict) and rule.get("when"):
                    found.append((rule["id"], rule["when"]))
        return found

    def test_the_corpus_is_not_empty(self, conditions):
        """Guards the two tests below: if the glob broke they would pass on
        nothing and report success."""
        assert len(conditions) > 500

    def test_every_condition_renders(self, conditions):
        empty = [rid for rid, when in conditions if not describe_condition(when)]
        assert not empty, f"{len(empty)} conditions render to nothing, e.g. {empty[:3]}"

    def test_no_rendering_leaks_a_registry_prefix(self, conditions):
        """`graha.`, `bhava.`, `level.` are internal. Leaking one into the panel
        is how "the level.maha of Ketu is running" reached a reader."""
        leaked = [
            rid for rid, when in conditions
            if any(p in describe_condition(when)
                   for p in ("graha.", "bhava.", "rashi.", "level.", "band.", "varga."))
        ]
        assert not leaked, f"{len(leaked)} leak a prefix, e.g. {leaked[:3]}"
