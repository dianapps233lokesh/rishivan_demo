"""The books, as passages the extractor can read.

`extract.py` takes a `Passage` and has never had anywhere to get one. This is
that: the eleven ingested books on disk, turned into passages with enough
surrounding context that a verse referring to "that planet" can be resolved.

The corpus lives as JSONL, one unit per line, produced by the bridge that pairs
shlokas with their translations:

    {"unit_id": 10305, "chapter": "48", "verse_ref": "40-41",
     "translation": "40-41: If the sun is located in the Ascendant...",
     "rule": {...}}          <- output of the OLD extractor; see convert.py

Two things this module refuses to do, both of which look like conveniences:

  * It does not silently skip units the bridge marked invalid. They are loaded
    and reported, because a book that suddenly drops from 950 units to 12 is a
    bridge regression, and a loader that quietly hides them makes that
    invisible.

  * It does not fabricate a locator. A passage with no chapter or verse
    reference cannot be cited, and a rule that cannot be cited must not exist -
    so those units are excluded by name, counted, and reported.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional

from rishivan.koonji.extract import Passage

CORPUS_DIR = Path(__file__).resolve().parents[2]
"""Repo root. The books sit in `koonji/` and one stray at the top level."""

BOOKS: dict[str, tuple[str, str]] = {
    # file stem                              -> (book_id, edition_id)
    "koonji-bphs-vol1": ("bphs", "bphs-gcsharma-vol1"),
    "bphs-vol2": ("bphs", "bphs-gcsharma-vol2"),
    "jatakaparijata-sastri-vol1": ("jataka-parijata", "jatakaparijata-sastri-vol1"),
    "jatakaparijata-sastri-vol2": ("jataka-parijata", "jatakaparijata-sastri-vol2"),
    "prasnamarga-raman-part1": ("prasna-marga", "prasnamarga-raman-part1"),
    "prasnamarga-raman-part2": ("prasna-marga", "prasnamarga-raman-part2"),
    "hindupredictiveastrology-raman": ("hindu-predictive", "hindupredictiveastrology-raman"),
    "bhavartha-ratnakara-by-b-v-raman-text": ("bhavartha-ratnakara", "bhavartha-ratnakara-raman"),
    "brihatjataka-row-1919": ("brihat-jataka", "brihatjataka-row-1919"),
    "cheiros-book-of-numbers": ("cheiro-numbers", "cheiros-book-of-numbers"),
    "numerology-and-the-divine-triangle": ("divine-triangle", "numerology-and-the-divine-triangle"),
}
"""Filename stem -> the ids a citation is built from.

