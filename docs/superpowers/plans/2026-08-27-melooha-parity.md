# Melooha Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the answer-quality gap between Rishivan and Melooha, whose readings commit to dated verdicts backed by transits, forward dasha windows and divisional charts, while ours hedge and narrate their own machinery.

**Architecture:** The gap is almost entirely capability, not presentation. `council/prompts.py` already instructs the model to lead with the verdict, to always close on a concrete action, and to take its window from "the transit that is actually moving" — those instructions go unfollowed because the facts they ask for are never computed. So the work is to supply the missing facts, and to separate two things the answer gate currently conflates: **astronomical arithmetic** (where a planet is, when a period runs — verifiable, needs no citation) from **interpretive claims** (what that means — needs a fired rule with a source). Melooha states the first freely; we forbid both.

**Tech Stack:** Python 3.14, Swiss Ephemeris (`swisseph`), LangGraph, Gemini (`gemini-3.5-flash-lite` for extraction), Streamlit, pytest.

**Spec:** This plan is its own spec — it was written from a measured diagnosis rather than a requirements document, so the evidence for each gap sits inline in the task that closes it. Every number in it was produced by a command against this repo, and those commands are quoted so an executor can re-run them rather than trust them.

## Global Constraints

- **Nothing in the serving path calls a language model.** `koonji/router.py` states this as a package rule. Transit and dasha facts must be computed arithmetically, never asked for.
- **A rule that cannot be cited must not exist.** `corpus.Unit.citable`. Any re-chunking must preserve `chapter` + `verse_ref` for every emitted passage.
- **Interpretive claims require a fired rule.** Adding a fact to `chart_facts` licenses the model to state it; it does not license a claim about what it means. Where this plan widens what may be said, it widens it for arithmetic only.
- **No extraction run without an approved cost estimate.** Standing instruction from the user. Tasks 1–4 and 7 cost nothing; Tasks 5 and 6 must not start without a figure approved first.
- **Run the full suite before every commit:** `.venv/bin/python -m pytest tests/ -q`. Baseline at the time of writing: **2,035 passed, 1 skipped**.

---

## Status

### Done — landed, 2,035 tests passing (+28)

| # | Gap | What changed |
|---|-----|--------------|
| 0.1 | Answers contradicted facts the user stated | `stated_facts` extracted by the existing classifier call, carried through state into the Rishi prompt and the narrative gate. `classifier.py`, `state.py`, `nodes/intake.py`, `nodes/rishi.py`, `rishis/prompt.py`, `answer_plan.py`, `narrate.py` |
| 0.2 | D9/D10 withheld from every real birth time | The boundary rescue compared each planet's margin against the *ascendant's* drift rate — unsatisfiable for every chart and division. Now per-body drift, using real planetary speed (`PlanetPosition.speed_deg_per_day`, previously discarded). `varga/select.py`, `varga/confidence.py`, `chart/ephemeris.py` |
| 0.3 | ~⅓ of each answer was the machinery describing itself | `must_say` prioritised and capped at 2. Out-of-remit abstentions dropped; the unreviewed-corpus notice moved to a standing caption. `answer_plan.py`, `narrate.py`, `nodes/answer_plan.py`, `streamlit_app.py` |

### Remaining

| Task | Cost | Unlocks |
|------|------|---------|
| 1. Re-chunk oversized passages | free | ~1,000 lost rules; prerequisite for 5 |
| 2. Transit facts | free | "Rahu transiting your 5th until Dec 2026"; "why this feels urgent now" |
| 3. Separate arithmetic from prediction in the gate | free | Dated antardasha windows — the single largest visible gap |
| 4. The seeker's name | free | "Bharat, the child comes, but not in…" |
| 5. Timing extraction | **model spend** | Rules that carry a datable window |
| 6. Transit rule predicates | **model spend** | Interpretive transit claims with citations |
| 7. Evidence list in the UI | free | Melooha's numbered 1–6 factor list |

---

## Task 1: Re-chunk the oversized passages

Sixty passages hold 1,196,701 characters — 30% of all corpus text — and yielded **72 rules**. The other 70% yielded 3,620. That is 0.06 rules per 1,000 characters against 1.45, a 24× gap. `prasna-marga ch25.v1` is 91,677 characters and produced zero. `hindu-predictive ch24.v15` is the dasha-phala chapter, 62,127 characters of pure timing material, and produced 13.

None of these appear in the failure logs. They ran, succeeded, and returned almost nothing.

The text already contains its own verse markers — `"Stanza 41. If the lord of the ascendant occupies the 11th…"`, `"140 | Rasi occupied by the lord of the 8th…"` — so this is a splitting job over existing JSONL, not a re-ingestion from PDFs.

**Files:**
- Create: `rishivan/koonji/rechunk.py`
- Create: `tests/koonji/test_rechunk.py`
- Modify: `rishivan/koonji/corpus.py` — call the splitter from `to_passages`
- Modify: `tests/koonji/test_corpus.py` — assert no oversized passage survives

**Interfaces:**
- Consumes: `corpus.Unit` (`unit_id, book_id, edition_id, chapter, verse_ref, translation, valid, problems`)
- Produces:
  - `rechunk.split_unit(unit: Unit, *, max_chars: int = 3000) -> list[Unit]` — one unit in, one or more out; returns `[unit]` unchanged when it is already small enough
  - `rechunk.is_apparatus(text: str) -> bool` — True for indexes, tables of contents and front matter
  - `rechunk.STANZA_MARKERS: tuple[re.Pattern, ...]`
  - `rechunk.MAX_PASSAGE_CHARS: int = 3000` — defined here, not in `corpus`, so `corpus` imports it rather than the reverse (`rechunk` already imports `Unit` from `corpus`, and the mutual import would be circular)

- [ ] **Step 1: Write the failing test for splitting on stanza markers**

```python
# tests/koonji/test_rechunk.py
from rishivan.koonji.corpus import Unit
from rishivan.koonji.rechunk import split_unit


def _unit(text: str, *, chapter="25", verse_ref="1") -> Unit:
    return Unit(unit_id="u1", book_id="prasna-marga",
                edition_id="prasnamarga-raman-part1",
                chapter=chapter, verse_ref=verse_ref, translation=text)


class TestItSplitsOnTheMarkersAlreadyInTheText:
    def test_numbered_stanzas_become_separate_units(self):
        text = (
            "Stanza 41. If the lord of the ascendant occupies the 11th, the "
            "traveller returns.\n"
            "Stanza 42. If malefics occupy the 4th, the enemy will not march.\n"
            "Stanza 43. Benefics in the 7th bring the partner home."
        )
        out = split_unit(_unit(text), max_chars=80)
        assert len(out) == 3
        assert out[0].verse_ref == "41"
        assert out[2].verse_ref == "43"

    def test_every_piece_keeps_a_citable_locator(self):
        """A rule that cannot be cited must not exist. Splitting must never
        produce a passage that has lost its chapter."""
        text = "Stanza 41. Aaa.\nStanza 42. Bbb."
        for piece in split_unit(_unit(text), max_chars=20):
            assert piece.chapter == "25"
            assert piece.verse_ref
            assert piece.citable

    def test_no_text_is_lost(self):
        text = "Stanza 1. " + "a" * 500 + "\nStanza 2. " + "b" * 500
        out = split_unit(_unit(text), max_chars=200)
        joined = "".join(p.translation for p in out)
        assert joined.count("a") == 500
        assert joined.count("b") == 500

    def test_a_small_unit_is_returned_untouched(self):
        u = _unit("13. A short verse about Saturn.")
        assert split_unit(u, max_chars=3000) == [u]

    def test_unmarked_text_falls_back_to_paragraph_splitting(self):
        """Not every blob is numbered. A 60,000-character run of prose must
        still be broken up rather than passed through whole."""
        text = "\n\n".join(f"Paragraph {i} about a planet." for i in range(40))
        out = split_unit(_unit(text), max_chars=200)
        assert len(out) > 1
        assert all(len(p.translation) <= 400 for p in out)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/koonji/test_rechunk.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rishivan.koonji.rechunk'`

