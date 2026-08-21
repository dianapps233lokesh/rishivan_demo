"""Destination B and the skip-nothing invariant.

These tests are deliberately database-free: they pin the *contract* — that the
arithmetic cannot hide a loss, and that every statement kind has somewhere to go.
The query itself is exercised against `rishivan_dev_local` by the coverage report
in `scripts/`.
"""

import pytest

from rishivan.knowledge.accounting import CoverageReport, UnaccountedUnit
from rishivan.models.knowledge.item import (
    NON_RULE_BEARING,
    ItemKind,
    ItemStatus,
    KnowledgeItem,
)


def _report(**kw) -> CoverageReport:
    base = dict(
        book_id=1,
        units=100,
        rule_bearing=60,
        item_only=40,
        unaccounted=0,
        knowledge_carrying_items=30,
        vocabulary_gaps=5,
    )
    return CoverageReport(**{**base, "unaccounted": 0, **kw})


def test_fully_accounted_book_is_ok():
    assert _report().ok is True


def test_a_single_lost_unit_fails_the_report():
    """One unit reaching neither table is a failure, not a rounding error. This is
    the whole point: a lost verse is invisible in the rule count."""
    assert _report(units=101, unaccounted=1).ok is False


def test_accounted_plus_unaccounted_reconciles_to_units():
    r = _report(units=101, unaccounted=1)
    assert r.accounted + r.unaccounted == r.units


def test_rule_and_item_counts_are_disjoint_by_construction():
    """`item_only` excludes units that also produced a rule, so a unit yielding
    both is never double-counted into a false 'accounted' total."""
    r = _report(units=100, rule_bearing=60, item_only=40)
    assert r.accounted == 100


def test_non_rule_bearing_kinds_are_real_kinds():
    assert NON_RULE_BEARING <= set(ItemKind)


def test_non_rule_bearing_excludes_everything_knowledge_carrying():
    """Formulae, definitions, remedies and classifications must never be treated as
    contentless — they are destination B's reason for existing. BPHS 20.5's Shubha
    Rashmi formula is the canonical case."""
    for kind in (
        ItemKind.definition,
        ItemKind.formula,
        ItemKind.reference_table,
        ItemKind.classification,
        ItemKind.enumeration,
        ItemKind.remedy,
        ItemKind.prescription,
    ):
        assert kind not in NON_RULE_BEARING


def test_unclassified_is_not_a_wastebasket():
    """Anything the classifier cannot place stays reviewable rather than being
    filed as contentless narrative."""
    assert ItemKind.unclassified not in NON_RULE_BEARING


def test_out_of_scope_is_a_status_not_a_deletion():
    """'We cannot express this' is recorded, with a reason column to say why."""
    assert ItemStatus.out_of_scope in set(ItemStatus)
    assert "status_reason" in KnowledgeItem.__table__.columns


def test_vocabulary_gap_column_exists_for_the_backlog():
    """Skipped capability becomes a ranked backlog rather than a silent loss."""
    assert "vocabulary_gap" in KnowledgeItem.__table__.columns


def test_importance_is_auditable():
    """A score with no recorded reasons would be an unfalsifiable opinion."""
    cols = KnowledgeItem.__table__.columns
    assert "importance" in cols and "importance_reasons" in cols


def test_item_is_idempotent_per_unit():
    idx = {i.name for i in KnowledgeItem.__table__.indexes}
    assert "uq_item_unit_hash" in idx


def test_every_item_traces_to_a_verse():
    """Provenance is not optional: an item with no unit cannot be cited."""
    assert KnowledgeItem.__table__.columns["unit_id"].nullable is False


@pytest.mark.parametrize("kind", list(ItemKind))
def test_every_kind_is_short_enough_for_the_column(kind):
    assert len(kind.value) <= KnowledgeItem.__table__.columns["kind"].type.length


def test_unaccounted_unit_renders_a_citation():
    assert str(UnaccountedUnit(9264, "47", "1")) == "unit 9264 (ch47:v1)"
