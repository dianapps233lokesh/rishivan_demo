"""Books on disk to rules the engine can fire, without a model in the loop.

Three thousand units were extracted by the earlier pipeline into a schema the
engine cannot read. This is the conversion, and the tests below are almost
entirely about the ways it is allowed to *fail*, because that is where the
damage is:

  * an atom dropped rather than mapped widens the rule silently;
  * a life_domain guessed rather than mapped attributes a verse to the wrong
    part of a life;
  * a rule written without compiling is a rule nobody can load.

The end-to-end test at the bottom is the one that matters: the real corpus,
converted, compiled, indexed, and fired on a real chart with a citation.
"""

import pytest

from rishivan.koonji.compiler import compile_rules
from rishivan.koonji.convert import (
    CLAIM_MAP,
    DOMAIN_WEIGHT,
    Unmappable,
    convert_corpus,
    convert_unit,
    map_atom,
    map_formation,
    rule_id_for,
    unknown_claims,
)
from rishivan.koonji.corpus import (
    BOOKS,
    SCHOOL_BY_BOOK,
    Unit,
    clean_translation,
    corpus_files,
    load_corpus,
    survey,
    to_passages,
)
from rishivan.koonji.registry import seed_registry
from rishivan.koonji.urf import RegistryKind


def unit(**kw) -> Unit:
    base = dict(
        unit_id="1", book_id="bphs", edition_id="bphs-gcsharma-vol1",
        chapter="23", verse_ref="13", translation="A verse about wealth.",
    )
    base.update(kw)
    return Unit(**base)


def extracted(atoms, effects=None, **kw) -> dict:
    doc = {
        "expressible": True,
        "formation": {"atoms": atoms},
        "effects": effects if effects is not None else [
            {"life_domain": "wealth", "polarity": "positive",
             "strength": "strong", "statement": "the native is wealthy"},
        ],
    }
    doc.update(kw)
    return doc


# ==========================================================================


class TestCorpusLoader:
    def test_every_book_file_has_a_citation_identity(self):
        """Derived from the filename would mean a rename silently rewrites
        thousands of citations."""
        for path in corpus_files():
            assert path.stem in BOOKS
            book_id, edition_id = BOOKS[path.stem]
            assert book_id and edition_id

    def test_the_corpus_loads(self):
        units = load_corpus()
        assert len(units) > 2500

    def test_the_survey_reports_rather_than_hides(self):
        """A book dropping from 950 units to 12 is a bridge regression, and a
        loader that quietly skips invalid rows makes it invisible."""
        report = survey(load_corpus())
        assert report.units == report.citable + sum(report.uncitable_by_book.values())
        assert report.invalid > 0, "the corpus does contain bridge-flagged units"

    def test_the_leading_verse_number_is_stripped(self):
        """It is already in the locator, and leaving it in means every
        quote-fidelity check has to know about it."""
        assert clean_translation("40-41: If the sun is in the Ascendant") == (
            "If the sun is in the Ascendant"
        )

    def test_a_unit_with_no_locator_is_not_citable(self):
        assert not unit(chapter="", verse_ref="").citable
        assert not unit(translation="  ").citable

    def test_passages_carry_preceding_context(self):
        """"if he is also aspected by a benefic" has no referent alone, and an
        extractor given the line by itself will invent one."""
        units = [unit(verse_ref="1", translation="First."),
                 unit(verse_ref="2", translation="Second.")]
        passages = list(to_passages(units))
        assert passages[0].context == ""
        assert passages[1].context == "First."

    def test_context_stops_at_the_chapter_boundary(self):
        """The last verse of ch12 is not context for the first of ch13 - it is a
        different topic, and offering it invites a carried-over condition."""
        units = [unit(chapter="12", verse_ref="9", translation="End of twelve."),
                 unit(chapter="13", verse_ref="1", translation="Start of thirteen.")]
        assert list(to_passages(units))[1].context == ""

    def test_uncitable_units_never_become_passages(self):
        units = [unit(chapter="", verse_ref="")]
        assert list(to_passages(units)) == []

    def test_numerology_has_no_school(self):
        """It is a modality, not a Jyotisha school. Mapping it to a default
        would put numerology rules in the Parashari namespace."""
        assert "cheiro-numbers" not in SCHOOL_BY_BOOK
        assert "divine-triangle" not in SCHOOL_BY_BOOK