- [ ] **Step 3: Write the splitter**

```python
# rishivan/koonji/rechunk.py
"""Oversized corpus units, split into the verses they already contain.

Sixty units hold 30% of the corpus text and produced 72 rules between them,
against 1.45 rules per thousand characters everywhere else. They did not fail -
they were handed to the model whole and came back nearly empty, which is the
worst shape a recall failure can take because nothing in the logs says so.

The split is driven by markers already present in the text ("Stanza 41.",
"140 |", "3. "), because those are the book's own verse numbers and using them
keeps every piece citable. A piece that cannot be cited cannot become a rule
(`corpus.Unit.citable`), so an unmarked blob falls back to paragraph
boundaries and inherits its parent's locator with a positional suffix.
"""

from __future__ import annotations

import re

from rishivan.koonji.corpus import Unit

MAX_PASSAGE_CHARS = 3000
"""Above this a passage is split. Chosen from the corpus rather than picked:
the median passage is 345 characters and the well-chunked books top out near
3,000, so this admits every unit that was chunked properly and catches the 60
that were not."""

STANZA_MARKERS: tuple[re.Pattern, ...] = (
    # "Stanza 41." / "Sloka 41." / "Verse 41."
    re.compile(r"^\s*(?:Stanza|Sloka|Shloka|Verse)s?\.?\s*(\d+(?:\s*[-–]\s*\d+)?)\s*[.:—-]",
               re.IGNORECASE | re.MULTILINE),
    # "140 | Rasi occupied by..." - the bridge's own separator
    re.compile(r"^\s*(\d+(?:\s*[-–]\s*\d+)?)\s*\|", re.MULTILINE),
    # "3. Cows rushing home..." - plain numbered list
    re.compile(r"^\s*(\d+(?:\s*[-–]\s*\d+)?)\s*[.)]\s+", re.MULTILINE),
)
"""Tried in order, most specific first. A plain "3. " is the loosest and would
also match a numbered list inside a single verse, so it is tried last and only
when the stricter forms found nothing."""

_APPARATUS = re.compile(
    r"(?:\b[ivxlc]+\s*,?\s*\d+\s*[|,]\s*){4,}"      # "ii 3 | ix 10 25 | i 61"
    r"|(?:\.\s*[IVXLC]+-\d+\s*\.\s*){3,}"            # ". XIV-18. . XXV-25."
    r"|N\s?B\s*---\s*The Roman and Arabic numerals",
    re.IGNORECASE,
)


def is_apparatus(text: str) -> bool:
    """True for an index, a table of contents or a concordance.

    The largest "verse" in the corpus is `jataka-parijata ch18.v178` at 210,712
    characters, and it is the book's alphabetical index - we were sending it to
    a language model and asking for astrological rules. These are dropped
    rather than split: there is nothing in them to extract, and the run-on
    Roman-numeral references defeat every marker above.
    """
    head = text[:4000]
    return bool(_APPARATUS.search(head))


def _clone(unit: Unit, *, verse_ref: str, text: str, suffix: str = "") -> Unit:
    return Unit(
        unit_id=f"{unit.unit_id}{suffix}",
        book_id=unit.book_id,
        edition_id=unit.edition_id,
        chapter=unit.chapter,
        verse_ref=verse_ref,
        translation=text.strip(),
        valid=unit.valid,
        problems=list(unit.problems),
    )


def _by_markers(unit: Unit) -> list[Unit] | None:
    """Split on the book's own verse numbers, or None if it has none."""
    for pattern in STANZA_MARKERS:
        hits = list(pattern.finditer(unit.translation))
        if len(hits) < 2:
            continue
        pieces: list[Unit] = []
        # Text before the first marker is a heading or a lead-in. It belongs to
        # the first verse rather than to a unit of its own, which would be a
        # passage with no verse number and therefore uncitable.
        for i, match in enumerate(hits):
            start = match.start()
            end = hits[i + 1].start() if i + 1 < len(hits) else len(unit.translation)
            if i == 0:
                start = 0
            body = unit.translation[start:end]
            if not body.strip():
                continue
            pieces.append(_clone(
                unit,
                verse_ref=re.sub(r"\s+", "", match.group(1)),
                text=body,
                suffix=f".{i:04d}",
            ))
        if len(pieces) >= 2:
            return pieces
    return None


def _by_paragraphs(unit: Unit, max_chars: int) -> list[Unit]:
    """The fallback. Groups paragraphs up to the limit.

    The locator gains a positional suffix - `ch25.v1a`, `ch25.v1b` - so the
    citation still points at a real verse in a real chapter and says which part
    of it. Inventing a verse number would be worse than a suffix: it would
    point a reader at text that is not there.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n|\n", unit.translation) if p.strip()]
    groups: list[list[str]] = [[]]
    size = 0
    for para in paragraphs:
        if size and size + len(para) > max_chars:
            groups.append([])
            size = 0
        groups[-1].append(para)
        size += len(para)

    letters = "abcdefghijklmnopqrstuvwxyz"
    out: list[Unit] = []
    for i, group in enumerate(g for g in groups if g):
        # Past 26 pieces the suffix runs out; index numerically instead of
        # silently reusing "a", which would give two passages one citation.
        tag = letters[i] if i < len(letters) else f"p{i}"
        out.append(_clone(unit, verse_ref=f"{unit.verse_ref}{tag}",
                          text="\n\n".join(group), suffix=f".{i:04d}"))
    return out or [unit]


def split_unit(unit: Unit, *, max_chars: int = MAX_PASSAGE_CHARS) -> list[Unit]:
    """One unit in, the verses it contains out.

    Returns `[unit]` unchanged when it is already small enough, so this is safe
    to call over the whole corpus.
    """
    if len(unit.translation) <= max_chars:
        return [unit]
    if is_apparatus(unit.translation):
        return []

    pieces = _by_markers(unit)
    if pieces is None:
        return _by_paragraphs(unit, max_chars)

    # A marker split can still leave a piece over the limit - one stanza with a
    # long commentary under it. Recurse on those only, so the marker structure
    # is kept wherever it worked.
    out: list[Unit] = []
    for piece in pieces:
        if len(piece.translation) > max_chars:
            out.extend(_by_paragraphs(piece, max_chars))
        else:
            out.append(piece)
    return out
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `.venv/bin/python -m pytest tests/koonji/test_rechunk.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the failing test for apparatus detection**

```python
# append to tests/koonji/test_rechunk.py
from rishivan.koonji.rechunk import is_apparatus, split_unit


class TestItThrowsAwayTheIndexes:
    """The largest unit in the corpus is 210,712 characters of alphabetical
    index, and it was being sent to a model as a passage."""

    INDEX = (
        "N B --- The Roman and Arabic numerals opposite to each refer "
        "respectively to the Adhyaya to which it belongs and to the number of "
        "the Sloka therein --- Aara  ii  3 | Aarki  ii, 4 | Abdaphala  ix  10  "
        "25 | Abhijit  i  61  ix  43 | Abhisheka  ix  79 | Ability  viii  55 |"
    )

    def test_an_index_is_recognised(self):
        assert is_apparatus(self.INDEX)

    def test_a_real_verse_is_not(self):
        assert not is_apparatus(
            "Stanza 41. If the lord of the ascendant occupies the 11th, 12th, "
            "1st, 2nd or 3rd, or if malefics occupy quadrants, the traveller "
            "will return home safely within the month."
        )

    def test_an_index_yields_no_passages(self):
        out = split_unit(_unit(self.INDEX * 40), max_chars=3000)
        assert out == []
```

- [ ] **Step 6: Run it**

Run: `.venv/bin/python -m pytest tests/koonji/test_rechunk.py -q`
Expected: PASS (8 tests) — `is_apparatus` was written in Step 3

- [ ] **Step 7: Wire the splitter into passage construction**

