"""The extraction prompt's two hard limits, and the validator that backs it up.

Both limits were found by hitting them, and both fail *silently* in production -- one
as a tripled bill, one as a bare `400 INVALID_ARGUMENT` naming nothing. So they are
pinned here.
"""

import json

import pytest

from app.astro.vocab import CONDITION_TOKEN_TEMPLATES, EMITTED_SCOPES
from app.knowledge.extract.prompt import (
    CACHE_FLOOR_TOKENS,
    CONDITION_ARGUMENTS,
    INSTRUCTIONS,
    RESPONSE_SCHEMA,
    SCHEMA_LEAF_BUDGET,
    cached_contents,
    fact_vocabulary,
    invariant_prefix,
    verse_block,
)
from app.knowledge.extract.validate import validate_atom, validate_rule

CHARS_PER_TOKEN = 3.26
"""Measured on this corpus's Devanagari + English mix by sampling the whole size
distribution against the live tokenizer."""


def _leaf_fields(node) -> int:
    if isinstance(node, dict):
        if "properties" in node:
            return sum(_leaf_fields(v) for v in node["properties"].values())
        if "items" in node:
            return _leaf_fields(node["items"])
    return 1


def test_schema_stays_within_the_measured_leaf_budget():
    """156 leaf fields succeeded, 180 failed with an error naming nothing. Exceeding
    this breaks every extraction call at once."""
    assert _leaf_fields(RESPONSE_SCHEMA) < SCHEMA_LEAF_BUDGET


def test_cached_payload_clears_the_cache_floor():
    """Below the floor, caching silently does not apply -- no error, just a bigger
    bill. The floor was measured, not read: 4,091 tokens rejected, 4,195 accepted.

    The payload is instructions + vocabulary + examples + the schema carried as a tool
    declaration. An intermediate draft compacted the vocabulary so hard that the
    prefix fell to 2,691 tokens -- 1,405 under -- which this test caught.
    """
    payload = INSTRUCTIONS + cached_contents() + json.dumps(RESPONSE_SCHEMA)
    assert len(payload) / CHARS_PER_TOKEN > CACHE_FLOOR_TOKENS


def test_cached_contents_are_byte_identical_across_calls():
    """The whole caching saving depends on this. Any timestamp, set iteration or
    unsorted dict here would silently disable it."""
    assert cached_contents() == cached_contents()
    assert invariant_prefix() == invariant_prefix()


def test_schema_is_not_duplicated_into_the_prefix():
    """The schema travels as a cached tool declaration. Restating it in the prefix
    billed it twice -- 4,569 tokens per call at the full rate, because config is not
    content and cannot be cached."""
    prefix = invariant_prefix()
    # The examples legitimately mention field names as prose; what must be absent is
    # the serialised schema itself.
    assert '"type": "object"' not in prefix
    assert '"properties"' not in prefix


def test_condition_arguments_match_the_vocabulary_lock():
    """vocab.py warns that a second copy is a second thing to drift, "and drift here
    means every affected rule silently matches nothing"."""
    assert set(CONDITION_ARGUMENTS) == set(CONDITION_TOKEN_TEMPLATES)


def test_vocabulary_names_planets_by_token_name():
    """`planet.Sa.house` looks reasonable and matches nothing, ever, so the prompt must
    state the token names explicitly even though the tokens themselves are given as
    templates rather than an enumerated cross-product."""
    vocab = fact_vocabulary()
    assert "saturn" in vocab and "jupiter" in vocab
    assert "planet.{planet}.house" in vocab
    assert "NOT the two-letter codes" in vocab


def test_vocabulary_names_what_is_not_expressible():
    """Degrade, never drop: the model must be able to say "I can't express this"."""
    vocab = fact_vocabulary()
    assert "strength_cmp" in vocab
    for unemitted in ("d4.", "from_arudha_lagna."):
        assert unemitted in vocab


def test_vocabulary_lists_required_arguments_per_type():
    """Without this the model omits `house` and invents `level`."""
    vocab = fact_vocabulary()
    assert "REQUIRED ARGUMENTS PER CONDITION TYPE" in vocab
    assert "lord_of_house_in_house   lord_of, house" in vocab


