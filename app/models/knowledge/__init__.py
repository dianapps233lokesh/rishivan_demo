"""Knowledge-pipeline persistence models."""

# Imported for its side effect: `rule.approved_by` and `review_task.resolved_by` are
# foreign keys to the backend's `user` table, which has no model in this repo. Without
# this, every query touching `rule` raises NoReferencedTableError.
from app.models.user_ref import user_table  # noqa: F401

from app.models.knowledge.affinity import (  # noqa: F401
    RISHI_KEYS,
    WEIGHT_HIGH,
    WEIGHT_LOW,
    WEIGHT_MEDIUM,
    BookRishiAffinity,
)
from app.models.knowledge.book import Book, CopyrightStatus  # noqa: F401
from app.models.knowledge.chapter import Chapter  # noqa: F401
from app.models.knowledge.item import (  # noqa: F401
    NON_RULE_BEARING,
    ItemKind,
    ItemStatus,
    KnowledgeItem,
)
from app.models.knowledge.page import Page, PageElementRow, PageStatus  # noqa: F401
from app.models.knowledge.rule import (  # noqa: F401
    MATCHABLE_PREDICATE,
    ReviewTask,
    Rule,
    RuleAtom,
)
from app.models.knowledge.run import (  # noqa: F401
    ExtractionCache,
    ExtractionRun,
    RunStage,
)
from app.models.knowledge.triage import UnitTriage  # noqa: F401
from app.models.knowledge.unit import SutraUnit  # noqa: F401
