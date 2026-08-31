"""The requirement table: what it contains, where it comes from, and what it
refuses to do."""

import pytest

from rishivan.council.requirements import store
from rishivan.council.requirements.catalog import (
    FLOOR, KINDS, catalogue, invalid_keys, requirement_set,
)
from rishivan.council.requirements.producers import known, label
from rishivan.council.requirements.types import BANDS, Requirement, Source


@pytest.fixture(autouse=True)
def clean_cache():
    store.reset()
    yield
    store.reset()


class TestTheCatalogue:
    def test_every_domain_and_kind_has_a_row(self):
        from rishivan.council.hierarchy import LIFE_DOMAIN_OF

        entries = catalogue()
        for domain in LIFE_DOMAIN_OF:
            for kind in KINDS:
                assert f"{domain}:{kind}" in entries

    def test_the_unroutable_question_has_a_row_too(self):
        """`constitution_for("")` falls back to atma, whose protocol is the
        whole-chart reading order. A question nobody could place gets that,
        rather than nothing."""
        for kind in KINDS:
            assert f":{kind}" in catalogue()

    def test_the_kinds_match_the_classifier(self):
        """A kind added to `QuestionKind` without a row here is a question type
        that silently falls back."""
        from rishivan.council.question_profile import QuestionKind

        assert set(KINDS) == {k.value for k in QuestionKind}

    def test_every_token_key_is_valid_under_the_vocabulary(self):
        """A misspelled token is a requirement nobody can satisfy and nobody
        notices. This is the only place that is cheap to catch."""
        assert invalid_keys() == ()

    def test_every_key_has_a_producer_or_is_a_declared_gap(self):
        """Not an assertion that everything is computable — a key with no
        producer is how a protocol step declares itself unavailable. It IS an
        assertion that we know which those are."""
        unproduced = sorted({
            r.key for e in catalogue().values() for r in e.requires
            if not known(r.key)
        })
        assert unproduced == [], (
            f"these keys silently produce nothing: {unproduced}"
        )

    def test_the_floor_is_in_every_row(self):
        for entry in catalogue().values():
            keys = {r.key for r in entry.requires}
            for requirement in FLOOR:
                assert requirement.key in keys, entry.doc_id

    def test_no_key_appears_twice_in_a_row(self):
        """The floor, the kind and the domain can all name the same fact.
        `_dedupe` keeps the strongest claim; two entries would render the block
        twice and read as corroboration."""
        for entry in catalogue().values():
            keys = [r.key for r in entry.requires]
            assert len(keys) == len(set(keys)), entry.doc_id

    def test_dedupe_keeps_the_strongest_claim(self):
        from rishivan.council.requirements.catalog import _dedupe

        merged = _dedupe((
            Requirement("house.7.lord.house", step=8, mandatory=False, priority=3),
            Requirement("house.7.lord.house", step=1, mandatory=True, priority=1),
        ))
        assert len(merged) == 1
        assert merged[0].mandatory
        assert merged[0].priority == 1
        assert merged[0].step == 1

    def test_the_constitution_is_not_restated(self):
        """Marriage rests on the 7th because `prema.primary_houses` says so, not
        because anybody typed it here. A second copy is a second thing to
        drift."""
        from rishivan.council.constitution import CONSTITUTIONS

        entry = requirement_set("domain.relationship", "when_will")
        keys = {r.key for r in entry.requires}
        for house in CONSTITUTIONS["prema"].primary_houses:
            assert f"block.house.{house}" in keys


class TestBands:
    def test_every_requirement_lands_in_a_known_band(self):
        for entry in catalogue().values():
            for requirement in entry.requires:
                assert requirement.priority in BANDS, requirement.key

    def test_a_band_is_sorted_by_protocol_step(self):
        """So band 1 of a marriage question walks promise -> spouse indicators ->
        affliction, which is how the protocol reads it."""
        entry = requirement_set("domain.relationship", "when_will")
        for group in entry.by_band().values():
            steps = [r.step for r in group]
            assert steps == sorted(steps)


class TestTheStore:
    def test_an_unreachable_cluster_falls_back_and_says_so(self, monkeypatch):
        monkeypatch.setattr(
            "rishivan.council.requirements.store._from_mongo", lambda: None
        )
        loaded, source = store.load(refresh=True)
        assert source is Source.BUILTIN
        assert loaded  # fully specified, not empty

    def test_an_empty_collection_is_data_and_still_falls_back(self, monkeypatch):
        """Different cause, same outcome, and both are reported. An operator who
        emptied the collection deliberately gets a warning, not silence."""
        monkeypatch.setattr(
            "rishivan.council.requirements.store._from_mongo", lambda: {}
        )
        _loaded, source = store.load(refresh=True)
        assert source is Source.BUILTIN

    def test_documents_from_mongo_win_and_are_labelled(self, monkeypatch):
        entry = requirement_set("domain.relationship", "when_will")
        monkeypatch.setattr(
            "rishivan.council.requirements.store._from_mongo",
            lambda: {entry.doc_id: entry},
        )
        result = store.requirements_for("domain.relationship", "when_will")
        assert result.source is Source.MONGO

    def test_a_malformed_document_is_dropped_not_fatal(self):
        """One bad row hand-edited in Atlas must not take out the other
        fifty-one."""
        assert store._document({"requires": [{"no_key": 1}]}).requires == ()

    def test_an_unknown_domain_falls_back_to_the_whole_chart_row(self, monkeypatch):
        monkeypatch.setattr(
            "rishivan.council.requirements.store._from_mongo", lambda: None
        )
        result = store.requirements_for("domain.nonexistent", "when_will")
        assert result.requires

    def test_the_seed_payload_round_trips(self):
        """What the seed script writes must be what the loader can read back."""
        documents = store.as_documents()
        rebuilt = store._document(documents[0])
        assert rebuilt is not None
        assert len(rebuilt.requires) == len(documents[0]["requires"])


class TestLabels:
    def test_a_withheld_varga_is_named_in_plain_words(self):
        """These are the keys a reader is most likely to be told about, because
        §7 withholds a division whenever the birth time cannot carry its arc."""
        assert "D9" in label("block.varga.d9")
        assert "D9" in label("block.varga_confirms.d9")

    def test_the_jaimini_gaps_read_as_english(self):
        assert "Darakaraka" in label("karaka.dara")
        assert "Upapada" in label("from_arudha_lagna.house.12")

    def test_an_unmapped_key_falls_back_to_itself(self):
        assert label("house.7.lord.house") == "house.7.lord.house"
