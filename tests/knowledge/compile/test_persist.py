"""Loading extracted rules is where "degraded, never dropped" becomes a row count.

These tests use no database: `load_decision` is a pure function over an extraction row,
so the rules about what may enter the rule base are checkable directly. Fixtures are real
rows from the BPHS vol 1 whole-book run.
"""

from rishivan.knowledge.compile.persist import load_decision, rule_key_for

VALID_ROW = {
    "unit_id": 9420,
    "chapter": "12",
    "verse_ref": "2",
    "verdict": "VALID",
    "valid": True,
    "translation": "If even one among Mercury, Jupiter and Venus happens to be placed "
    "in a Kendra House the combination destroys all the evils.",
    "problems": [],
    "rule": {
        "rule_key": "12.2.1",
        "formation": {
            "combinator": "any",
            "atoms": [
                {
                    "type": "planet_in_house",
                    "planet": "mercury",
                    "houses": [1, 4, 7, 10],
                }
            ],
        },
        "effects": [
            {
                "polarity": "positive",
                "strength": "moderate",
                "statement": "destroys all evils",
            }
        ],
        "life_domains": ["general"],
        "rule_category": "formation",
        "expressible": True,
    },
}


def test_a_valid_rule_loads_as_parsed_and_unapproved():
    """`ix_rule_matchable` requires `approved_at IS NOT NULL`, so loading must never set
    it. An auto-approved rule reaches a user unreviewed, and 376 machine-checked rules
    are only safe to load in bulk because of this."""
    decision = load_decision(VALID_ROW)
    assert decision.load is True
    assert decision.status == "parsed"
    assert decision.approved_at is None


def test_a_valid_rule_compiles_its_atoms():
    """Four houses in a set form -> four prefilter rows."""
    assert len(load_decision(VALID_ROW).atoms) == 4


def test_a_declined_row_is_not_a_rule():
    """581 of vol 1's 999 extractions declined. They belong in `knowledge_item` with
    their reason; loading them as rules would fill the matcher with conditionless rows
    that match every chart or none."""
    row = {
        **VALID_ROW,
        "verdict": "DECLINED",
        "rule": {
            **VALID_ROW["rule"],
            "expressible": False,
            "out_of_scope_reason": "benefic/malefic as a class",
            "formation": {"atoms": []},
        },
    }
    decision = load_decision(row)
    assert decision.load is False
    assert "declined" in decision.reason


def test_an_invalid_row_loads_unparsed_rather_than_being_discarded():
    """Degraded, never dropped: 42 of vol 1's rules were invalid. They are kept with
    their faults so a reviewer can fix them, and `status='unparsed'` keeps them out of
    `ix_rule_matchable` in the meantime."""
    row = {
        **VALID_ROW,
        "verdict": "INVALID",
        "valid": False,
        "problems": ["atom[0] conjunct: field 'house' does not belong to this type"],
    }
    decision = load_decision(row)
    assert decision.load is True
    assert decision.status == "unparsed"


def test_a_rule_whose_atoms_will_not_compile_is_kept_as_unparsed():
    """Changed deliberately from a refusal. `unparsed` is invisible to the matcher, so
    keeping the row costs nothing and gives a reviewer the fault -- whereas refusing it
    left the unit producing neither a rule nor a knowledge_item, which is the silent
    drop `models/knowledge/item.py` says cannot happen."""
    row = {
        **VALID_ROW,
        "rule": {
            **VALID_ROW["rule"],
            "formation": {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 5}]},
        },
    }
    decision = load_decision(row)
    assert decision.load is True
    assert decision.status == "unparsed"
    assert "compile" in decision.reason


def test_a_conditionless_rule_is_kept_as_unparsed():
    """Same reasoning: nothing to prefilter on is a defect to show a reviewer, not a
    reason to lose the verse."""
    row = {**VALID_ROW, "rule": {**VALID_ROW["rule"], "formation": {"atoms": []}}}
    decision = load_decision(row)
    assert decision.load is True
    assert decision.status == "unparsed"
    assert "nothing to prefilter" in decision.reason


def test_a_timing_only_rule_loads_with_no_atoms():
    """BPHS 46.15-21 carries its condition in `timing`, not `formation`. It has no
    prefilterable natal atom and is still a legitimate rule -- the matcher reaches it by
    dasha rather than by placement."""
    row = {
        **VALID_ROW,
        "rule": {
            **VALID_ROW["rule"],
            "formation": {},
            "rule_category": "timing",
            "timing": {
                "activation_factors": {
                    "atoms": [{"type": "dasha_of", "planet": "saturn", "level": "maha"}]
                }
            },
        },
    }
    decision = load_decision(row)
    assert decision.load is True
    assert decision.atoms == []


def test_rule_key_is_namespaced_by_book():
    """`uq_rule_key_version` is unique across the whole table, and two books both have a
    chapter 12 verse 2."""
    key = rule_key_for(VALID_ROW, book_slug="bphs-gcsharma-vol1")
    assert key.startswith("bphs-gcsharma-vol1:")
    assert "12.2" in key


def test_rule_key_is_stable_across_runs():
    """Re-running extraction must update a rule, not append a twin."""
    assert rule_key_for(VALID_ROW, book_slug="b") == rule_key_for(
        VALID_ROW, book_slug="b"
    )


def test_siblings_from_one_verse_get_distinct_keys():
    """BPHS 26.1 fanned into six rules, one per outcome, sharing one condition. They
    must not collapse into a single row."""
    second = {**VALID_ROW, "rule": {**VALID_ROW["rule"], "rule_key": "12.2.2"}}
    assert rule_key_for(VALID_ROW, book_slug="b") != rule_key_for(second, book_slug="b")


