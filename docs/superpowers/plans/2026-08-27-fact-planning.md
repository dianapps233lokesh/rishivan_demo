# Question-Scoped Facts, One Framed Table

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** Stop the direct lane handing the model sixty facts in five shapes, and start handing it the facts the question actually needs, in one shape it cannot misread.

**Architecture:** A deterministic `QuestionProfile` (keyword tables, no model call) decides what kind of question this is, which date it is about, and which fact bundles it requires — on top of a floor the constitution guarantees. `build_direct_prompt` renders only the planned bundles, and every planetary position goes into ONE table with a `FRAME` column so natal and transit can never fuse. Two new computations, tara bala and chandra bala, plus panchang for the date the question is about, make date-specific questions answerable at all.

**Tech Stack:** Python 3.14, pytest, Swiss Ephemeris via `pyswisseph`.

**Spec:** `docs/superpowers/specs/2026-08-27-direct-call-reading-design.md` (see the revisions section; this plan is revision 5).

## Why

Two failures, both proven rather than suspected.

**The chart was fabricated.** Asked "Can I travel foreign tomorrow?", the reading named
Saturn in Pisces, Venus in Virgo, Mercury in Leo, Moon conjunct Rahu in Aquarius, Jupiter
in Cancer. All five are the *transit* positions for 2026-08-28. A natal chart matching
today's sky on five planets would mean the seeker was born that day. **Not one natal
placement was used**, and the natal condition flags — "combust", "aspected by Mars and
Saturn", straight out of `PLANETARY CONDITION` — were grafted onto transiting bodies.

The cause is shape, not disobedience. Five blocks carry planetary positions
(`CHART FRAMEWORK`, `PRIMARY EVIDENCE`, `WIDER CHART`, `PLANETARY CONDITION`,
`TRANSITS NOW`), and exactly one of them pairs *planet + sign + which house of yours* on a
single line — the transit block. `PLANETARY CONDITION` carries dignity with no sign and no
house, so it can only be used by re-joining across blocks on planet name. The most usable
shape won. The prompt already said that block was authoritative and not to be re-derived;
it lost to a cleaner line four hundred characters away.

**The question was not answered.** "Tomorrow" is a muhurta question. It needs tomorrow's
panchang, tara bala, chandra bala, Rahu Kaal. We computed none of them and sent a natal
chart, today's transits, and dasha boundaries to 2060 — so the reading answered the
question it had facts for ("late 2026 or early 2027") rather than the one asked.
`relative_day_offset()` and `compute_panchang(day, ...)` already existed and were never
called in this lane.

## Global Constraints

- **No new model calls.** The planner is keyword tables, matching `hierarchy_node` and
  `koonji.router` — "a table a reviewer can read and correct".
- **The floor is deterministic and cannot be dropped.** A model or table that forgets the
  7th lord on a marriage question produces a confidently incomplete reading and nothing
  downstream can detect it.
- **The retrieval lane does not change.** `tests/graph/test_parity.py` and
  `test_adapter.py` green at every commit.
- **Run tests with** `./.venv/bin/python -m pytest`.
- **Fixed test chart**, every task:
  ```python
  BIRTH = BirthData(year=1990, month=1, day=1, hour=12, minute=0,
                    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi")
  WHEN = datetime(2026, 8, 25, 12, 0)
  ```

---

### Task 1: One framed table

The single change that would have prevented the fabrication on its own. Replaces
`scoped_chart` and `_condition_block` with one table whose first column is the frame.

**Files:** Create `rishivan/council/fact_table.py`; Test `tests/council/test_fact_table.py`

**Produces:**
- `PlanetRow` dataclass: `frame, planet, sign, house, dignity, strength, flags, aspects, nakshatra`
- `natal_rows(chart, chart_state) -> list[PlanetRow]`
- `transit_rows(chart, transiting) -> list[PlanetRow]`
- `render_table(rows, *, primary: set[str]) -> str`