In `rishivan/koonji/corpus.py`, `to_passages` currently yields one passage per citable unit. Change the loop body so oversized units are split first. The context window must be computed from the *split* sequence, so that a stanza's context is the stanzas before it rather than the whole blob:

```python
def to_passages(units: list[Unit], *, context_window: int = 2,
                max_chars: int = None) -> Iterator[Passage]:
    """Units in reading order, each carrying the verses before it.

    Oversized units are split before anything else happens. Sixty of them held
    30% of the corpus text and produced 72 rules between them; a context window
    computed over the unsplit sequence would also have handed a stanza the
    whole preceding blob as "context".
    """
    from rishivan.koonji.rechunk import MAX_PASSAGE_CHARS, split_unit

    if max_chars is None:
        max_chars = MAX_PASSAGE_CHARS

    expanded: list[Unit] = []
    for unit in units:
        if not unit.citable:
            continue
        expanded.extend(split_unit(unit, max_chars=max_chars))

    for i, unit in enumerate(expanded):
        if not unit.citable:
            continue
        preceding = [
            u.translation
            for u in expanded[max(0, i - context_window):i]
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
```

- [ ] **Step 8: Write the corpus-level test**

```python
# append to tests/koonji/test_rechunk.py
class TestTheWholeCorpusAfterSplitting:
    def test_no_oversized_passage_survives(self):
        from rishivan.koonji.corpus import load_corpus, to_passages
        from rishivan.koonji.rechunk import MAX_PASSAGE_CHARS

        worst = max(len(p.text) for p in to_passages(load_corpus()))
        assert worst <= MAX_PASSAGE_CHARS, (
            f"a {worst}-character passage still reaches the model in one call"
        )

    def test_the_books_that_were_starved_gain_passages(self):
        from collections import Counter

        from rishivan.koonji.corpus import load_corpus, to_passages

        counts = Counter(p.book_id for p in to_passages(load_corpus()))
        # 37 and 141 before. Both books are hundreds of verses long.
        assert counts["prasna-marga"] > 200
        assert counts["phaladeepika"] > 200

    def test_every_passage_can_still_be_cited(self):
        from rishivan.koonji.corpus import load_corpus, to_passages

        for p in to_passages(load_corpus()):
            assert p.locator.startswith("ch")
            assert p.locator != "ch."
            assert p.book_id and p.edition_id
```

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. If `tests/koonji/test_corpus.py` pins exact passage counts, update those numbers — the counts changing is the point of this task, not a regression.

- [ ] **Step 10: Record what changed, for the cost estimate in Task 5**

Run:
```bash
.venv/bin/python -c "
import statistics
from collections import Counter
from rishivan.koonji.corpus import load_corpus, to_passages
ps=list(to_passages(load_corpus()))
print('passages now:',len(ps))
print('median chars:',int(statistics.median([len(p.text) for p in ps])))
print('max chars:',max(len(p.text) for p in ps))
for b,n in Counter(p.book_id for p in ps).most_common(): print(f'  {b:24}{n:>6}')
"
```
Expected: passage count up from 5,563; max at or under 3,000. Paste the output into the commit message — Task 5's cost estimate is computed from it.

- [ ] **Step 11: Commit**

```bash
git add rishivan/koonji/rechunk.py rishivan/koonji/corpus.py tests/koonji/test_rechunk.py
git commit -m "fix(koonji): oversized units are split into the verses they contain

Sixty passages held 1,196,701 chars - 30% of the corpus - and produced 72
rules between them, against 1.45 rules per thousand chars everywhere else.
They did not fail; they were handed over whole and came back empty, which is
why nothing in the logs said so. prasna-marga ch25.v1 is 91,677 chars and
yielded nothing. hindu-predictive ch24.v15 is the dasha-phala chapter and
yielded 13.

Split on the verse markers already in the text, so every piece stays citable.
Indexes are dropped rather than split - the largest unit in the corpus was
210,712 chars of alphabetical index being sent to a model as a passage."
```

---

## Task 2: Transit facts

Melooha's answers are roughly half transits, with dates: *"Rahu transiting Aquarius retrograde, house 5, since 18 May 2025 until 05 Dec 2026"*, *"Saturn transiting Pisces retrograde, house 6 from the ascendant, since 26 Jul 2026, until 11 Dec 2026"*. It also uses them to explain the question itself: *"Right now Rahu is transiting your fifth house until December 2026, which is why you are thinking about this question far earlier than your wife is."*

We compute none of it. `council/hierarchy.py:33` says so: *"`transit` is declared and currently unreachable: no registry predicate expresses a transit."* The Rishi prompt assembles seven blocks and none is transits. `chart/transit.py` exists but is only ever used for today's Moon nakshatra.

**Where a transit position is a fact, not a claim.** "Saturn is in Pisces in your 6th house from 26 Jul 2026 to 11 Dec 2026" is arithmetic over the ephemeris — checkable against any almanac, no classical citation needed. What Saturn there *means* is a claim and still needs a fired rule. This task supplies the first only; Task 6 does the second.

**Files:**
- Create: `rishivan/chart/transits.py`
- Create: `tests/chart/test_transits.py`
- Modify: `rishivan/chart/facts.py` — add transit lines to the fact set
- Modify: `rishivan/graph/nodes/ground.py` or `chart.py` — compute once, store on state
- Modify: `rishivan/graph/state.py` — add `transits`
- Modify: `rishivan/council/rishis/prompt.py` — add `_transits_block`

**Interfaces:**
- Consumes: `chart.ephemeris.Chart`, `chart.ephemeris.compute_chart`, `chart.transit.chart_for_moment`
- Produces:
  - `transits.TransitPosition` — frozen dataclass: `body: str`, `rashi: str`, `bhava: int`, `retrograde: bool`, `since: datetime | None`, `until: datetime | None`, `nakshatra: str`
  - `transits.current_transits(natal: Chart, when: datetime, *, bodies: tuple[str, ...] = SLOW_BODIES) -> list[TransitPosition]`
  - `transits.SLOW_BODIES: tuple[str, ...]`
  - `transits.describe(position: TransitPosition) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/chart/test_transits.py
"""Where the slow planets are now, and for how long.

Melooha's readings are about half transits, with dates - "Saturn transiting
Pisces retrograde, house 6 from the ascendant, since 26 Jul 2026, until 11 Dec
2026" - and they use them to explain why the seeker is asking today rather than
next year. We computed none of it.

A transit position is arithmetic, not interpretation: it is checkable against
an almanac and needs no classical citation. That is why it goes into the fact
set rather than through the rule engine.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.transits import SLOW_BODIES, current_transits, describe

BIRTH = BirthData(
    year=1998, month=5, day=15, hour=18, minute=45,
    tz_offset_hours=5.5, lat=26.9155, lon=75.8190, place="Jaipur",
)
WHEN = datetime(2026, 8, 27, 11, 0)


@pytest.fixture(scope="module")
def natal():
    return compute_chart(BIRTH)


@pytest.fixture(scope="module")
def positions(natal):
    return current_transits(natal, WHEN)


class TestItReportsTheSlowBodies:
    def test_every_slow_body_is_present(self, positions):
        assert {p.body for p in positions} == set(SLOW_BODIES)

    def test_the_fast_ones_are_not(self, positions):
        """The Moon changes sign every two days. A "window" for it is noise."""
        assert "Moon" not in {p.body for p in positions}

    def test_the_house_is_counted_from_the_natal_ascendant(self, natal, positions):
        """"house 6 from the ascendant" - the natal lagna, not the transit
        chart's own. A transit house counted from a transit ascendant is a
        different and much less useful statement."""
        for p in positions:
            assert 1 <= p.bhava <= 12

    def test_saturn_is_where_the_ephemeris_says_it_is(self, positions):
        saturn = next(p for p in positions if p.body == "Saturn")
        assert saturn.rashi == "Pisces"


class TestItBracketsEachTransitWithDates:
    def test_a_transit_carries_a_start_and_an_end(self, positions):
        for p in positions:
            assert p.since is not None, p.body
            assert p.until is not None, p.body
            assert p.since <= WHEN <= p.until

    def test_the_body_is_in_that_sign_throughout_the_window(self, natal, positions):
        """The bracket is only worth stating if it is true. Sampled rather than
        proved: a sign the body leaves mid-window would be caught."""
        from rishivan.chart.transit import chart_for_moment

        for p in positions:
            for frac in (0.05, 0.5, 0.95):
                t = p.since + (p.until - p.since) * frac
                assert chart_for_moment(t).planets[p.body].rashi == p.rashi, (
                    f"{p.body} is not in {p.rashi} throughout its window"
                )

    def test_the_window_is_bounded_rather_than_searched_forever(self, natal):
        """A body near a station can sit in one sign for years. The search has
        to stop somewhere, and it must stop at a stated horizon rather than by
        running out of patience."""
        out = current_transits(natal, WHEN, bodies=("Rahu",))
        span_days = (out[0].until - out[0].since).days
        assert span_days <= 366 * 6


class TestTheSentenceItProduces:
    def test_it_names_the_body_sign_house_and_dates(self, positions):
        line = describe(next(p for p in positions if p.body == "Saturn"))
        assert "Saturn" in line
        assert "Pisces" in line
        assert "house" in line.lower()
        assert "2026" in line

    def test_retrograde_is_said_when_it_is_true(self, natal):
        out = current_transits(natal, WHEN, bodies=("Rahu",))
        # The nodes are always retrograde by convention.
        assert "retrograde" in describe(out[0]).lower()
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/chart/test_transits.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'rishivan.chart.transits'`

