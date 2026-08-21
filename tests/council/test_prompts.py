"""What the primary Rishi is allowed to see, and in what order.

Blueprint §8 rule 4 is a hierarchy of evidence. It cannot hold when a flat fact dump sits
beside cited rules with equal visibility, or when an S3 source and an S0 source look
identical.
"""

from rishivan.council.contributors import ContributorReport
from rishivan.council.prompts import contributor_context, coverage_facts, rule_context
from rishivan.rag.rules import RuleHit

FACTS = [
    "Ascendant (Lagna) is Cancer.",
    "The 1st house (self, body, personality) is ruled by Moon, placed in the 8th house.",
    "The 10th house (career, status, public life) is ruled by Mars, placed in the 5th house.",
]


def test_facts_inside_coverage_come_before_the_wider_chart():
    text = coverage_facts(FACTS, "atma")
    assert text.index("WITHIN YOUR COVERAGE") < text.index("WIDER CONTEXT")


def test_a_fact_about_an_owned_house_lands_inside_coverage():
    """ATMA owns house 1 alone."""
    inside = coverage_facts(FACTS, "atma").split("WIDER CONTEXT")[0]
    assert "1st house" in inside
    assert "10th house" not in inside


def test_a_planet_the_constitution_owns_lands_inside_coverage():
    """ATMA owns the Sun and Moon outright (§4). A house-only reading of coverage
    filed "Sun is in ..." under the wider chart -- demoting the single most important
    fact for a personality question."""
    facts = [*FACTS, "Sun is in Sagittarius in the 6th house (Purva Ashadha, pada 2)."]
    inside = coverage_facts(facts, "atma").split("WIDER CONTEXT")[0]
    assert "Sun is in Sagittarius" in inside


def test_a_planet_fact_is_not_filed_by_where_the_planet_sits():
    """The 6th is the Sun's location, not the fact's subject.

    KARMA owns house 6 and no planet at all, so a fact filed by the trailing house
    number would be claimed by KARMA -- a career reading leading on the Sun because it
    happens to sit in the 6th. AAROGYA is the wrong domain to test this with: it owns
    the Sun outright as the vitality karaka, so the fact is legitimately its own.
    """
    facts = ["Sun is in Sagittarius in the 6th house (Purva Ashadha, pada 2)."]
    inside = coverage_facts(facts, "karma").split("WIDER CONTEXT")[0]
    assert "Sun is in Sagittarius" not in inside


def test_the_chart_framework_is_always_inside_coverage():
    """Step 1 of every §4-11 protocol is "chart framework"."""
    for domain in ("atma", "artha", "prema"):
        inside = coverage_facts(FACTS, domain).split("WIDER CONTEXT")[0]
        assert "Ascendant (Lagna) is Cancer." in inside, domain


def test_no_fact_is_dropped():
    """Every §4-11 protocol ends in whole-chart synthesis, so demote -- never delete."""
    text = coverage_facts(FACTS, "atma")
    for fact in FACTS:
        assert fact in text


def test_an_unrouted_question_gets_the_facts_unsplit():
    text = coverage_facts(FACTS, None)
    assert "WIDER CONTEXT" not in text
    for fact in FACTS:
        assert fact in text


def test_a_contributor_block_names_the_rishi_and_its_values():
    report = ContributorReport(
        rishi="ritam",
        computed={"Mahadasha": "Saturn until 2044-09-21"},
        rules=(),
        note="3 timing rules true of this chart",
    )
    text = contributor_context((report,))
    assert "RITAM" in text
    assert "Saturn until 2044-09-21" in text
    assert "3 timing rules" in text


def test_no_contributors_renders_nothing():
    assert contributor_context(()) == ""


def test_a_rule_carries_its_tier_and_school():
    """The billionaire reading named an S3 source a 'classic text' while S0 BPHS sat
    unnamed beside it. Blueprint §8 rule 5 also forbids mixing schools silently."""
    hit = RuleHit(
        rule_key="r", condition={}, effects=[{"polarity": "positive", "statement": "x"}],
        source={"chapter": "1", "verse_ref": "1", "translation": "t"},
        relevance=1.0, tier="S3", school="prashna",
    )
    text = rule_context([hit])
    assert "S3" in text
    assert "prashna" in text


# ── Activation labelling (Blueprint §8 rule 2) ────────────────────────────────


class _Hit:
    """A rule as `rule_context` sees it."""

    def __init__(self, active=None, citation="BPHS 7.1"):
        self.active = active
        self.citation = citation
        self.tier = "S0"
        self.school = "parashari"
        self.source = {"translation": "the 7th lord in the 7th gives a happy marriage"}
        self.effects = [{"polarity": "favourable", "statement": "a happy marriage"}]


def test_a_running_rule_is_labelled_as_running():
    from rishivan.council.prompts import rule_context

    rendered = rule_context([_Hit(active=True)])
    assert "RUNNING NOW" in rendered


def test_a_dormant_rule_is_labelled_as_not_running():
    """The defect this closes: a rule whose activation period is years away read
    identically to one running today, so the model could only imply timing it had no
    basis for."""
    from rishivan.council.prompts import rule_context

    rendered = rule_context([_Hit(active=False)])
    assert "NOT RUNNING" in rendered


def test_a_rule_with_no_recorded_timing_is_not_labelled_either_way():
    """A pure natal promise. Labelling it "not running" would assert something the
    corpus never recorded."""
    from rishivan.council.prompts import rule_context

    rendered = rule_context([_Hit(active=None)])
    # The guidance explains the labels, so match the per-rule marker rather than the
    # word.
    assert "TIMING:" not in rendered


def test_the_guidance_tells_the_model_what_the_label_means():
    """A label the prompt does not explain is a label the model will interpret for
    itself, which is how "not running" becomes "will not happen"."""
    from rishivan.council.prompts import RULE_GUIDANCE

    assert "RUNNING NOW" in RULE_GUIDANCE
    assert "promise" in RULE_GUIDANCE.lower()


# ── Plain speech (readability without losing facts) ───────────────────────────


def test_the_voice_is_told_to_simplify_words_and_not_content():
    """The readability instruction has to be explicit about the boundary. "Write more
    simply" alone invites the model to drop the placement, the period or the nakshatra
    to make a shorter sentence -- which would quietly undo the grounding the whole
    engine exists to provide."""
    from rishivan.council.prompts import _CORE_RULES

    assert "PLAIN SPEECH" in _CORE_RULES
    assert "never the content" in _CORE_RULES.lower()


def test_the_voice_is_told_to_gloss_a_technical_term_on_first_use():
    """A reading may say "Venus antardasha" -- the client's own documents use the
    vocabulary and dropping it would cost credibility. What it may not do is leave a
    seeker who has never heard the word unable to follow the sentence."""
    from rishivan.council.prompts import _CORE_RULES

    assert "antardasha" in _CORE_RULES.lower()
    assert "first time" in _CORE_RULES.lower()


def test_the_plain_speech_example_does_not_break_the_banned_openings():
    """Rule 6(a) bans "You are in a period where...". A worked example that opened
    that way would teach the model to do exactly what another rule forbids -- and the
    model follows examples more readily than prohibitions."""
    from rishivan.council.prompts import _CORE_RULES

    banned = ("You are in a period", "You are in a season", "You have entered",
              "You are standing at", "You find yourself")
    plain = _CORE_RULES[_CORE_RULES.index("PLAIN SPEECH"):]
    example = plain[:plain.index("\n3.")] if "\n3." in plain else plain
    for phrase in banned:
        assert phrase not in example, phrase
