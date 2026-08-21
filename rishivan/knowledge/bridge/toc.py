"""Chapter structure, read from the book's own printed table of contents.

BPHS prints its contents as lines shaped `14. EFFECTS OF THE 1st HOUSE 194`, and
the POC extractor captured them as `heading` elements on PDF page 3 of vol 1. So
the chapter tree is a parse, not an inference — no model, and no guessing where a
chapter starts.

Two page numberings coexist. The TOC cites *printed* pages;
`source_element.page_number` is a *PDF* page index. The offset between them is
recoverable because running heads print the folio, and it is taken as the modal
value over all of them: individual heads are noisy (measured on vol 1 — 630 heads,
modal offset 8, 71 distinct values), so a mode is robust where any single sample
is not. When no offset can be derived, `pdf_page_*` stays `None` rather than being
guessed, because a wrong offset would point every citation in the book at the
wrong page.
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from rishivan.knowledge.bridge.adapt import SourceRow
from rishivan.knowledge.bridge.clean import strip_ingestion_prefixes
from rishivan.knowledge.bridge.roles import is_running_head

_TOC_DOTTED_RE = re.compile(r"^\s*(\d+)\s*\.\s+(.+?)\s+(\d+)\s*$")
"""Vol 1's form: `14. EFFECTS OF THE 1st HOUSE 194` — number, title, start page."""

_TOC_CHAPTER_RE = re.compile(
    r"^\s*(?:CHAPTER|ADHYAYA)[-\s]*(\d+)\s*(?:(\d+)\s*[-–—]\s*(\d+))?\s*$",
    re.IGNORECASE,
)
"""Vol 2's form. Two layouts occur, and both must be read::

    CHAPTER-48 1-110              CHAPTER-61
    DASA SYSTEMS :                355-378
                                  RESULTS OF THE ANTARDASAS ... OF KETU:

The range is optional on the first line because chapters 61-66 put it on its own
line — reading only the two-line layout silently loses exactly those six.

Better than vol 1's form either way, because it states the page *range* outright
rather than leaving the end to be inferred from the following entry.
"""