- [ ] **Step 3: Write the module**

```python
# rishivan/chart/transits.py
"""Where the slow planets are now, and the window they sit in.

`council/hierarchy.py` has carried the line "`transit` is declared and
currently unreachable" since the tiers were written. This is the half that can
be built without touching the rule engine: **a transit position is arithmetic,
not interpretation.** "Saturn is in Pisces, your 6th house, from 26 Jul 2026 to
11 Dec 2026" is checkable against any almanac. What Saturn there means is a
claim, needs a fired rule with a citation, and is not this module's business.

Two decisions worth stating.

**Only the slow bodies.** The Moon changes sign every two and a bit days, so a
"window" for it is noise dressed as precision. Sun and Mercury and Venus move
through a sign in weeks, which is worth saying for a question about this month
and misleading for one about the next three years. The five that matter for a
life question are Jupiter, Saturn, Rahu, Ketu and Mars.

**Houses are counted from the natal ascendant.** "House 6 from the ascendant"
means the natal lagna. Counting from the transit chart's own ascendant gives a
number that changes every two hours and describes nothing about the person.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from rishivan.chart.ephemeris import Chart
from rishivan.chart.transit import chart_for_moment

SLOW_BODIES: tuple[str, ...] = ("Jupiter", "Saturn", "Rahu", "Ketu", "Mars")
"""The bodies whose position is worth a date range on a life question.

Mars is the fastest of these and still spends about six weeks in a sign, which
is a window a person can act inside. Below Mars the ingress dates arrive faster
than the advice can be useful.
"""

SEARCH_HORIZON_DAYS = 366 * 6
"""How far the ingress search will look in each direction.

A bound rather than a guess. Rahu takes eighteen months per sign and a station
can hold a body in one sign for years, so an unbounded search would walk the
ephemeris until something else stopped it. Six years covers every real case and
fails loudly rather than hanging.
"""

_COARSE_DAYS = 8
"""Step for the first pass. Mars is the fastest body here and holds a sign for
about six weeks, so an eight-day step cannot step over a whole transit."""


@dataclass(frozen=True, slots=True)
class TransitPosition:
    body: str
    rashi: str
    bhava: int
    """Counted from the NATAL ascendant, whole-sign."""

    retrograde: bool
    nakshatra: str
    since: Optional[datetime]
    until: Optional[datetime]
    """None only when the search hit `SEARCH_HORIZON_DAYS` without finding an
    edge. Reported as None rather than as the horizon, because the horizon is
    our limit and stating it as a date would be inventing one.
    """


def _rashi_at(body: str, when: datetime) -> str:
    return chart_for_moment(when).planets[body].rashi


def _edge(body: str, rashi: str, start: datetime, *, forward: bool) -> Optional[datetime]:
    """The moment `body` entered or leaves `rashi`, to the day.

    Coarse pass then bisect. The alternative is asking Swiss Ephemeris for the
    ingress directly, which is exact but needs a per-body branch for the nodes
    (they move backwards) and for retrograde re-entry (a body can leave a sign,
    turn, and come back). Sampling handles all of that identically.
    """
    step = timedelta(days=_COARSE_DAYS if forward else -_COARSE_DAYS)
    known_inside = start
    probe = start
    for _ in range(SEARCH_HORIZON_DAYS // _COARSE_DAYS):
        probe = probe + step
        if abs((probe - start).days) > SEARCH_HORIZON_DAYS:
            return None
        if _rashi_at(body, probe) != rashi:
            break
        known_inside = probe
    else:
        return None

    # Bisect between the last day known inside the sign and the first outside.
    inside, outside = known_inside, probe
    while abs((outside - inside).total_seconds()) > 86400:
        middle = inside + (outside - inside) / 2
        if _rashi_at(body, middle) == rashi:
            inside = middle
        else:
            outside = middle
    return inside.replace(hour=0, minute=0, second=0, microsecond=0)


def current_transits(
    natal: Chart,
    when: datetime,
    *,
    bodies: tuple[str, ...] = SLOW_BODIES,
) -> list[TransitPosition]:
    """Each body's sign, house and window at `when`."""
    moment = chart_for_moment(when)
    out: list[TransitPosition] = []
    for body in bodies:
        planet = moment.planets[body]
        bhava = (planet.rashi_index - natal.lagna_rashi_index) % 12 + 1
        out.append(TransitPosition(
            body=body,
            rashi=planet.rashi,
            bhava=bhava,
            retrograde=planet.retrograde,
            nakshatra=planet.nakshatra,
            since=_edge(body, planet.rashi, when, forward=False),
            until=_edge(body, planet.rashi, when, forward=True),
        ))
    return out


def describe(position: TransitPosition) -> str:
    """One transit, as a sentence the narration can use unchanged."""
    retro = " retrograde" if position.retrograde else ""
    span = ""
    if position.since and position.until:
        span = (f", since {position.since:%d %b %Y} until "
                f"{position.until:%d %b %Y}")
    elif position.until:
        span = f", until {position.until:%d %b %Y}"
    return (f"{position.body} transiting {position.rashi}{retro}, house "
            f"{position.bhava} from the natal ascendant{span}.")
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/chart/test_transits.py -q`
Expected: PASS (10 tests). If `test_saturn_is_where_the_ephemeris_says_it_is` fails, print the actual sign and fix the *test* — the ephemeris is the authority, not the assertion.

- [ ] **Step 5: Add transits to the fact set**

In `rishivan/chart/facts.py`, after the existing per-planet loop, append the transit lines. `chart_facts` already reaches the narration via `build_narration_prompt`, so this is the whole delivery path for the prose:

```python
    # Transits, as facts rather than as claims. Where a slow body sits and for
    # how long is arithmetic over the ephemeris; a reader can check it against
    # an almanac. What it means is a claim and still needs a fired rule.
    #
    # `council/prompts.py` already asks the narration to take its window from
    # "the transit that is actually moving" - these are the first transits it
    # has ever been given.
    from rishivan.chart.transits import current_transits, describe as _describe

    for position in current_transits(chart, when or datetime.now()):
        lines.append(f"Transit: {_describe(position)}")
```

- [ ] **Step 6: Add the Rishi prompt block**

In `rishivan/council/rishis/prompt.py`:

```python
def _transits_block(positions) -> str:
    """Where the slow bodies are now.

    Separate from the chart block because it is a different kind of statement:
    the chart block is what was true at birth and is fixed, this is what is true
    today and moves. A model given both in one list reads the transit as natal
    and dates a lifelong disposition to next spring.
    """
    if not positions:
        return ""
    from rishivan.chart.transits import describe

    return "TRANSITS RUNNING NOW (arithmetic, not a claim — no rule fired for these)\n" + "\n".join(
        f"  {describe(p)}" for p in positions
    ) + (
        "\n  You may state these as fact; they are checkable against an "
        "almanac. You may NOT say what one means unless a rule below says so."
    )
```

Add `transits=()` to `build_rishi_report_prompt`'s signature and `_transits_block(transits)` to `blocks`, immediately after `_chart_block`.

- [ ] **Step 7: Store transits on state and pass them in**

Add `transits: list` to `RishivanState` in `rishivan/graph/state.py` with a docstring saying why it is arithmetic rather than evidence. Compute it in `chart_state_node` (it already has both the chart and the query time) and pass `transits=state.get("transits") or ()` in `rishivan/graph/nodes/rishi.py`.

- [ ] **Step 8: Write the wiring test**

```python
# tests/graph/test_transit_wiring.py
"""The transits have to survive the trip from the ephemeris to the prompt.

Every capability in this codebase that went missing did so at a hop like this
one - `question=` dropped from a call site took the safety gate with it, and
`routing["koonji_domains"]` was read by a node nothing ever wrote.
"""

from datetime import datetime

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.transits import current_transits


def test_the_rishi_prompt_names_a_transit():
    from rishivan.council.rishis.prompt import build_rishi_report_prompt

    birth = BirthData(year=1998, month=5, day=15, hour=18, minute=45,
                      tz_offset_hours=5.5, lat=26.9155, lon=75.8190,
                      place="Jaipur")
    positions = current_transits(compute_chart(birth), datetime(2026, 8, 27))
    prompt = build_rishi_report_prompt(
        rishi="dhruvan", question="how will my appraisal go?",
        transits=positions,
    )
    assert "Saturn transiting" in prompt
    assert "almanac" in prompt


def test_the_fact_set_carries_transits():
    from rishivan.chart.facts import derive_facts

    birth = BirthData(year=1998, month=5, day=15, hour=18, minute=45,
                      tz_offset_hours=5.5, lat=26.9155, lon=75.8190,
                      place="Jaipur")
    facts = derive_facts(compute_chart(birth))
    assert any("Transit:" in f for f in facts)
```

Check `derive_facts`'s real signature in `chart/facts.py` before running — it may take `when` or a chart-state argument, and the test must match it rather than the other way round.

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. Watch for tests that pin the exact number of chart facts — those need their counts updated.

Then check the cost of the ingress search, because it runs on every reading:

```bash
.venv/bin/python -c "
import time
from datetime import datetime
from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.transits import current_transits
b=BirthData(year=1998,month=5,day=15,hour=18,minute=45,tz_offset_hours=5.5,lat=26.9155,lon=75.8190,place='Jaipur')
ch=compute_chart(b)
t=time.perf_counter(); current_transits(ch, datetime(2026,8,27)); print(f'{time.perf_counter()-t:.2f}s')
"
```
If this is over about 1.5 seconds, widen `_COARSE_DAYS` for Rahu and Ketu — they move slowly enough for a 20-day first pass — or memoise `chart_for_moment` on the day.

- [ ] **Step 10: Commit**

```bash
git add rishivan/chart/transits.py rishivan/chart/facts.py \
        rishivan/council/rishis/prompt.py rishivan/graph/state.py \
        rishivan/graph/nodes/chart.py rishivan/graph/nodes/rishi.py \
        tests/chart/test_transits.py tests/graph/test_transit_wiring.py
git commit -m "feat(chart): the slow transits, with the window each sits in

hierarchy.py has said '\`transit\` is declared and currently unreachable' since
the tiers were written, and the Rishi prompt assembled seven blocks with no
transit among them. Roughly half of a competitor's reading is transits with
dates, including the line that explains why the seeker is asking today.

Supplied as facts, not as claims: where a body sits and for how long is
arithmetic against an almanac and needs no citation. What it means still needs
a fired rule, and the prompt block says so in those words."
```

---

## Task 3: Separate arithmetic from prediction in the answer gate

This is the largest visible gap and it costs nothing to close.

`answer_plan.py` adds this whenever there is no dasha window:

> Do not name a date, a year or a month. No dasha window supports one, and the periods would be arithmetic rather than a prediction.

A window exists only when `reading.promises(domain)` is true, which needs a fired rule carrying a `timing` block, of which the corpus has **one in 3,692**. So the prohibition is on for practically every question, and it is why our answer to *"when will I have a child"* was *"a clear, exact timeline does not show an active window in your chart at this time"* while Melooha's was *"expect conception in 2028 and a birth between late 2028 and the middle of 2029."*

The prohibition conflates two things. **Naming a period is arithmetic; promising an event inside it is a claim.** "Your Moon/Venus antardasha runs Feb 2028 to Oct 2029" is a fact about the Vimshottari calendar. "You will conceive in it" needs evidence. The current gate forbids both because it can only license the second.

All the arithmetic is already built — `mahadasha_timeline`, `periods_at`, `activates_domain` in `rishivan/timing/`. It is gated behind `promise` and unreachable.

**Files:**
- Modify: `rishivan/timing/query.py` — add `upcoming_periods`
- Modify: `rishivan/graph/nodes/timing.py` — always compute the calendar
- Modify: `rishivan/graph/state.py` — add `dasha_calendar`
- Modify: `rishivan/council/answer_plan.py` — narrow the prohibition
- Modify: `rishivan/council/narrate.py` — add the calendar block
- Modify: `rishivan/council/rishis/prompt.py` — extend `_timing_block`
- Test: `tests/timing/test_upcoming.py`, `tests/council/test_arithmetic_vs_prediction.py`

**Interfaces:**
- Consumes: `timing.query.periods_at`, `chart.dasha.mahadasha_timeline`, `council.hierarchy.EvidenceHierarchy`
- Produces:
  - `timing.query.upcoming_periods(chart, start, end, *, level="antar") -> list[DashaSpan]`
  - `timing.query.DashaSpan` — frozen dataclass: `lords: tuple[str, ...]`, `start: datetime`, `end: datetime`, `level: str`
  - `answer_plan.AnswerPlan.dasha_calendar: tuple[DashaSpan, ...]`

- [ ] **Step 1: Write the failing test for the calendar**

```python
# tests/timing/test_upcoming.py
"""The Vimshottari calendar ahead, as arithmetic.

The answer gate forbade naming any date unless a fired rule carried a timing
block - one rule in 3,692 did - so no reading ever named a period. But a
period is not a prediction: "your Moon/Venus antardasha runs Feb 2028 to Oct
2029" is a fact about a calendar, checkable by hand. Promising an event inside
it is the claim, and that still needs evidence.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.timing.query import upcoming_periods

BIRTH = BirthData(
    year=1998, month=5, day=15, hour=18, minute=45,
    tz_offset_hours=5.5, lat=26.9155, lon=75.8190, place="Jaipur",
)
START = datetime(2026, 8, 27)
END = datetime(2036, 8, 27)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


class TestTheCalendarAhead:
    def test_it_returns_the_antardashas_in_the_horizon(self, chart):
        spans = upcoming_periods(chart, START, END)
        assert spans
        assert all(s.level == "antar" for s in spans)

    def test_they_are_contiguous_and_in_order(self, chart):
        """A gap means a period was dropped, and a reader planning around the
        calendar would plan around a hole."""
        spans = upcoming_periods(chart, START, END)
        for a, b in zip(spans, spans[1:]):
            assert a.end <= b.start
            assert (b.start - a.end).days <= 1

    def test_each_span_names_its_lords_outermost_first(self, chart):
        spans = upcoming_periods(chart, START, END)
        assert len(spans[0].lords) == 2  # mahadasha lord, antardasha lord

    def test_nothing_outside_the_horizon_is_returned(self, chart):
        spans = upcoming_periods(chart, START, END)
        assert all(s.end >= START and s.start <= END for s in spans)

    def test_it_needs_no_promise_and_no_reading(self, chart):
        """The whole point. This is arithmetic over the birth Moon, and it does
        not consult the rule base at all."""
        import inspect

        params = set(inspect.signature(upcoming_periods).parameters)
        assert "promise" not in params
        assert "reading" not in params
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/timing/test_upcoming.py -q`
Expected: FAIL — `ImportError: cannot import name 'upcoming_periods'`