def test_verse_block_is_separate_from_the_prefix():
    """Per-verse text must never enter the cached prefix."""
    block = verse_block(
        chapter="26", verse_ref="85", verse_devanagari="x",
        translation="unique-marker-translation",
    )
    assert "unique-marker-translation" in block
    assert "unique-marker-translation" not in invariant_prefix()


def test_schema_is_valid_json():
    json.dumps(RESPONSE_SCHEMA)


# --- the validator: what the schema cannot enforce -------------------------------

def test_validator_catches_the_real_leaked_atom():
    """Verbatim from a live BPHS 26.85 call: schema-valid, and useless."""
    problems = validate_atom(
        {"type": "lord_of_house_in_house", "lord_of": 8, "level": "maha", "scope": ""}
    )
    reasons = " ".join(p.reason for p in problems)
    assert "'level' does not belong" in reasons
    assert "'house' is missing" in reasons


def test_validator_rejects_book_style_planet_codes():
    problems = validate_atom({"type": "planet_in_house", "planet": "Sa", "house": 7})
    assert any("not a token name" in p.reason for p in problems)


def test_validator_rejects_unemitted_scope():
    problems = validate_atom(
        {"type": "planet_in_house", "planet": "saturn", "house": 4, "scope": "d4."}
    )
    assert any("not emitted" in p.reason for p in problems)


@pytest.mark.parametrize("house", [0, 13, 99])
def test_validator_rejects_impossible_house(house):
    problems = validate_atom(
        {"type": "planet_in_house", "planet": "saturn", "house": house}
    )
    assert any("must be 1-12" in p.reason for p in problems)


def test_valid_atom_passes():
    assert validate_atom(
        {"type": "planet_in_house", "planet": "saturn", "house": 7, "scope": "d9."}
    ) == []


def test_timing_atom_is_moved_out_of_formation():
    """"Timing cannot manufacture a natal promise" becomes structural here, not
    advisory. The atom is moved rather than rejected: it is real information in the
    wrong slot."""
    rule = {
        "formation": {
            "atoms": [
                {"type": "planet_in_house", "planet": "saturn", "house": 7},
                {"type": "dasha_of", "planet": "jupiter", "level": "maha"},
            ]
        },
        "effects": [{"polarity": "negative", "strength": "strong", "statement": "d"}],
    }
    result = validate_rule(rule)
    assert result.timing_atoms_moved == 1
    assert [a["type"] for a in rule["formation"]["atoms"]] == ["planet_in_house"]
    assert rule["timing"]["activation_factors"]["atoms"][0]["type"] == "dasha_of"
    assert result.ok


def test_timing_only_rule_is_recategorised_not_rejected():
    """BPHS's dasha-result chapters have no natal placement at all. That is a valid
    `timing` rule, not a broken `formation` one."""
    rule = {
        "formation": {
            "atoms": [{"type": "dasha_of", "planet": "saturn", "level": "antar"}]
        },
        "rule_category": "formation",
        "effects": [{"polarity": "negative", "strength": "moderate", "statement": "d"}],
    }
    validate_rule(rule)
    assert rule["formation"]["atoms"] == []
    assert rule["rule_category"] == "timing"


def test_rule_with_no_effects_is_rejected():
    result = validate_rule({"formation": {"atoms": []}, "effects": []})
    assert any("predicts nothing" in p.reason for p in result.problems)


def test_out_of_scope_must_carry_a_reason():
    """Degrade, never drop -- but an unexplained degradation is a silent drop."""
    result = validate_rule(
        {
            "formation": {"atoms": []},
            "effects": [{"polarity": "neutral", "strength": "weak", "statement": "x"}],
            "expressible": False,
        }
    )
    assert any("without out_of_scope_reason" in p.reason for p in result.problems)


def test_house_set_form_is_available_for_disjunction():
    """Eight of eighteen rules in the first sample failed for lack of this. "The 7th
    lord in the 6th, 8th or 12th" is pervasive, not an edge case."""
    atom = RESPONSE_SCHEMA["properties"]["rules"]["items"]["properties"]["formation"]
    atom = atom["properties"]["atoms"]["items"]["properties"]
    assert "houses" in atom and atom["houses"]["type"] == "array"