Explicit rather than derived from the filename. A book id is what appears in
front of a user under a claim, and deriving it from whatever the file happens to
be called means a rename silently rewrites thousands of citations.
"""

SCHOOL_BY_BOOK: dict[str, str] = {
    "bphs": "school.parashari",
    "jataka-parijata": "school.parashari",
    "bhavartha-ratnakara": "school.parashari",
    "brihat-jataka": "school.parashari",
    "hindu-predictive": "school.parashari",
    "prasna-marga": "school.prashna",
    # Numerology is a separate modality, not a Jyotisha school. It has no
    # school symbol and no rules should be emitted from it into the Parashari
    # namespace - which is why it is absent rather than mapped to a default.
}


@dataclass(slots=True)
class Unit:
    """One line of the corpus, before anything decides it is a rule."""

    unit_id: str
    book_id: str
    edition_id: str
    chapter: str
    verse_ref: str
    translation: str
    valid: bool = True
    problems: list[str] = field(default_factory=list)
    extracted: dict = field(default_factory=dict)
    """The OLD extractor's output for this unit, when there is one. Read by
    `convert.py`; ignored by the live extraction path, which re-reads the
    verse."""

    @property
    def locator(self) -> str:
        return f"ch{self.chapter}.v{self.verse_ref}"

    @property
    def passage_id(self) -> str:
        return f"{self.edition_id}:{self.locator}"

    @property
    def citable(self) -> bool:
        """A unit that cannot be pointed at cannot be cited, and a rule with no
        citation is the one output this system must never produce."""
        return bool(self.chapter and self.verse_ref and self.translation.strip())


_LEADING_REF = re.compile(r"^\s*[\d\-–,\s]+[.:)]\s*")


def clean_translation(text: str) -> str:
    """Strip the verse number the translator printed at the head of the line.

    "40-41: If the sun is located..." becomes "If the sun is located...". The
    number is already in the locator, and leaving it in the quoted text means
    every quote-fidelity check has to know about it.
    """
    return _LEADING_REF.sub("", text or "").strip()


def corpus_files(root: Optional[Path] = None) -> list[Path]:
    """Every ingested book, in a stable order."""
    root = root or CORPUS_DIR
    found = sorted((root / "koonji").glob("*.jsonl")) + sorted(root.glob("koonji-*.jsonl"))
    return [p for p in found if p.stem in BOOKS]


def load_units(path: Path | str) -> list[Unit]:
    """One book. Malformed lines are skipped rather than fatal - a single bad
    line should not cost the other 949."""
    path = Path(path)
    book_id, edition_id = BOOKS[path.stem]
    units: list[Unit] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        units.append(Unit(
            unit_id=str(row.get("unit_id", "")),
            book_id=book_id,
            edition_id=edition_id,
            chapter=str(row.get("chapter") or ""),
            verse_ref=str(row.get("verse_ref") or ""),
            translation=clean_translation(row.get("translation") or ""),
            valid=bool(row.get("valid", True)),
            problems=list(row.get("problems") or []),
            extracted=dict(row.get("rule") or {}),
        ))
    return units


def load_corpus(
    root: Optional[Path] = None, *, books: Optional[Iterable[str]] = None
) -> list[Unit]:
    """Every book, or the named ones. Book ids, not filenames."""
    wanted = set(books) if books else None
    units: list[Unit] = []
    for path in corpus_files(root):
        book_id, _ = BOOKS[path.stem]
        if wanted is None or book_id in wanted or path.stem in wanted:
            units.extend(load_units(path))
    return units


def to_passages(units: list[Unit], *, context_window: int = 2) -> Iterator[Passage]:
    """Units in reading order, each carrying the verses before it.

    The context window is what resolves anaphora. "If he is also aspected by a
    benefic" has no referent on its own, and an extractor given the line alone
    will invent one - which is exactly the failure `anaphora_unresolved` exists
    to flag. Two preceding verses from the same chapter resolves most of it, and
    the flag catches the rest.

    Context deliberately stops at the chapter boundary. The last verse of
    chapter 12 is not context for the first verse of chapter 13; it is a
    different topic, and offering it as context invites the extractor to carry a
    condition across.
    """
    for i, unit in enumerate(units):
        if not unit.citable:
            continue
        preceding = [
            u.translation
            for u in units[max(0, i - context_window):i]
            if u.chapter == unit.chapter and u.translation
        ]
        yield Passage(
            passage_id=unit.passage_id,
            text=unit.translation,
            book_id=unit.book_id,
            edition_id=unit.edition_id,
            locator=unit.locator,
            context="\n".join(preceding),
        )


@dataclass(slots=True)
class CorpusReport:
    units: int = 0
    citable: int = 0
    invalid: int = 0
    by_book: dict[str, int] = field(default_factory=dict)
    uncitable_by_book: dict[str, int] = field(default_factory=dict)

    def __str__(self) -> str:
        lines = [f"{self.units} units · {self.citable} citable · {self.invalid} "
                 f"marked invalid by the bridge"]
        for book, n in sorted(self.by_book.items(), key=lambda kv: -kv[1]):
            dropped = self.uncitable_by_book.get(book, 0)
            note = f"   ({dropped} not citable)" if dropped else ""
            lines.append(f"  {book:26} {n:5}{note}")
        return "\n".join(lines)


def survey(units: list[Unit]) -> CorpusReport:
    """What is actually loadable, reported rather than assumed."""
    report = CorpusReport(units=len(units))
    for unit in units:
        report.by_book[unit.book_id] = report.by_book.get(unit.book_id, 0) + 1
        if unit.citable:
            report.citable += 1
        else:
            report.uncitable_by_book[unit.book_id] = (
                report.uncitable_by_book.get(unit.book_id, 0) + 1
            )
        if not unit.valid:
            report.invalid += 1
    return report
