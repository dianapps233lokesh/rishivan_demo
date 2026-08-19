"""Verse references, in both delimiter conventions BPHS actually uses.

Vol 1 closes a verse with `॥` (U+0965 DEVANAGARI DOUBLE DANDA); vol 2 uses `।।`
(U+0964 DEVANAGARI DANDA, twice, usually spaced). Handling only the first drops
57% of vol 2's verse numbers to inferred, silently.
"""

from app.knowledge.bridge.verse_ref import (
    deva_to_int,
    verse_numbers,
    verse_ref_from_translation,
    verse_ref_from_verse_text,
)


def test_deva_to_int():
    assert deva_to_int("१२") == 12
    assert deva_to_int("११") == 11
    assert deva_to_int("१२३") == 123
    assert deva_to_int("") is None
    assert deva_to_int("12") is None


def test_double_danda_form_vol1():
    assert verse_numbers("हनूर्मुखं च ॥१२॥") == [12]


def test_two_single_dandas_form_vol2():
    assert verse_numbers("दशाः कतिविधाः ।। १ ।।") == [1]


def test_two_single_dandas_unspaced():
    assert verse_numbers("कालचक्रदशा चान्या।।६।।") == [6]


def test_multi_verse_element_yields_every_number():
    text = "शिरो नेत्रे ॥१२॥\nमध्यद्रेष्काणगे ॥१३॥\nवस्तिर्लिङ्गगुदे ॥१४॥"
    assert verse_numbers(text) == [12, 13, 14]


def test_ref_from_single_verse_is_plain_number():
    assert verse_ref_from_verse_text("हनूर्मुखं ॥१२॥") == "12"


def test_ref_from_multi_verse_is_a_range():
    # Must be "12-14" so reflow.RANGE_RE pairs it with the "12-14." translation.
    assert verse_ref_from_verse_text("a ॥१२॥\nb ॥१३॥\nc ॥१४॥") == "12-14"


def test_ref_from_unmarked_verse_is_none():
    assert verse_ref_from_verse_text("शिरो नेत्रे तथा कर्णौ") is None


def test_translation_ref_plain_and_range():
    assert verse_ref_from_translation("11. Prediction of Effects") == "11"
    assert verse_ref_from_translation("12-14. Head, eyes, ears") == "12-14"
    assert verse_ref_from_translation("12 - 14. Head, eyes") == "12-14"
    assert verse_ref_from_translation("12–14. en dash") == "12-14"


def test_translation_ref_none_when_unnumbered():
    assert verse_ref_from_translation("Notes : As the effects are studied") is None
    assert verse_ref_from_translation("basis of the Drekkanas") is None


def test_translation_ref_ignores_numbers_that_are_not_a_leading_marker():
    assert verse_ref_from_translation("the 7th house shows marriage") is None


def test_translation_range_collapses_when_both_ends_equal():
    assert verse_ref_from_translation("12-12. same verse twice") == "12"