def test_a_row_with_no_extractor_rule_key_falls_back_to_chapter_and_verse():
    row = {**VALID_ROW, "rule": {**VALID_ROW["rule"], "rule_key": None}}
    assert rule_key_for(row, book_slug="b") == "b:12.2"


# --- Blueprint §4 levels 2 and 5 survive the load ---------------------------


def test_the_effect_payload_keeps_the_rule_category():
    """BP §4 level 5 and §8 rule 2: potential and timing are different reasoning
    problems. The extractor emits `rule_category`, and the loader dropped it -- so a
    "when will I marry" question retrieved the same rules as "will I marry"."""
    from rishivan.knowledge.compile.persist import effect_for

    effect = effect_for({"rule_category": "timing", "effects": [], "timing": {}})
    assert effect["rule_category"] == "timing"


def test_a_missing_rule_category_defaults_to_formation():
    """A natal promise is the common case, and the extractor omits the field when the
    rule is one."""
    from rishivan.knowledge.compile.persist import effect_for

    assert effect_for({})["rule_category"] == "formation"


def test_the_effect_payload_keeps_modifiers_and_exceptions():
    """They are Koonji fields (BP §6) and the matcher needs them to know when the
    source itself cancels a rule."""
    from rishivan.knowledge.compile.persist import effect_for

    effect = effect_for({
        "modifiers": [{"kind": "cancel", "condition": {}}],
        "exceptions": [{"statement": "not for Aries", "condition": {}}],
    })
    assert effect["modifiers"] and effect["exceptions"]


def test_the_school_comes_from_the_book_not_a_column_default():
    """§8 rule 5 forbids mixing schools silently. All 398 loaded rules read
    `parashari` because that is the column default, so a Prashna Marga rule would have
    been stored as Parashari."""
    from rishivan.council.source_matrix import school_for

    assert school_for("prasnamarga-raman-part1") == "prashna"
    assert school_for("bphs-gcsharma-vol1") == "parashari"


# --- Degrade, never drop ------------------------------------------------------
#
# `models/knowledge/item.py`: "Every `sutra_unit` must produce at least one `rule` row or
# one `knowledge_item` row... 'We dropped it' therefore cannot happen quietly." It could,
# and it did: the loader refused declines and non-compiling rules alike and wrote neither.

DECLINED_ROW = {
    "unit_id": 7, "chapter": "15", "verse_ref": "1",
    "verdict": "DECLINED", "valid": True,
    "translation": "A benefic in the 2nd House is the giver of wealth.",
    "rule": {
        "rule_key": "benefic_2nd_wealth",
        "expressible": False,
        "out_of_scope_reason": "benefic/malefic as a class -- no atom expresses "
                               "planetary benevolence",
        "formation": {"atoms": []},
        "effects": [{"polarity": "positive", "strength": "moderate",
                     "statement": "giver of wealth"}],
    },
}

NON_COMPILING_ROW = {
    "unit_id": 8, "chapter": "50", "verse_ref": "9-13",
    "verdict": "INVALID", "valid": False,
    "translation": "If the 10th lord is in a sign...",
    "rule": {
        "rule_key": "50_9_13_1",
        "formation": {"atoms": [{"type": "lord_of_house_in_sign", "lord_of": 10}]},
        "effects": [{"polarity": "positive", "strength": "moderate",
                     "statement": "an outcome"}],
    },
}


def test_a_decline_becomes_a_knowledge_item_not_a_discard():
    from rishivan.knowledge.compile.persist import load_decision

    decision = load_decision(DECLINED_ROW)
    assert decision.load is False
    assert decision.destination == "item"


def test_a_decline_carries_its_reason_as_the_vocabulary_gap():
    """This is what makes the backlog real: 195 benefic/malefic and 150 avastha
    declines are a ranked list of what the engine needs next, and they existed only in
    terminal output."""
    from rishivan.knowledge.compile.persist import load_decision

    decision = load_decision(DECLINED_ROW)
    assert any("benefic" in gap for gap in decision.vocabulary_gap)


def test_a_rule_whose_atoms_will_not_compile_loads_as_unparsed():
    """Same treatment as its siblings. Of BPHS vol 2's 66 invalid rules, 36 loaded as
    `unparsed` and 30 were dropped -- the only difference being whether their malformed
    atoms happened to compile."""
    from rishivan.knowledge.compile.persist import load_decision

    decision = load_decision(NON_COMPILING_ROW)
    assert decision.load is True
    assert decision.status == "unparsed"
    assert decision.atoms == []


def test_an_unparsed_rule_keeps_the_fault_that_caused_it():
    from rishivan.knowledge.compile.persist import load_decision

    assert "sign" in load_decision(NON_COMPILING_ROW).reason


def test_the_reason_does_not_blame_the_validator():
    """The old message read "validation should have rejected it before compilation".
    Validation DID reject it -- the verdict is INVALID. The message sent a reader
    looking for a validator bug that was not there."""
    from rishivan.knowledge.compile.persist import load_decision

    assert "validation should have" not in load_decision(NON_COMPILING_ROW).reason


def test_a_valid_rule_still_loads_as_parsed():
    from rishivan.knowledge.compile.persist import load_decision

    decision = load_decision(VALID_ROW)
    assert decision.load is True
    assert decision.status == "parsed"
    assert decision.destination == "rule"
