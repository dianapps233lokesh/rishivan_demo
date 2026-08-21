"""The bridge CLI's constants — the pilot's scope, asserted rather than assumed."""

from rishivan.models.knowledge.affinity import RISHI_KEYS, WEIGHT_HIGH
from scripts.bridge_bphs import BPHS_RISHI_WEIGHTS, BPHS_VOLUMES


def test_both_volumes_targeted():
    assert [slug for slug, _ in BPHS_VOLUMES] == [
        "bphs-gcsharma-vol1",
        "bphs-gcsharma-vol2",
    ]


def test_both_volumes_share_one_book_title():
    """Two documents, one work — they must register under the same title."""
    assert len({title for _, title in BPHS_VOLUMES}) == 1


def test_bphs_is_high_affinity_for_all_eight_rishis():
    """The client's matrix rates BPHS High across every Rishi, which is why it is
    the pilot book: one work exercises the whole affinity vector."""
    assert set(BPHS_RISHI_WEIGHTS) == set(RISHI_KEYS)
    assert all(weight == WEIGHT_HIGH for weight in BPHS_RISHI_WEIGHTS.values())