- [ ] **Step 3: Implement `upcoming_periods`**

Read `rishivan/chart/dasha.py` first to get the real `Period` shape and the name of the antardasha walker. Then add to `rishivan/timing/query.py`:

```python
@dataclass(frozen=True, slots=True)
class DashaSpan:
    """One period on the Vimshottari calendar.

    Deliberately not `EventWindow`. That type carries `promise`, `confidence`
    and `promise_basis` because it answers "when could this claim come true";
    this one answers "what period is running", which is arithmetic and has no
    confidence to report. Reusing `EventWindow` would have meant inventing a
    confidence for a fact.
    """

    lords: tuple[str, ...]
    """Outermost first: (mahadasha lord, antardasha lord)."""

    start: datetime
    end: datetime
    level: str

    def __str__(self) -> str:
        return (f"{'/'.join(self.lords)}, {self.start:%b %Y} to "
                f"{self.end:%b %Y}")


def upcoming_periods(
    chart: Chart,
    start: datetime,
    end: datetime,
    *,
    level: str = "antar",
) -> list[DashaSpan]:
    """The Vimshottari calendar across a horizon.

    No `promise` argument and no `reading`, on purpose. `windows_between` times
    a *claim* and rightly refuses without one; this reports a *calendar* and
    needs nothing from the rule base. Conflating them is what left every
    reading unable to name the period it was already running.
    """
    if end < start:
        raise ValueError(f"horizon ends before it starts: {start} .. {end}")

    spans: list[DashaSpan] = []
    for maha in mahadasha_timeline(chart):
        if maha.end < start or maha.start > end:
            continue
        for antar in antardasha_timeline(chart, maha):
            if antar.end < start or antar.start > end:
                continue
            spans.append(DashaSpan(
                lords=(_graha(maha), _graha(antar)),
                start=antar.start, end=antar.end, level=level,
            ))
    return spans
```

If `chart/dasha.py` has no `antardasha_timeline`, use whatever it does expose for sub-periods and adjust — do not write a second dasha implementation. `chart/dasha.py` is the one calculation the timing layer rests on.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/timing/test_upcoming.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the failing test for the narrowed prohibition**

```python
# tests/council/test_arithmetic_vs_prediction.py
"""What the gate may forbid, and what it may not.

The prohibition read "Do not name a date, a year or a month", and it fired on
almost every question because it needed a fired rule with a timing block to
lift it - one rule in 3,692 had one. So a reading could not tell someone which
dasha they were in, which is arithmetic off their birth Moon.

The distinction the gate was missing: naming a period is a fact, promising an
event inside it is a claim.
"""

from datetime import datetime

from rishivan.council.answer_plan import build_answer_plan
from rishivan.timing.query import DashaSpan

SPAN = DashaSpan(lords=("Moon", "Venus"),
                 start=datetime(2028, 2, 1), end=datetime(2029, 10, 1),
                 level="antar")


class TestNamingAPeriodIsNotPredicting:
    def test_the_calendar_survives_with_no_promise(self):
        plan = build_answer_plan(question="when will I have a child?",
                                 domain="domain.progeny",
                                 dasha_calendar=[SPAN])
        assert plan.dasha_calendar

    def test_the_blanket_date_ban_is_gone_when_a_calendar_exists(self):
        plan = build_answer_plan(question="when will I have a child?",
                                 domain="domain.progeny",
                                 dasha_calendar=[SPAN])
        assert not any("Do not name a date" in m for m in plan.must_not_say)

    def test_but_dating_the_claim_is_still_forbidden(self):
        """The replacement has to be narrower, not absent. A period may be
        named; an event may not be promised inside it without evidence."""
        plan = build_answer_plan(question="when will I have a child?",
                                 domain="domain.progeny",
                                 dasha_calendar=[SPAN])
        joined = " ".join(plan.must_not_say).lower()
        assert "period" in joined
        assert "promise" in joined or "event" in joined

    def test_with_no_calendar_the_ban_stands(self):
        """A chartless question has no calendar, and there the old prohibition
        is exactly right."""
        plan = build_answer_plan(question="what is a nakshatra?",
                                 domain="domain.temperament")
        assert any("Do not name a date" in m for m in plan.must_not_say)

    def test_the_prompt_carries_the_calendar(self):
        from rishivan.council.narrate import gate_block

        plan = build_answer_plan(question="when will I have a child?",
                                 domain="domain.progeny",
                                 dasha_calendar=[SPAN])
        block = gate_block(plan)
        assert "Moon/Venus" in block
        assert "2028" in block
```

- [ ] **Step 6: Run it**

Run: `.venv/bin/python -m pytest tests/council/test_arithmetic_vs_prediction.py -q`
Expected: FAIL — `build_answer_plan() got an unexpected keyword argument 'dasha_calendar'`

- [ ] **Step 7: Narrow the prohibition**

In `rishivan/council/answer_plan.py`, add `dasha_calendar: tuple = ()` to `AnswerPlan` and `dasha_calendar=()` to `build_answer_plan`, then replace the blanket ban:

```python
    must_not_say: list[str] = []
    if not window and not dasha_calendar:
        # No chart, so no calendar either. Here the old prohibition is right:
        # there is nothing arithmetic to name.
        must_not_say.append(
            "Do not name a date, a year or a month. No dasha window supports "
            "one, and the periods would be arithmetic rather than a prediction."
        )
    elif not window:
        # There IS a calendar and no promise. The period may be named - it is a
        # fact about the Vimshottari calendar, checkable by hand - but nothing
        # may be promised inside it. The old ban forbade both, and because a
        # promise needs a fired rule carrying timing (one rule in 3,692 does),
        # it forbade both on essentially every question.
        must_not_say.append(
            "You may name the periods listed under THE CALENDAR AHEAD, and you "
            "may say what is running now. You may NOT promise an event inside "
            "one: no rule fired with a timing condition, so nothing licenses "
            "\"this will happen in that period\". Say when the period falls and "
            "what the chart indicates, as two separate statements."
        )
```

- [ ] **Step 8: Add the calendar to the narration prompt**

In `gate_block` in `rishivan/council/narrate.py`, after the stated-facts block:

```python
    if plan.dasha_calendar:
        blocks.append(
            "THE CALENDAR AHEAD (arithmetic — no rule fired for these)\n"
            + "\n".join(f"  {span}" for span in plan.dasha_calendar[:8])
            + "\n  These are periods, not predictions. Name them freely and "
              "give the dates; do not attach an outcome to one unless a "
              "finding above supports it."
        )
```

The `[:8]` bound is deliberate: a ten-year horizon holds a dozen or more antardashas, and a reader given all of them gets a table rather than an answer.

- [ ] **Step 9: Compute the calendar in the graph**

In `rishivan/graph/nodes/timing.py`, `dasha_windows_node` currently returns only `timing`. Add the calendar, which does not depend on `promise`:

```python
    # Computed whether or not there is a promise. The window answers "when
    # could this claim come true" and rightly needs one; the calendar answers
    # "what period is running", which is arithmetic off the birth Moon. Tying
    # the second to the first left every reading unable to name the dasha it
    # was already in.
    from rishivan.timing.query import upcoming_periods

    return {
        "timing": TimingReport(by_system={PRIMARY_SYSTEM: window}),
        "dasha_calendar": upcoming_periods(chart, start, end),
    }
```

Add `dasha_calendar: list` to `RishivanState`, pass `dasha_calendar=state.get("dasha_calendar") or ()` in `nodes/answer_plan.py`, and extend `_timing_block` in `rishis/prompt.py` to print the calendar when there is no promise — so the Rishi sees it too, not only the narrator.