class TestAtomMapping:
    def test_planet_in_house(self):
        assert map_atom({"type": "planet_in_house", "planet": "mars", "house": 4}) == {
            "occupies_bhava": {"subject": "graha.mars", "bhava": "bhava.04"}
        }

    def test_a_lord_resolves_to_a_lord_reference(self):
        assert map_atom({"type": "lord_of_house_in_house", "lord_of": 10, "house": 11}) == {
            "occupies_bhava": {"subject": "lord.bhava.10", "bhava": "bhava.11"}
        }

    def test_a_house_list_on_a_lord_is_a_disjunction(self):
        """The verse enumerating alternatives: "the 10th lord in the 10th, 11th,
        4th or 5th"."""
        node = map_atom({"type": "lord_of_house_in_house", "lord_of": 10,
                         "houses": [10, 11]})
        assert set(node) == {"any"}
        assert len(node["any"]) == 2

    def test_a_house_list_on_emptiness_is_a_conjunction(self):
        """"the kendras are empty" means every one of them. The opposite of the
        case above, which is why they are separate mappers."""
        node = map_atom({"type": "house_is_empty", "houses": [1, 4, 7, 10]})
        assert set(node) == {"all"}
        assert len(node["all"]) == 4

    def test_aspected_by_puts_the_aspecting_graha_in_the_subject(self):
        """`aspects(subject, target)` - the old atom names them the other way
        round, and getting it backwards makes every aspect rule about the wrong
        planet."""
        assert map_atom({"type": "aspected_by", "target": "jupiter",
                         "planet": "saturn"}) == {
            "aspects": {"subject": "graha.jupiter", "target": "graha.saturn"}
        }

    def test_an_empty_house_becomes_an_occupant_count(self):
        assert map_atom({"type": "house_is_empty", "house": 8}) == {
            "occupant_count": {"bhava": "bhava.08", "op": "eq", "n": 0}
        }


class TestRefusals:
    """Every one of these appears in the real corpus."""

    def test_an_unknown_atom_type_is_refused(self):
        with pytest.raises(Unmappable, match="no mapping"):
            map_atom({"type": "shadbala_above", "planet": "sun"})

    def test_a_numeric_sign_is_refused(self):
        """`{"sign": "2"}` resolves to bhava.02, which would type-check as a
        house and silently mean something else."""
        with pytest.raises(Unmappable, match="not a rashi"):
            map_atom({"type": "planet_in_sign", "planet": "rahu", "sign": "2"})

    def test_a_nakshatra_pada_is_refused_rather_than_dropped(self):
        """The registry has no pada. Dropping it fires the rule on all four
        quarters when the verse names one - a fourfold widening, invisible."""
        with pytest.raises(Unmappable, match="pada"):
            map_atom({"type": "planet_in_nakshatra", "planet": "moon",
                      "nakshatra": "ashwini", "pada": 1})

    def test_an_aspect_with_no_subject_is_refused(self):
        """"aspected by Jupiter" with the referent only in the prose. Guessing
        it is how a rule ends up about the wrong planet."""
        with pytest.raises(Unmappable, match="anaphora"):
            map_atom({"type": "aspected_by", "target": "jupiter"})

    def test_a_placement_with_no_house_is_refused(self):
        with pytest.raises(Unmappable, match="house"):
            map_atom({"type": "planet_in_house", "planet": "mars"})

    def test_an_empty_formation_is_refused(self):
        """A rule with no conditions fires on every chart ever cast."""
        with pytest.raises(Unmappable, match="every chart"):
            map_formation({"atoms": []})

    def test_one_unmappable_atom_kills_the_whole_rule(self):
        """The rule this module exists to enforce. Keeping the mappable half
        widens the rule to charts the verse never described, and nothing
        downstream can detect it."""
        result = convert_unit(unit(extracted=extracted([
            {"type": "planet_in_house", "planet": "mars", "house": 4},
            {"type": "shadbala_above", "planet": "sun"},
        ])))
        assert result.docs == []
        assert any("no mapping" in s for s in result.skipped)


class TestClaims:
    def test_every_mapped_claim_is_in_the_registry(self):
        """A typo here produces hundreds of closure failures that name the rule
        rather than the mapping that caused it."""
        known = seed_registry().symbols(RegistryKind.CLAIM)
        for domain, (claim, _) in CLAIM_MAP.items():
            assert claim in known, f"{domain} -> {claim}"

    def test_family_is_deliberately_unmapped(self):
        """The registry distinguishes father, mother and siblings; the old tag
        says only "family". Picking one attributes a verse about a mother to a
        father."""
        assert "family" not in CLAIM_MAP

    def test_an_unmapped_life_domain_drops_the_effect_not_the_rule(self):
        result = convert_unit(unit(extracted=extracted(
            [{"type": "planet_in_house", "planet": "mars", "house": 4}],
            effects=[
                {"life_domain": "wealth", "polarity": "positive", "strength": "strong"},
                {"life_domain": "family", "polarity": "positive", "strength": "strong"},
            ],
        )))
        assert len(result.docs) == 1
        assert any("family" in s for s in result.skipped)

    def test_a_general_claim_carries_no_domain_tag(self):
        """It says something true about a life without saying which part. The
        index treats an untagged rule as reachable from every domain filter."""
        result = convert_unit(unit(extracted=extracted(
            [{"type": "planet_in_house", "planet": "mars", "house": 4}],
            effects=[{"life_domain": "general", "polarity": "positive",
                      "strength": "moderate"}],
        )))
        assert "domains" not in result.docs[0]

    def test_polarity_is_carried_not_reinterpreted(self):
        """Polarity is a stance toward the claim, not a verdict on the outcome.
        Flipping it here would silently invert the evidence."""
        result = convert_unit(unit(extracted=extracted(
            [{"type": "planet_in_house", "planet": "mars", "house": 4}],
            effects=[{"life_domain": "wealth", "polarity": "negative",
                      "strength": "strong"}],
        )))
        assert result.docs[0]["indicates"]["polarity"] == "negative"


