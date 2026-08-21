"""The contract between us and the extraction model.

Sent to Gemini as `response_schema` and validated on return, so this file is
simultaneously a prompt, a parser and a gate. Two design points carry real
weight:

* **bbox is normalized 0..1**, so stored geometry survives a DPI change. Storing
  pixels would silently invalidate every reviewer overlay the day someone
  re-rasterizes at a different resolution.
* **`ChartFigure` emits structure, not prose.** No OCR engine can read a North
  or South Indian chart diagram at all; only a VLM can, and if it returns "Mars
  and Saturn are in the seventh house" we have to parse English back into a
  chart. Asking for `{house: [planet codes]}` makes the answer checkable by
  exact match.
"""

from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator


class ElementType(StrEnum):
    heading = "heading"  # chapter/section title
    verse = "verse"  # Devanagari shloka — a Sutra Unit anchor
    iast = "iast"  # romanized transliteration
    translation = "translation"  # English rendering of the verse
    commentary = "commentary"  # the editor's exposition
    prose = "prose"  # body text belonging to no single verse
    table = "table"  # Ashtakavarga grid, dasha table, koota table
    figure_chart = "figure_chart"  # North/South Indian chart diagram
    footnote = "footnote"
    verse_number = "verse_number"  # a bare numeral printed apart from the verse
    page_furniture = (
        "page_furniture"  # header, folio, running title — dropped at reflow
    )


class Script(StrEnum):
    deva = "deva"
    latin = "latin"
    mixed = "mixed"


class BBox(BaseModel):
    """Normalized page coordinates, origin top-left."""

    x0: float = Field(ge=0.0, le=1.0)
    y0: float = Field(ge=0.0, le=1.0)
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("bbox must satisfy x0 < x1 and y0 < y1")
        return self

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


class TableGrid(BaseModel):
    n_rows: int = Field(ge=1)
    n_cols: int = Field(ge=1)
    cells: dict[str, str] = Field(default_factory=dict)
    """`"row,col"` -> cell text. Sparse: an absent key means an empty cell.

    Keys are strings because this schema round-trips through JSON, where object
    keys cannot be tuples.
    """
    caption: str | None = None


class ChartFigure(BaseModel):
    """A chart diagram read as structure. No OCR engine can produce this."""

    style: Literal["north", "south", "east", "unknown"]
    houses: dict[int, list[str]] = Field(default_factory=dict)
    lagna_slot: int | None = None
    caption: str | None = None

    @model_validator(mode="after")
    def _slots_in_range(self) -> Self:
        for slot in self.houses:
            if not 1 <= slot <= 12:
                raise ValueError(f"house slot {slot} outside 1..12")
        if self.lagna_slot is not None and not 1 <= self.lagna_slot <= 12:
            raise ValueError("lagna_slot outside 1..12")
        return self


class PageElement(BaseModel):
    reading_order: int = Field(ge=0)
    type: ElementType
    script: Script
    text: str
    bbox: BBox | None = None
    """Normalized page geometry, when the extractor captured it.

    `None` for elements bridged from the POC ingestion layer: `source_element`
    holds JSONB null for every one of BPHS's 10,052 rows, so there is no geometry
    to carry across. Optional rather than a synthesized box — a fake bbox would
    place a reviewer's page overlay confidently on the wrong region, which is
    worse than admitting the position is unknown.
    """

    verse_no: str | None = None
    """`"12"`, or a range `"12-14"` where one verse spans several numbers."""

    chapter_hint: str | None = None
    continues_to_next_page: bool = False
    """The element runs off the foot of the page. Reflow merges on this, and it
    is how a verse keeps its translation across a page boundary."""

    table: TableGrid | None = None
    chart: ChartFigure | None = None
    model_confidence: float = Field(ge=0.0, le=1.0, default=1.0)

    disagrees_with_ocr: bool = False
    """Set by the model where its reading differs from the OCR prior. A signal
    to route for review — but *not* a confidence score: VLM self-confidence is
    poorly calibrated, which is why cross-engine agreement is computed
    separately in validate.py."""