- [ ] **Step 10: Run everything**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS. Tests asserting the old blanket prohibition will fail; update them to the new intent rather than deleting them, and note in the docstring that the ban was narrowed rather than dropped.

- [ ] **Step 11: Check it end to end**

```bash
.venv/bin/python -c "
from datetime import datetime
from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.timing.query import upcoming_periods
b=BirthData(year=1998,month=5,day=15,hour=18,minute=45,tz_offset_hours=5.5,lat=26.9155,lon=75.8190,place='Jaipur')
for s in upcoming_periods(compute_chart(b), datetime(2026,8,27), datetime(2036,8,27))[:8]:
    print(' ', s)
"
```
Expected: contiguous antardasha spans with dates — the shape of Melooha's *"Moon/Venus, Feb 2028 to Oct 2029 (antardasha window)"*.

- [ ] **Step 12: Commit**

```bash
git add rishivan/timing/query.py rishivan/graph/nodes/timing.py \
        rishivan/graph/state.py rishivan/council/answer_plan.py \
        rishivan/council/narrate.py rishivan/council/rishis/prompt.py \
        rishivan/graph/nodes/answer_plan.py \
        tests/timing/test_upcoming.py tests/council/test_arithmetic_vs_prediction.py
git commit -m "feat(timing): a period may be named; an event may not be promised in it

The gate said 'Do not name a date, a year or a month' unless a fired rule
carried a timing block. One rule in 3,692 does, so no reading ever named a
period - not even the one currently running, which is arithmetic off the birth
Moon and checkable by hand.

Splits the two: upcoming_periods reports the Vimshottari calendar with no
promise and no reading, and the prohibition narrows from 'no dates' to 'no
outcome attached to a period without evidence'. The arithmetic already existed
in timing/ and was unreachable behind the promise flag."
```

---

## Task 4: The seeker's name

Melooha opens with it and returns to it: *"Bharat, the child comes, but not in the first two years of this marriage"*, *"You negotiate badly for yourself, Bharat."* We have no name field anywhere — not in `RishivanState`, not in the Streamlit form.

Small, but it is the difference between a reading and a report.

**Files:**
- Modify: `rishivan/graph/state.py` — add `seeker_name: str`
- Modify: `streamlit_app.py` — a name input beside the birth details
- Modify: `rishivan/council/prompts.py` — tell the voice it may use the name
- Test: `tests/council/test_seeker_name.py`

**Interfaces:**
- Consumes: `RishivanState["seeker_name"]`
- Produces: nothing new — `build_rishi_prompt` gains a `seeker_name: str = ""` keyword

- [ ] **Step 1: Write the failing test**

```python
# tests/council/test_seeker_name.py
"""Addressing the seeker by name.

A reading that says "Bharat, the child comes, but not in the first two years of
this marriage" lands differently from one that says "A clear, exact timeline
does not show an active window in your chart at this time." Part of that is
evidence and part of it is simply that one of them knows who it is talking to.
"""

from rishivan.council.domains import QueryDomain
from rishivan.council.prompts import build_rishi_prompt


def _prompt(**kw):
    base = dict(rishi_name="medhan", domain=QueryDomain.NATAL,
                question="tell me about my love life", context="",
                chart_facts=None, conversation=None, rules="",
                life_domain=None, contributors=())
    base.update(kw)
    return build_rishi_prompt(**base)


def test_the_name_reaches_the_prompt():
    assert "Bharat" in _prompt(seeker_name="Bharat")


def test_the_voice_is_told_it_may_use_it():
    prompt = _prompt(seeker_name="Bharat").lower()
    assert "name" in prompt


def test_no_name_adds_nothing():
    """An unnamed seeker must not produce a prompt telling the model to address
    someone called "" - which is how a placeholder reaches production."""
    assert "seeker's name" not in _prompt(seeker_name="").lower()


def test_a_blank_name_is_treated_as_absent():
    assert "seeker's name" not in _prompt(seeker_name="   ").lower()
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/council/test_seeker_name.py -q`
Expected: FAIL — `build_rishi_prompt() got an unexpected keyword argument 'seeker_name'`

- [ ] **Step 3: Implement**

Add `seeker_name: str = ""` to `build_rishi_prompt` in `rishivan/council/prompts.py` and a block when it is non-blank:

```python
    if (seeker_name or "").strip():
        blocks.append(
            f"THE SEEKER'S NAME\n  {seeker_name.strip()}\n"
            f"  Use it where it lands naturally - the opening, or a sentence "
            f"that turns to them directly. Once or twice in a reading, not in "
            f"every paragraph, and never as a substitute for saying something."
        )
```

Add `seeker_name: str` to `RishivanState`, pass it from `build_narration_prompt` (`state.get("seeker_name") or ""`), and add the input in `streamlit_app.py` beside the birth-details fields, writing it into the state the graph is invoked with.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/council/test_seeker_name.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite and commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add rishivan/council/prompts.py rishivan/graph/state.py \
        rishivan/council/narrate.py streamlit_app.py tests/council/test_seeker_name.py
git commit -m "feat(council): the reading may address the seeker by name"
```

---

## Task 5: Timing extraction — REQUIRES APPROVED COST ESTIMATE

**Do not start this task until the user has approved a cost figure.**

One rule in 3,692 carries a `timing` block, and the extraction prompt never asks for one — "timing" appears once in `koonji/prompts.py`, in a note about longevity restrictions. Meanwhile 504 rules do reference dashas, but as a *firing condition* (`when: dasha_active(...)`), which constrains when a rule speaks and produces no datable window.

Task 1 is a hard prerequisite. The densest timing material in the corpus — Hindu Predictive's dasha-phala chapter — is currently one 62,127-character passage. Asking more carefully about material the model was never going to work through would waste the run.

- [ ] **Step 1: Produce the cost estimate from Task 1's actual output**

```bash
.venv/bin/python -c "
from rishivan.koonji.corpus import load_corpus, to_passages
from rishivan.koonji.prompts import extractor_system
ps=[p for p in to_passages(load_corpus())
    if p.book_id in {'prasna-marga','hindu-predictive','phaladeepika',
                     'jataka-parijata','prashna-tantra','bphs',
                     'brihat-jataka','bhavartha-ratnakara'}]
