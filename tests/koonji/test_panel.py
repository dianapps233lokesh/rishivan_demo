"""The rules panel, and the safety gate that travels with it.

`hits_from_reading` replaced `rag.rules.rank_true_rules` when the panel moved
onto the Koonji engine. The ranker did two things besides ranking, and only the
ranking was carried across:

    if withhold_reasons(hit, question):   # Eight Rishis §9 - drop it entirely
        continue
    hit.sensitivities = sensitivities(hit)   # flag what survives, for the UI

Neither reached the replacement, and `question` was dropped from the call site
along with the comment explaining why it was there. The visible symptom was
`AttributeError: 'KoonjiHit' object has no attribute 'sensitivities'` in the
Streamlit app; the invisible one was that a rule naming the manner of the
querent's death was free to appear under a question about their love life.
"""

import types

import pytest

from rishivan.koonji.compiler import compile_rules
from rishivan.koonji.panel import KoonjiHit, hits_from_reading
from rishivan.koonji.registry import seed_registry
from rishivan.koonji.vm import Firing, Outcome


@pytest.fixture(scope="module")
def registry():
    return seed_registry()


def _doc(rule_id: str, *, quote: str, claim: str = "relationship.harmony") -> dict:
    return {
        "id": rule_id,
        "status": "candidate",
        "school": "school.parashari",
        "assertion": "assert_claim",
        "domains": {"domain.relationship": 0.9},
        "source": {"book": "bphs", "edition": "bphs-gcsharma-vol1",
                   "locator": "ch1.v1", "quote": quote},
        "when": {"occupies_bhava": {"subject": "graha.moon", "bhava": 7}},
        "indicates": {"claim": claim, "polarity": "positive",
                      "magnitude": "strong", "text": quote},
    }


def _reading_for(registry, docs):
    """A fake reading in which every supplied rule fired."""
    result = compile_rules(docs, registry)
    assert result.rules, [str(d) for d in result.diagnostics]
    engine = types.SimpleNamespace(
        bundle=types.SimpleNamespace(rules=result.rules)
    )
    reading = types.SimpleNamespace(firings=[
        Firing(rule_id=r.rule_id, version=r.version, outcome=Outcome.FIRED,
               strength=1.0)
        for r in result.rules
    ])
    return reading, engine


DEATH = "the native's death is certain in the maraka period"
BENIGN = "the native enjoys harmony with the spouse"


class TestTheSafetyGateSurvivedTheMove:
    """Eight Rishis §9. The rule has not changed; the appropriateness has."""

    def test_a_death_rule_is_withheld_from_a_question_that_did_not_ask(
        self, registry
    ):
        reading, engine = _reading_for(registry, [_doc("D", quote=DEATH)])
        hits = hits_from_reading(
            reading, engine=engine, question="Tell me about my love life."
        )
        assert [h.rule_key for h in hits] == []

    def test_the_same_rule_is_shown_when_the_question_asks_for_it(self, registry):
        """A querent who wants that answer can ask for it directly."""
        reading, engine = _reading_for(registry, [_doc("D", quote=DEATH)])
        hits = hits_from_reading(
            reading, engine=engine, question="How long will I live?"
        )
        assert [h.rule_key for h in hits] == ["D"]
        assert hits[0].sensitivities == {"death"}

    def test_an_unremarkable_rule_carries_no_sensitivity(self, registry):
        reading, engine = _reading_for(registry, [_doc("H", quote=BENIGN)])
        hits = hits_from_reading(
            reading, engine=engine, question="Tell me about my love life."
        )
        assert [h.rule_key for h in hits] == ["H"]
        assert hits[0].sensitivities == set()

    def test_withholding_is_off_when_no_question_is_supplied(self, registry):
        """`question=""` must not silently withhold everything. Callers that do
        not have the question - tests, tooling - should see the whole reading
        rather than a filtered one they did not ask for."""
        reading, engine = _reading_for(registry, [_doc("D", quote=DEATH)])
        assert [h.rule_key for h in hits_from_reading(reading, engine=engine)] == ["D"]


class TestTheHitCarriesWhatItsConsumersRead:
    """The parity check that would have caught this before it reached a user.

    `KoonjiHit` was written to stand in for `rag.rules.RuleHit` without anyone
    comparing the two attribute by attribute. `remedies` was found by a test,
    `sensitivities` was not, and the app raised on the first question that
    reached the caption that reads it.
    """

    def test_every_attribute_the_app_reads_off_a_hit_exists(self):
        import pathlib
        import re

        source = pathlib.Path("streamlit_app.py").read_text(encoding="utf-8")
        used = set(re.findall(r"\bhit\.([a-z_]+)", source))
        assert used, "the scrape found nothing - the panel loop was renamed"

        missing = sorted(a for a in used if not hasattr(KoonjiHit, a))
        assert not missing, (
            f"the app reads {missing} off a hit and KoonjiHit does not define "
            f"it; add the field rather than removing the caption"
        )
