from app.knowledge.bridge.clean import strip_ingestion_prefixes


def test_strips_heading_prefix():
    raw = "[Heading: Brihat Parasara Hora Shastra 197]\n11. Prediction of Effects."
    assert strip_ingestion_prefixes(raw) == "11. Prediction of Effects."


def test_strips_heading_prefix_with_pipe_separator():
    raw = "[Heading: 198 Effects of The First House] | basis of the Drekkanas"
    assert strip_ingestion_prefixes(raw) == "basis of the Drekkanas"


def test_strips_original_content_label():
    raw = "[Heading: X 197]\nOriginal Content:\nशिरो नेत्रे ॥१२॥"
    assert strip_ingestion_prefixes(raw) == "शिरो नेत्रे ॥१२॥"


def test_preserves_internal_newlines_between_verse_lines():
    raw = "Original Content:\nline one ॥१२॥\nline two ॥१३॥"
    assert strip_ingestion_prefixes(raw) == "line one ॥१२॥\nline two ॥१३॥"


def test_idempotent():
    once = strip_ingestion_prefixes("[Heading: X 1] | body")
    assert strip_ingestion_prefixes(once) == once


def test_handles_empty_and_blank():
    assert strip_ingestion_prefixes("") == ""
    assert strip_ingestion_prefixes("   ") == ""