def test_validator_accepts_a_house_set():
    assert validate_atom(
        {"type": "lord_of_house_in_house", "lord_of": 7, "houses": [6, 8, 12]}
    ) == []


def test_validator_rejects_both_scalar_and_set_forms():
    problems = validate_atom(
        {"type": "lord_of_house_in_house", "lord_of": 7, "house": 6, "houses": [6, 8]}
    )
    assert any("not both" in p.reason for p in problems)


def test_flattened_disjunction_is_still_caught():
    """The set form is the fix; the contradiction check is the backstop. Mars in houses
    1 AND 4 matches no chart that has ever existed."""
    from app.knowledge.extract.validate import impossible_conjunctions

    problems = impossible_conjunctions(
        {
            "combinator": "all",
            "atoms": [
                {"type": "planet_in_house", "planet": "mars", "house": 1},
                {"type": "planet_in_house", "planet": "mars", "house": 4},
            ],
        }
    )
    assert any("impossible conjunction" in p.reason for p in problems)


# --- The four faults the first graded sample actually had --------------------
#
# It scored 9 valid of 31 rules (29%) and each of these is one reason why. Three were
# the model's; the largest was the harness's own scoring. Every fixture below is the
# real verse and the real output, quoted from output.json.

EFFECTS = [{"polarity": "negative", "strength": "moderate", "statement": "x"}]

MOVABLE_VERSE = (
    "If at the time of birth the Sun be in a movable sign, the lamp will be "
    "flickering, if he be in a fixed sign, it will remain fixed and, if he be in a "
    "dual sign, it should be told as sometimes stable and sometimes flickering."
)


def _rule(atoms, **extra):
    return {"formation": {"atoms": atoms, **extra}, "effects": EFFECTS}


def test_a_decline_is_not_an_invalid_rule():
    """BPHS 11.1 -- "the astrologer should consider the evils and their antidotes from
    the Ascendant first" -- is methodology, not a rule. The model said so, with a
    reason. Counting that as a failed rule is what reported 29%."""
    result = validate_rule(
        {
            "formation": {"atoms": []},
            "effects": EFFECTS,
            "expressible": False,
            "out_of_scope_reason": "introductory methodological instruction",
        }
    )
    assert result.declined
    assert result.ok, str(result)


def test_a_decline_asserts_nothing():
    """BPHS 15.2: expressible=false AND `jupiter in house 2` for "a benefic in the 2nd".
    The decline is right and the atom is a fabrication, so the atom is stripped."""
    rule = {
        "formation": {"atoms": [{"type": "planet_in_house", "planet": "jupiter", "house": 2}]},
        "effects": EFFECTS,
        "expressible": False,
        "out_of_scope_reason": "benefic/malefic as a class",
    }
    result = validate_rule(rule)
    assert result.stripped_atoms == 1
    assert rule["formation"]["atoms"] == []
    assert result.ok, str(result)


def test_a_fixed_sign_class_may_be_expanded_whole():
    """BPHS 10.8's "movable sign" is Aries, Cancer, Libra and Capricorn for every chart
    ever cast, so expanding it assumes nothing. Rejecting the expansion threw away three
    correct rules."""
    result = validate_rule(
        _rule(
            [
                {"type": "planet_in_sign", "planet": "sun", "sign": sign}
                for sign in ("aries", "cancer", "libra", "capricorn")
            ],
            combinator="any",
        ),
        source_text=MOVABLE_VERSE,
    )
    assert result.ok, str(result)


def test_a_sign_class_expanded_in_part_is_still_rejected():
    """Half a class is not the class: "movable" does not mean Aries alone."""
    result = validate_rule(
        _rule([{"type": "planet_in_sign", "planet": "sun", "sign": "aries"}]),
        source_text=MOVABLE_VERSE,
    )
    assert any("expanded whole or not at all" in p.reason for p in result.problems)


def test_exaltation_is_still_not_a_sign():
    """The check this table must not weaken. BPHS 24.2's "the 11th lord is exalted" is a
    different sign per planet, so `sign: aries` remains a fabrication."""
    result = validate_rule(
        _rule([{"type": "lord_of_house_in_sign", "lord_of": 11, "sign": "aries"}]),
        source_text="If the lord of the 11th is exalted the native enjoys many gains.",
    )
    assert any("never named in the verse" in p.reason for p in result.problems)