_BARE_RANGE_RE = re.compile(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s*$")

_LEADING_FOLIO_RE = re.compile(r"^\s*(\d+)\s+\S")
_TRAILING_FOLIO_RE = re.compile(r"\s(\d+)\s*$")

NON_RULE_BEARING_PATTERNS: tuple[tuple[str, str], ...] = (
    ("CREATION", "cosmology"),
    ("INCARNATION", "devotional"),
    ("TO FIND OUT", "calculation method"),
    ("CALCULAT", "calculation method"),
    ("SIXTEEN DIVISIONS", "reference data"),
    ("CONTENTS", "front matter"),
    ("PREFACE", "front matter"),
    ("INTRODUCTION", "front matter"),
    ("INDEX", "back matter"),
    ("APPENDIX", "back matter"),
)
"""Chapter-title substrings marking a chapter as carrying no extractable rules,
each with the reason recorded so a skip is reviewable rather than invisible.

Deliberately conservative. A chapter wrongly kept costs a handful of extraction
calls; a chapter wrongly skipped loses its rules with no trace that it happened.
"""


@dataclass(frozen=True)
class TocEntry:
    number: int
    title: str
    printed_page: int
    printed_page_to: int | None = None
    """Stated explicitly by vol 2's TOC form; `None` for vol 1's, where the end of
    a chapter is inferred from where the next one starts."""


@dataclass
class ChapterDraft:
    number: int
    title: str
    printed_page_from: int | None
    printed_page_to: int | None
    pdf_page_from: int | None
    pdf_page_to: int | None
    is_rule_bearing: bool
    gating_reason: str | None


def _parse_toc_heading(text: str) -> TocEntry | None:
    """One table-of-contents heading in either of BPHS's two forms."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    # Vol 1: everything on one line.
    if match := _TOC_DOTTED_RE.match(lines[0]):
        return TocEntry(
            number=int(match.group(1)),
            title=match.group(2).strip(),
            printed_page=int(match.group(3)),
        )

    # Vol 2: `CHAPTER-48`, with the page range either on the same line or the next,
    # and the title on the line after that.
    if match := _TOC_CHAPTER_RE.match(lines[0]):
        rest = lines[1:]
        if match.group(2) is not None:
            page_from, page_to = int(match.group(2)), int(match.group(3))
        elif rest and (bare := _BARE_RANGE_RE.match(rest[0])):
            page_from, page_to = int(bare.group(1)), int(bare.group(2))
            rest = rest[1:]
        else:
            # A chapter number with no page range is a body heading, not a TOC
            # entry. Admitting it would create a chapter with no page span.
            return None
        return TocEntry(
            number=int(match.group(1)),
            title=(rest[0] if rest else "").rstrip(" :"),
            printed_page=page_from,
            printed_page_to=page_to,
        )

    return None


def parse_toc(rows: Sequence[SourceRow]) -> list[TocEntry]:
    """Every table-of-contents heading, deduplicated and ordered by chapter number.

    Deduplication is required, not defensive: vol 2's contents pages appear twice
    in the scan, so chapters 90 onward each parse twice with identical titles and
    identical page ranges. Left in, they would violate `uq_chapter_book_number` at
    persist time. First occurrence wins — the repeats agree, so there is nothing
    to reconcile.
    """
    seen: dict[int, TocEntry] = {}
    for source in rows:
        if source.type != "heading":
            continue
        entry = _parse_toc_heading(strip_ingestion_prefixes(source.content or ""))
        if entry is not None and entry.number not in seen:
            seen[entry.number] = entry
    return sorted(seen.values(), key=lambda entry: entry.number)


def derive_page_offset(rows: Sequence[SourceRow], *, book_title: str) -> int | None:
    """`pdf_page - printed_page`, as the modal value over running heads."""
    offsets: Counter[int] = Counter()
    for source in rows:
        if source.type != "heading":
            continue
        text = strip_ingestion_prefixes(source.content or "")
        if not is_running_head(text, book_title):
            continue
        match = _LEADING_FOLIO_RE.match(text) or _TRAILING_FOLIO_RE.search(text)
        if match is None:
            continue
        offsets[source.page_number - int(match.group(1))] += 1
    if not offsets:
        return None
    return offsets.most_common(1)[0][0]


def gate_reason(title: str) -> str | None:
    """Why this chapter carries no rules, or `None` if it does."""
    upper = title.upper()
    for needle, reason in NON_RULE_BEARING_PATTERNS:
        if needle in upper:
            return reason
    return None


def build_chapter_tree(
    rows: Sequence[SourceRow], *, book_title: str, total_pdf_pages: int
) -> list[ChapterDraft]:
    """The chapter tree, with page spans and rule-bearing gating."""
    entries = parse_toc(rows)
    offset = derive_page_offset(rows, book_title=book_title)

    drafts: list[ChapterDraft] = []
    for index, entry in enumerate(entries):
        is_last = index == len(entries) - 1
        # Prefer the range the TOC states outright (vol 2) over one inferred from
        # where the next chapter starts (vol 1) — the book's own answer beats ours.
        if entry.printed_page_to is not None:
            printed_to = entry.printed_page_to
        elif is_last:
            printed_to = None
        else:
            printed_to = entries[index + 1].printed_page - 1
        reason = gate_reason(entry.title)

        if offset is None:
            pdf_from = pdf_to = None
        else:
            pdf_from = entry.printed_page + offset
            if printed_to is None:
                pdf_to = total_pdf_pages
            else:
                # A stated range can overrun the scan on the final chapter; the
                # book cannot have more pages than were scanned.
                pdf_to = min(printed_to + offset, total_pdf_pages)

        drafts.append(
            ChapterDraft(
                number=entry.number,
                title=entry.title,
                printed_page_from=entry.printed_page,
                printed_page_to=printed_to,
                pdf_page_from=pdf_from,
                pdf_page_to=pdf_to,
                is_rule_bearing=reason is None,
                gating_reason=reason,
            )
        )
    return drafts
