"""The atomic retrievable unit. Never split below this granularity.

A Sutra Unit is verse + transliteration + translation + commentary held
together. Chunking may split the commentary; it may never separate a verse from
its meaning, because a half-unit still retrieves and still reads fluently — it
is just wrong.
"""

from pydantic import BaseModel, Field


class SutraUnitDraft(BaseModel):
    """Reflow output, before persistence."""

    verse_devanagari: str = ""
    verse_iast: str = ""
    translation: str = ""
    commentary: str = ""
    chapter: str | None = None
    verse_ref_local: str | None = None
    verse_range: tuple[int, int] | None = None
    """`(12, 14)` where one printed verse covers a numbered range."""

    inferred_verse_no: bool = False
    """The number was counted, not read. Reviewers sort on this."""

    element_ids: list[int] = Field(default_factory=list)
    page_from: int | None = None
    page_to: int | None = None
    topic_tags: list[str] = Field(default_factory=list)

    @property
    def has_translation(self) -> bool:
        return bool(self.translation.strip())