def test_earthen_lamp_does_not_ground_capricorn():
    """Grounding is substring matching, and BPHS 10.8 -- the verse the class table was
    built for -- opens with "the situation of the earthen lamp"."""
    result = validate_rule(
        _rule([{"type": "planet_in_sign", "planet": "sun", "sign": "capricorn"}]),
        source_text="The situation of the earthen lamp is to be told from the Sun.",
    )
    assert any("capricorn" in p.reason for p in result.problems)


def test_two_half_atoms_are_merged_into_one():
    """BPHS 18.4: "the 5th Lord being in the 6th House" arrived as `{lord_of: 5}` plus
    `{house: 6}`. Neither half is a claim; the intent is unambiguous."""
    rule = _rule(
        [
            {"type": "lord_of_house_in_house", "lord_of": 5},
            {"type": "lord_of_house_in_house", "house": 6},
        ],
        combinator="all",
    )
    result = validate_rule(rule)
    assert result.atoms_merged == 1
    assert rule["formation"]["atoms"] == [
        {"type": "lord_of_house_in_house", "lord_of": 5, "house": 6}
    ]
    assert result.ok, str(result)


def test_a_half_atom_merges_with_a_set_form():
    """BPHS 24.2: `{lord_of: 11}` plus `{houses: [1,4,7,10,5,9]}` -- "the 11th lord in
    the 11th, an angle or a trine"."""
    rule = _rule(
        [
            {"type": "lord_of_house_in_house", "lord_of": 11},
            {"type": "lord_of_house_in_house", "houses": [11, 1, 4, 7, 10, 5, 9]},
        ]
    )
    result = validate_rule(rule)
    assert result.atoms_merged == 1
    assert rule["formation"]["atoms"][0]["lord_of"] == 11
    assert result.ok, str(result)


def test_an_ambiguous_merge_is_refused():
    """Three half-atoms could pair up more than one way, and a wrong merge fabricates a
    condition -- worse than rejecting one. They stay rejected with fields missing."""
    rule = _rule(
        [
            {"type": "lord_of_house_in_house", "lord_of": 5},
            {"type": "lord_of_house_in_house", "lord_of": 9},
            {"type": "lord_of_house_in_house", "house": 6},
        ]
    )
    result = validate_rule(rule)
    assert result.atoms_merged == 0
    assert any("missing" in p.reason for p in result.problems)


def test_complete_atoms_are_never_merged():
    rule = _rule(
        [
            {"type": "lord_of_house_in_house", "lord_of": 5, "house": 6},
            {"type": "lord_of_house_in_house", "lord_of": 9, "house": 12},
        ]
    )
    assert validate_rule(rule).atoms_merged == 0
    assert len(rule["formation"]["atoms"]) == 2


def test_the_prompt_names_benefic_malefic_as_a_gap():
    """5 of 18 rule-destined verses in the graded sample substituted a planet for "a
    benefic" or "a malefic". The vocabulary block never said it was a gap."""
    vocabulary = fact_vocabulary().lower()
    assert "benefic" in vocabulary and "malefic" in vocabulary


def test_a_decline_does_not_earn_a_retry():
    from app.knowledge.extract.runner import retryable

    result = validate_rule(
        {
            "formation": {"atoms": []},
            "effects": EFFECTS,
            "expressible": False,
            "out_of_scope_reason": "benefic/malefic as a class",
        }
    )
    assert not retryable(result.problems)


def test_a_grounding_fault_tells_the_retry_to_decline():
    """15 retries fixed 0 rules because the note said only "that was rejected", so the
    model substituted a different planet and failed the same check again."""
    from app.knowledge.extract.runner import correction_note

    result = validate_rule(
        _rule([{"type": "planet_in_house", "planet": "jupiter", "house": 2}]),
        source_text="A benefic in the 2nd House is the giver of wealth.",
    )
    note = correction_note(result.problems)
    assert "expressible: false" in note
    assert "NOT substitute another planet" in note


