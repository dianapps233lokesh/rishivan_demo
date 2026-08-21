"""Embedding batches are bounded by tokens, not by document count.

`text-embedding-004` accepts up to 20,000 input tokens PER REQUEST, summed across the
batch. Batching by document count worked at 376 rules and failed at 1,046 with
`400 INVALID_ARGUMENT ... input token count is 20191 but the model supports up to
20000` -- after `--reset` had already emptied the live collection.
"""

import pytest

from scripts.embed_rules import TOKEN_BUDGET, token_batches


def est(text: str) -> int:
    from scripts.embed_rules import estimated_tokens

    return estimated_tokens(text)


def test_every_batch_stays_inside_the_budget():
    texts = ["word " * 300] * 200          # ~375 tokens each, 200 of them
    for batch in token_batches(texts, TOKEN_BUDGET):
        assert sum(est(t) for t in batch) <= TOKEN_BUDGET


def test_no_text_is_lost_or_duplicated():
    texts = [f"verse {i} " + "x " * (i % 40) for i in range(150)]
    flattened = [t for batch in token_batches(texts, TOKEN_BUDGET) for t in batch]
    assert flattened == texts


def test_order_is_preserved():
    """Vectors are zipped back against the rules by position, so a reordered batch
    would attach every embedding to the wrong rule."""
    texts = [f"t{i}" for i in range(40)]
    flattened = [t for batch in token_batches(texts, 50) for t in batch]
    assert flattened == texts


def test_a_single_oversized_text_goes_out_alone():
    """Rather than being dropped or silently truncated. It may still be rejected by the
    API, which is a visible failure on one rule instead of a lost batch."""
    huge = "word " * 20000
    batches = list(token_batches(["small", huge, "small"], TOKEN_BUDGET))
    assert [len(b) for b in batches].count(1) >= 1
    assert huge in [t for b in batches for t in b]


def test_the_budget_leaves_headroom_under_the_hard_limit():
    """The estimate is chars/4 and real tokenisation varies, so the budget must sit
    below 20,000 rather than at it."""
    assert TOKEN_BUDGET < 20000


@pytest.mark.parametrize("texts", [[], [""]])
def test_degenerate_input_does_not_hang(texts):
    assert [t for b in token_batches(texts, TOKEN_BUDGET) for t in b] == texts