Key decisions:
- **Frame is a column, never a heading.** `natal` / `transit` / `D9` / `D10`.
- **Every row is complete.** Sign AND house AND dignity AND strength on one line, so no
  cross-block join exists to get wrong.
- **Relevance is a marker, not a section.** A `*` prefix on rows the question's domain
  owns, so demoting does not mean relocating — the wider chart stays in one table.
- Transit rows carry no dignity or strength: those are natal judgements and printing them
  beside a transit sign is exactly the fusion this task removes.

- [ ] **Step 1: failing test** — assert one table, `FRAME` header present, a natal Saturn
  row and a transit Saturn row both present and distinguishable, transit rows have no
  dignity column value, primary rows marked, no per-frame headings.
- [ ] **Step 2: run, confirm ImportError**
- [ ] **Step 3: implement**
- [ ] **Step 4: run, confirm pass**
- [ ] **Step 5: commit** `feat(direct): one table, frame as a column`

---

### Task 2: Tara bala and chandra bala

The two computations `facts.py:138` records as missing. Both are index arithmetic.

**Files:** Create `rishivan/chart/bala.py`; Test `tests/chart/test_bala.py`

**Produces:**
- `tara_bala(natal_moon_nakshatra: str, transit_moon_nakshatra: str) -> TaraBala`
  with `number` (1-9), `name`, `is_favourable`
- `chandra_bala(natal_moon_rashi: str, transit_moon_rashi: str) -> ChandraBala`
  with `house` (1-12), `is_favourable`

The nine taras from the birth nakshatra, counting the birth nakshatra as 1:
Janma(1) unfavourable, Sampat(2) favourable, Vipat(3) unfavourable, Kshema(4) favourable,
Pratyari(5) unfavourable, Sadhaka(6) favourable, Vadha(7) unfavourable, Mitra(8)
favourable, Ati-Mitra(9) favourable.

Chandra bala: transiting Moon in houses 1, 3, 6, 7, 10, 11 from the natal Moon is
favourable for undertaking something; 4, 8, 12 are not.

- [ ] **Step 1: failing test** — same nakshatra gives Janma/1/unfavourable; +1 gives
  Sampat/2/favourable; wraps at 27; all nine names reachable; chandra bala 1/3/6/7/10/11
  favourable and 4/8/12 not.
- [ ] **Step 2-4: run, implement, run**
- [ ] **Step 5: commit** `feat(chart): tara bala and chandra bala`

---

### Task 3: The question profile

**Files:** Create `rishivan/council/question_profile.py`; Test `tests/council/test_question_profile.py`

**Produces:**
- `QuestionKind` enum: `WHEN_WILL`, `OK_ON_DATE`, `WHAT_IS_IT_LIKE`, `WHICH_OPTION`
- `Bundle` enum, the closed menu: `NATAL_PLACEMENTS`, `HOUSE_LORDS`, `CONJUNCTIONS`,
  `YOGAS`, `PLANET_CONDITION`, `DASHA_CURRENT`, `DASHA_FORWARD`, `TRANSITS_SLOW`,
  `SADE_SATI`, `PANCHANG_FOR_DATE`, `TARA_BALA`, `CHANDRA_BALA`, `VARGAS`,
  `ASHTAKAVARGA`, `NUMEROLOGY`
- `QuestionProfile` dataclass: `kind`, `day_offset`, `bundles: frozenset[Bundle]`,
  `unavailable: tuple[str, ...]`, `reason: str`
- `profile_for(question: str, *, koonji_domain: str) -> QuestionProfile`

Key decisions:
- `day_offset` comes from `panchang.relative_day_offset` — already written, already
  handles Hindi and "day after tomorrow".
- `kind` from a keyword table, longest phrase first, defaulting to `WHAT_IS_IT_LIKE`.
  "when will", "kab" → WHEN_WILL. "can i", "should i", "is it good", plus a day word →
  OK_ON_DATE. "or" between two options → WHICH_OPTION.