class TestDocuments:
    def test_nothing_is_ever_emitted_as_production(self):
        """Machine output nobody has read. `candidate` is the honest status and
        the serving default excludes it."""
        report = convert_corpus(load_corpus(legacy=True))
        assert {d["status"] for d in report.docs} == {"candidate"}

    def test_every_document_carries_its_verse_and_a_hash(self):
        report = convert_corpus(load_corpus(legacy=True))
        for doc in report.docs:
            assert doc["source"]["quote"].strip()
            assert doc["source"]["locator"].strip()
            assert doc["source"]["quote_sha256"]

    def test_rule_ids_are_stable_across_runs(self):
        """Derived from the citation, not a counter, so a re-run diffs cleanly."""
        a = rule_id_for(unit(), "wealth.accumulation", 1)
        b = rule_id_for(unit(), "wealth.accumulation", 1)
        assert a == b == "BPHS.WEALTH.CH23V13.0001"

    def test_rule_ids_are_unique_across_the_corpus(self):
        """A duplicate id compiles twice, indexes twice and fires twice - which
        reads as two independent sources agreeing."""
        report = convert_corpus(load_corpus(legacy=True))
        ids = [d["id"] for d in report.docs]
        assert len(ids) == len(set(ids))

    def test_converted_domain_weight_sits_below_reviewed_material(self):
        """Above the incidental-tag threshold, below a reviewer's judgement."""
        assert 0.5 <= DOMAIN_WEIGHT < 0.9

    def test_a_timing_verse_requires_activation(self):
        """A promise is not an event."""
        result = convert_unit(unit(extracted=extracted(
            [{"type": "planet_in_house", "planet": "mars", "house": 4}],
            rule_category="timing",
        )))
        assert result.docs[0]["timing"]["requires_activation"] is True

    def test_an_inexpressible_unit_is_skipped_with_a_reason(self):
        result = convert_unit(unit(extracted={"expressible": False}))
        assert result.docs == []
        assert result.skipped

    def test_no_claim_ids_outside_the_registry(self):
        report = convert_corpus(load_corpus(legacy=True))
        assert unknown_claims(report.docs, seed_registry()) == set()


class TestReport:
    def test_the_census_names_what_could_not_be_expressed(self):
        """A converter that reports only its successes tells you it worked. One
        that reports the atom shapes and domain tags it could not express tells
        you what to build next."""
        report = convert_corpus(load_corpus(legacy=True))
        assert report.reasons
        assert report.unmapped_domains
        assert "family" in report.unmapped_domains

    def test_the_report_renders(self):
        assert "rule documents" in str(convert_corpus(load_corpus(legacy=True)[:200]))


@pytest.fixture(scope="module")
def gated():
    """The whole corpus through the compiler once, shared by the tests below."""
    from rishivan.koonji.pipeline import gate

    report = convert_corpus(load_corpus(legacy=True))
    rules, gate_report, _ = gate(report.docs, seed_registry())
    return rules, gate_report


class TestEndToEnd:
    """The corpus, converted, compiled, and fired on a real chart."""

    def test_almost_everything_compiles(self, gated):
        rules, report = gated
        assert len(rules) > 1000
        assert len(rules) / report.submitted > 0.99

    def test_what_does_not_compile_is_named(self, gated):
        """The compiler is the arbiter. A converter that dropped rules on its
        own reasoning would grow a second, undocumented copy of it."""
        _, report = gated
        for rule_id, why in report.dropped.items():
            assert rule_id
            assert "ERROR" in why

    def test_every_written_rule_round_trips(self, gated):
        """Nothing reaches disk that cannot be read back."""
        _, report = gated
        assert report.round_trip_failures == {}

    def test_the_converted_corpus_fires_on_a_chart_with_citations(self, gated):
        from datetime import datetime

        from rishivan.chart.ephemeris import BirthData, compute_chart
        from rishivan.koonji.bundle import Bundle
        from rishivan.koonji.engine import Engine

        rules, _ = gated
        registry = seed_registry()
        engine = Engine(Bundle.build(rules, registry))
        chart = compute_chart(BirthData(
            year=1990, month=1, day=1, hour=12, minute=0,
            tz_offset_hours=5.5, lat=28.6139, lon=77.2090,
        ))
        reading = engine.read(
            chart, when=datetime(2026, 8, 25),
            statuses=frozenset({"production", "candidate"}),
        )
        fired = [f for f in reading.firings if f.counts]
        assert fired, "a thousand rules and none fired - retrieval is broken"
        assert reading.claims
        for claim in reading.claims:
            for support in claim.support:
                assert support.citation.strip()

    def test_the_seed_corpus_is_not_served_by_default(self, gated):
        """Everything converted is `candidate`. A caller that does not ask for
        candidates gets nothing from this corpus, which is the point."""
        rules, _ = gated
        assert all(r.status == "candidate" for r in rules)