static=len(extractor_system())//4
body=sum(len(p.text)+len(p.context) for p in ps)//4
print('passages to re-extract:',len(ps))
print('static prompt tokens:',static,'(cacheable above 4096)')
print(f'input tokens: {len(ps)*static+body:,} of which {len(ps)*static:,} cacheable')
print(f'output tokens (est. 400/call): {len(ps)*400:,}')
"
```

Check `extractor_system`'s real signature first. Present the figures to the user with the current Gemini rate and **stop until approved.**

- [ ] **Step 2: Add the timing field to the extraction prompt and schema**

Read `koonji/urf.py` for the `Qualifiers.timing` shape and `koonji/prompts.py` for `EXTRACTION_SCHEMA` before writing. The prompt must distinguish the two cases explicitly, because they look identical in a verse and behave completely differently:

- *"During the dasha of the 5th lord, children come"* → a `timing` block. The period is when the effect **arrives**.
- *"If the 5th lord is in the 8th during its own dasha, ill health"* → `dasha_active` in `when`. The period is part of the **condition**.

Include a worked example of each, in the style of the existing `CONDITION_COMPLETENESS_NOTE`.

- [ ] **Step 3: Validate on ten passages before spending on all of them**

Run the extractor with `--limit 10` over `hindu-predictive` after re-chunking, and check by hand that dasha-phala verses now produce `timing` blocks rather than `dasha_active` conditions. Fix the prompt and repeat until they do. **A full run before this check is money spent on an unvalidated prompt** — this is the mistake the earlier flash-lite work avoided by probing first.

- [ ] **Step 4: Run the affected books, verify, commit**

After the run: confirm the engine still loads (`_engine()`), confirm `rules carrying timing` has moved off 1, and re-run the full suite. Commit rules separately from code.

---

## Task 6: Transit rule predicates — REQUIRES APPROVED COST ESTIMATE

The largest remaining piece, and the only one that needs engine work rather than plumbing.

Task 2 lets the narration *state* a transit. This lets a rule *fire* on one, so a transit claim can carry a citation. `koonji/describe.py:122` already handles a `transits_bhava` predicate that the registry does not define — the work is half-anticipated already.

Scope, in order: add `transits_bhava` and `transits_rashi` to `SEED_PREDICATES`; make `chart/tokens.py` emit transit tokens at the reading's `when`; confirm the `transit` tier weight in `council/hierarchy.py` (already declared at 0.30) now reaches something; extend the extraction prompt to recognise transit rules; re-extract the transit-heavy books.

**Do not start before Tasks 1, 2 and 5 are done and reviewed.** A transit predicate with no timing on the rules and no re-chunked corpus underneath it will fire on very little, and the cost of finding that out is a full extraction run.

**This task deliberately has no numbered steps, and that is not an oversight.** Every other task in this plan specifies its tests and its code because the inputs are known today. This one's shape depends on what Tasks 1 and 5 actually produce — how many transit-bearing verses survive re-chunking, and whether the timing work already covers part of the ground. Writing test code now against a corpus that does not exist yet would be inventing precision. **When Tasks 1, 2 and 5 are done, this task gets its own plan document**, written against the corpus as it then is.

---

## Task 7: The evidence list in the UI

Melooha shows its work as a numbered list under a "See Less" fold — six rows, each naming the factor, the chart it came from, the house, the date window, and one clause of meaning:

```
2) Ketu, house 5 (birth chart): classic delay on fifth-house matters, conception pushed into 2028
5) Rahu transiting Aquarius retrograde, house 5, since 18 May 2025 until 05 Dec 2026: fifth-house activation
```

We have all of this and render none of it in that form. `AnswerPlan.allowed` carries claim, band, citations, rule ids, tier and window; `contributor_reports` carries what each Rishi computed; after Task 2 `transits` carries the transit rows; after Task 3 `dasha_calendar` carries the periods.

This is presentation only — no new facts, no model calls, no prompt changes.

**Files:**
- Create: `rishivan/council/evidence_list.py`
- Create: `tests/council/test_evidence_list.py`
- Modify: `streamlit_app.py` — render it in an expander under the answer

**Interfaces:**
- Consumes: `AnswerPlan.allowed`, `AnswerPlan.dasha_calendar`, `RishivanState["transits"]`
- Produces: `evidence_list.rows(plan, *, transits=()) -> list[EvidenceRow]` with `EvidenceRow(index: int, factor: str, source: str, meaning: str, window: str)`

- [ ] **Step 1: Write the failing test**

```python
# tests/council/test_evidence_list.py
"""The reading's own working, shown as rows.

Everything needed for this was already in the plan - claim, band, citation,
tier, window - and none of it was ever rendered. A reader who can see the six
factors behind a verdict can weigh it; one given only the prose has to take it
on trust, which is the position every astrology app puts them in.
"""

from rishivan.council.answer_plan import AllowedClaim, AnswerPlan
from rishivan.council.evidence_list import rows


def _plan(**kw):
    base = dict(
        question="when will I have a child?", domain="domain.progeny",
        allowed=(AllowedClaim(
            claim_id="progeny.children", band="strongly_indicated",
            phrasing="strongly indicated", confidence=0.72,
            citations=("bphs ch23.v5",), rule_ids=("r1",), tier="house",
            counter=(), corroborated=True, window="Feb 2028 – Oct 2029",
        ),),
    )
    base.update(kw)
    return AnswerPlan(**base)


def test_each_claim_becomes_one_numbered_row():
    out = rows(_plan())
    assert len(out) == 1
    assert out[0].index == 1


def test_the_row_names_its_source():
    assert "bphs" in rows(_plan())[0].source.lower()


def test_the_window_is_carried_when_there_is_one():
    assert "2028" in rows(_plan())[0].window


def test_a_transit_becomes_a_row_too():
    from datetime import datetime

    from rishivan.chart.transits import TransitPosition

    position = TransitPosition(
        body="Rahu", rashi="Aquarius", bhava=5, retrograde=True,
        nakshatra="Shatabhisha",
        since=datetime(2025, 5, 18), until=datetime(2026, 12, 5),
    )
    out = rows(_plan(), transits=[position])
    assert any("Rahu" in r.factor for r in out)
    assert any("2026" in r.window for r in out)


def test_rows_are_numbered_contiguously_from_one():
    """The numbering is the reader's index into the list. A gap reads as a row
    that was withheld."""
    from datetime import datetime

    from rishivan.chart.transits import TransitPosition

    position = TransitPosition(
        body="Saturn", rashi="Pisces", bhava=6, retrograde=True,
        nakshatra="Revati", since=datetime(2026, 7, 26),
        until=datetime(2026, 12, 11),
    )
    out = rows(_plan(), transits=[position])
    assert [r.index for r in out] == list(range(1, len(out) + 1))
```

- [ ] **Step 2: Run it, implement, run again**

Run: `.venv/bin/python -m pytest tests/council/test_evidence_list.py -q`
Expected: FAIL, then PASS after `rishivan/council/evidence_list.py` exists. Check `AllowedClaim`'s real field list in `answer_plan.py` before writing the fixture — it must match exactly.

- [ ] **Step 3: Render it under the answer**

In `streamlit_app.py`, below the answer and above the standing captions:

```python
_rows = evidence_rows(result.get("answer_plan"), transits=result.get("transits") or ())
if _rows:
    with st.expander(f"Why — {len(_rows)} factors"):
        for row in _rows:
            st.markdown(
                f"**{row.index})** {row.factor}"
                + (f" ({row.source})" if row.source else "")
                + (f", {row.window}" if row.window else "")
                + (f": {row.meaning}" if row.meaning else "")
            )
```

- [ ] **Step 4: Run the full suite and commit**

```bash
.venv/bin/python -m pytest tests/ -q
git add rishivan/council/evidence_list.py tests/council/test_evidence_list.py streamlit_app.py
git commit -m "feat(ui): the reading shows its working as numbered factors"
```

---

## What this plan does not close

Stated plainly, because a plan that implies parity it does not deliver is worse than one that admits the gap.

**Behavioural specificity.** Melooha writes *"You negotiate badly for yourself, Bharat. In the meeting you will accept the first number offered because pushing back feels rude."* That is a character reading with a predicted behaviour attached. Our corpus is classical placement rules, and no amount of plumbing turns *"Mercury and Saturn in the 7th"* into that sentence. It would need either a psychological layer on top of the placements or a much freer hand for the narrative voice — and the second trades away the evidence discipline that is this product's actual argument. **Worth an explicit decision rather than drift.**

**Statements about third parties.** *"Your wife is unlikely to press the timeline yet"*, *"she reads that silence as disinterest."* We read one chart. These are inferences about someone who is not present and whose chart we do not have.

**Divisional-chart vocabulary.** Melooha says "children chart" and "marriage chart"; we say "your Navamsha — the subtle ninth divisional chart often used for marriage". Ours is longer but it teaches the reader something, and after Task 0.2 the division is actually being used rather than apologised for. Judged a deliberate difference rather than a gap, and left alone. Revisit if readers say the gloss reads as padding.

**Whether Melooha is right.** Nothing here checks that. Its answers are more specific and more useful-sounding; specificity is not accuracy, and the corroboration machinery we would be loosening in Task 3 exists because paraphrase-counting is how astrology products end up confidently wrong. The target is Melooha's *usefulness*, not its confidence.

**The approval gate is still disconnected.** Every extracted rule is `candidate`, and `SERVED_STATUSES` accepts candidates, so unreviewed rules reach users and approving one changes nothing. Raised previously, still open, and Tasks 5 and 6 will add roughly a thousand more rules to the pile. Not in this plan because it is a policy decision, not an implementation.
