"""Knowledge-pipeline persistence models."""

# Imported for its side effect: `rule.approved_by` and `review_task.resolved_by` are
# foreign keys to the backend's `user` table, which has no model in this repo. Without
# this, every query touching `rule` raises NoReferencedTableError.
from rishivan.models.user_ref import user_table  # noqa: F401

from rishivan.models.knowledge.affinity import (  # noqa: F401
    RISHI_KEYS,
    WEIGHT_HIGH,
    WEIGHT_LOW,
    WEIGHT_MEDIUM,
    BookRishiAffinity,
)
from rishivan.models.knowledge.book import Book, CopyrightStatus  # noqa: F401
from rishivan.models.knowledge.chapter import Chapter  # noqa: F401
from rishivan.models.knowledge.item import (  # noqa: F401
    NON_RULE_BEARING,
    ItemKind,
    ItemStatus,
    KnowledgeItem,
)
from rishivan.models.knowledge.page import Page, PageElementRow, PageStatus  # noqa: F401
from rishivan.models.knowledge.rule import (  # noqa: F401
    MATCHABLE_PREDICATE,
    ReviewTask,
    Rule,
    RuleAtom,
)
from rishivan.models.knowledge.run import (  # noqa: F401
    ExtractionCache,
    ExtractionRun,
    RunStage,
)
from rishivan.models.knowledge.triage import UnitTriage  # noqa: F401
from rishivan.models.knowledge.unit import SutraUnit  # noqa: F401