- **FLOOR** — always present regardless of kind: `NATAL_PLACEMENTS`, `HOUSE_LORDS`,
  `PLANET_CONDITION`, `DASHA_CURRENT`. The reading cannot be right without them and a
  table that can drop them is a table that will.
- Per kind, on top of the floor:
  - `WHEN_WILL` → `DASHA_FORWARD`, `TRANSITS_SLOW`, `SADE_SATI`, `YOGAS`, `VARGAS`
  - `OK_ON_DATE` → `PANCHANG_FOR_DATE`, `TARA_BALA`, `CHANDRA_BALA`, `TRANSITS_SLOW`
  - `WHAT_IS_IT_LIKE` → `YOGAS`, `CONJUNCTIONS`, `VARGAS`  (**no transits, no dasha
    forward** — a character question timed against a transit is how a temperament reading
    becomes a forecast nobody asked for)
  - `WHICH_OPTION` → `PANCHANG_FOR_DATE`, `TRANSITS_SLOW`
- `unavailable` names what this question wanted and cannot have — Jaimini karakas, a D9 at
  hour-precision birth time. Declared so the prompt can say so rather than let the model
  substitute.

- [ ] **Step 1: failing test** — "when will I marry" → WHEN_WILL, no PANCHANG;
  "can I travel foreign tomorrow" → OK_ON_DATE, day_offset 1, PANCHANG + TARA + CHANDRA;
  "what is my personality like" → WHAT_IS_IT_LIKE, no TRANSITS_SLOW, no DASHA_FORWARD;
  the floor present in all four kinds; unknown question defaults to WHAT_IS_IT_LIKE.
- [ ] **Step 2-4: run, implement, run**
- [ ] **Step 5: commit** `feat(council): a question profile decides which facts a question needs`

---

### Task 4: Assemble from the profile

**Files:** Modify `rishivan/council/direct_prompt.py`, `scripts/direct_prompt.py`;
Test `tests/council/test_direct_prompt.py`

- `build_direct_prompt` builds a `QuestionProfile`, renders the one framed table, and
  emits only the planned bundles.
- `PANCHANG_FOR_DATE` calls `compute_panchang(query_time.date() + day_offset)` and prints
  `Panchang.summary()` — exact clock times, which the granularity rule already exempts.
- An `EVIDENCE NOT AVAILABLE` block lists `profile.unavailable`, so a gap is declared once
  rather than discovered per step.
- Delete `scoped_chart` and `_condition_block` and their tests; the table replaces both.
- `scripts/direct_prompt.py` keeps working with no signature change.

- [ ] **Step 1: failing test** — a tomorrow question's prompt contains "Rahu Kaal" and the
  tomorrow date; a character question's prompt contains no `TRANSITS NOW`; the prompt
  contains exactly one planetary table; fact count is materially lower than the old
  prompt for a character question.
- [ ] **Step 2-4: run, implement, run**
- [ ] **Step 5: regenerate goldens, read one prompt of each kind by hand**
- [ ] **Step 6: commit** `feat(direct): the prompt carries what the question needs`

---

## Verification

```bash
./.venv/bin/python -m pytest tests/ -q
./.venv/bin/python -m pytest tests/graph/test_parity.py tests/graph/test_adapter.py -v
for q in "when will I marry?" "can I travel foreign tomorrow?" "what is my personality like?"; do
  ./.venv/bin/python -m scripts.direct_prompt --question "$q" \
    --dob 1990-01-01 --tob 12:00 --place "New Delhi" --lat 28.6139 --lon 77.2090 \
    --when 2026-08-27 | head -5
done
```

The three prompts must differ in which blocks they carry. If they do not, the profile is
wired but inert — which is the failure mode this plan exists to remove, arriving one layer
further in.

## Not in this plan

**Approach B.** Once the profile is emitted, it becomes the contract a critic can check:
did the reading use every bundle it was given, and nothing it was not? "Venus debilitated
in Virgo" fails that check instantly, because no transit-Venus fact was ever planned. B is
worth building after this, and was not worth building before it — a critic reading the same
five fused blocks would have confirmed the fabricated chart rather than caught it.