def test_a_rate_limit_is_waited_out_not_recorded_as_a_failure():
    """3 of 20 calls in the graded sample died on `429 RESOURCE_EXHAUSTED` and the loop
    moved on. At 963 units that thins the rule base ~15% while every printed number
    still looks healthy."""
    from app.knowledge.extract.runner import call_with_backoff

    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("429 RESOURCE_EXHAUSTED. quota exceeded")
        return "ok"

    import app.knowledge.extract.runner as runner

    original, runner.RATE_LIMIT_BACKOFF = runner.RATE_LIMIT_BACKOFF, (0, 0, 0)
    try:
        assert call_with_backoff(flaky, describe="test") == "ok"
    finally:
        runner.RATE_LIMIT_BACKOFF = original
    assert len(attempts) == 3


def test_a_malformed_request_is_not_retried():
    """400 means the request is wrong and will stay wrong; retrying it burns money."""
    from app.knowledge.extract.runner import call_with_backoff

    attempts = []

    def broken():
        attempts.append(1)
        raise RuntimeError("400 INVALID_ARGUMENT")

    with pytest.raises(RuntimeError):
        call_with_backoff(broken, describe="test")
    assert len(attempts) == 1


def test_named_planets_are_not_a_benefic_class():
    """BPHS 12.2 names Mercury, Jupiter and Venus. The extractor declined it as "benefic
    class" -- a real rule lost to the gap warning being too broad."""
    vocabulary = fact_vocabulary()
    assert "if the verse NAMES the planets, extract" in vocabulary


def test_the_gap_list_stays_specific():
    """A measured constraint on this prompt, not a style preference.

    A draft added a sweeping gap warning -- "a HOUSE or a HOUSE LORD as the subject of
    any atom that takes `planet`" -- to stop three fabricated atoms. A/B on the same 20
    units: precision fell from 95% to 44%, because the model stopped trusting
    `lord_of_house_in_house` too and returned six garbled variants of one verse. The
    three fabrications it was meant to prevent still happened.

    Gap warnings must name concrete constructions. A warning broad enough to cast doubt
    on a working condition type costs far more than the fabrications it prevents.
    """
    vocabulary = fact_vocabulary()
    assert "subject of any atom" not in vocabulary


def test_half_atoms_in_the_none_list_are_merged_too():
    """`none` splits the same way `atoms` does; 4 of the 9 faults in one sample were
    there, and a fix covering only `atoms` leaves the identical defect standing."""
    rule = {
        "formation": {
            "atoms": [{"type": "lord_of_house_in_house", "lord_of": 1, "house": 5}],
            "none": [
                {"type": "lord_of_house_in_house", "lord_of": 5},
                {"type": "lord_of_house_in_house", "house": 6},
            ],
        },
        "effects": EFFECTS,
    }
    result = validate_rule(rule)
    assert result.atoms_merged == 1
    assert rule["formation"]["none"] == [
        {"type": "lord_of_house_in_house", "lord_of": 5, "house": 6}
    ]
    assert result.ok, str(result)


def test_grounding_covers_timing_atoms_not_just_formation():
    """BPHS 46.15-21 says "Death may occur in the Dasa of the 6th Lord" and passed the
    whole-book run as VALID carrying `dasha_of{planet: sun}`. `dasha_of` takes a planet
    and the vocabulary has no way to say "the 6th lord's dasha", so the Sun was a
    substitution -- in the one place the grounding check never looked."""
    rule = {
        "formation": {"atoms": []},
        "timing": {
            "activation_factors": {
                "atoms": [{"type": "dasha_of", "planet": "sun", "level": "maha"}]
            }
        },
        "effects": EFFECTS,
    }
    result = validate_rule(
        rule, source_text="Death may occur in the Dasa of the 6th Lord."
    )
    assert any("sun" in p.reason and "never mentioned" in p.reason
               for p in result.problems), str(result)


def test_a_grounded_timing_atom_still_passes():
    rule = {
        "formation": {"atoms": []},
        "timing": {
            "activation_factors": {
                "atoms": [{"type": "dasha_of", "planet": "saturn", "level": "antar"}]
            }
        },
        "effects": EFFECTS,
    }
    result = validate_rule(
        rule,
        source_text="In the antardasa of Saturn the native suffers loss of wealth.",
    )
    assert result.ok, str(result)
