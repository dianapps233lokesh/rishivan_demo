# Direct-Call Reading Lane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second reading lane that sends the classical *method* plus a question-scoped computed chart to one model call, instead of retrieving book passages and matched rules — and prints the assembled prompt to console so the same prompt can be pasted into ChatGPT, Gemini and Claude for comparison.

**Architecture:** A new pure prompt builder (`council/direct_prompt.py`) turns the per-domain `protocol` tuples already in `council/constitution.py` into a numbered reading procedure, and sorts `chart_facts` into four labelled blocks scoped to the routed domain. A new node (`graph/nodes/direct.py`) writes that prompt to state; `graph/build.py` gains a `direct=True` mode that swaps two edge tables so the routers themselves never change; `council/direct.py` makes the one streaming call and prints the prompt. Nothing is deleted — the retrieval lane keeps working, because the whole point is to compare them.

**Tech Stack:** Python 3.14, LangGraph, `google-genai` (Vertex), pytest, Streamlit, Swiss Ephemeris via `pyswisseph`.

**Spec:** `docs/superpowers/specs/2026-08-27-direct-call-reading-design.md`

## Global Constraints

- **Model:** `gemini-3.7-flash` via `model_name("flash")`. Do not change `client.MODELS`.
- **Generation config:** `temperature=0.0`, `thinking_config=types.ThinkingConfig(thinking_budget=-1)`. Verify `-1` is accepted by the installed SDK (Task 6, Step 2); the only in-repo precedent is `thinking_budget=0` in `knowledge/extract/runner.py:342`.
- **No persona in this lane.** Do not import `get_persona`, `RishiPersona`, `_build_system`, or `_CORE_RULES` into any new module. The Rishi voice returns in a later phase.
- **Delete nothing.** No edits that remove behaviour from `rishivan/rag/`, `rishivan/koonji/`, `rishivan/knowledge/`, `council/prompts.py`, `council/narrate.py`, or `council/answer_plan.py`.
- **`coverage_facts()` in `council/prompts.py` must not be modified.** The retrieval lane depends on its exact output. New scoping goes in a new function.
- **Default behaviour is unchanged.** `council_consult(...)` without `direct=True` must behave exactly as today. `tests/graph/test_parity.py` and `tests/graph/test_adapter.py` must stay green at every commit.
- **Every key a node returns must be declared in `RishivanState`.** LangGraph discards writes to undeclared channels silently. `tests/graph/test_integration.py` walks node modules for this.
- **No network in the prompt builder.** `build_direct_prompt` must not import or touch Qdrant, Postgres, or the model client.
- **Fixed test chart**, used in every test in this plan:
  ```python
  BIRTH = BirthData(
      year=1990, month=1, day=1, hour=12, minute=0,
      tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
  )
  WHEN = datetime(2026, 8, 25, 12, 0)
  ```
- **Run tests with the repo venv:** `./.venv/bin/python -m pytest`.

---

### Task 1: Domain resolution and the method block

The method block is the substance of this change. `constitution.protocol` holds the classical reading order per domain and until now only filtered which rules counted; here it becomes the instruction.

Note the two taxonomies. `hierarchy_node` writes `koonji_domain` as a `domain.*` symbol (`"domain.relationship"`), while `CONSTITUTIONS` is keyed by the client's life-domain keys (`"prema"`). `hierarchy.LIFE_DOMAIN_OF` is the existing bridge; use it rather than writing a second mapping.

**Files:**
- Create: `rishivan/council/direct_prompt.py`
- Test: `tests/council/test_direct_prompt.py`

**Interfaces:**
- Consumes: `rishivan.council.constitution.CONSTITUTIONS`, `rishivan.council.hierarchy.LIFE_DOMAIN_OF`
- Produces:
  - `constitution_for(koonji_domain: str) -> Constitution`
  - `framing_block(constitution: Constitution) -> str`
  - `method_block(constitution: Constitution) -> str`
  - `DEFAULT_CONSTITUTION_KEY: str = "atma"`

- [ ] **Step 1: Write the failing tests**

Create `tests/council/test_direct_prompt.py`:

```python
"""The direct lane's prompt, assembled from the constitution and nothing else.

Every test here runs with no network, no client and no database. That is the
property the lane exists to have, and `test_no_network` pins it explicitly.
"""

from rishivan.council.direct_prompt import (
    constitution_for, framing_block, method_block,
)


class TestDomainResolution:
    def test_a_relationship_question_resolves_to_prema(self):
        assert constitution_for("domain.relationship").domain == "prema"

    def test_a_career_question_resolves_to_karma(self):
        assert constitution_for("domain.career").domain == "karma"

    def test_the_first_life_domain_wins_when_a_domain_maps_to_two(self):
        """`domain.status` maps to ("karma", "vansh"). The hierarchy weights the
        first, and so does this — a question routed to two domains is primarily
        about the first."""
        assert constitution_for("domain.status").domain == "karma"

    def test_an_unknown_domain_falls_back_to_atma(self):
        """Atma's protocol is the whole-chart one, which is the right default for
        a question the router could not place. Falling back to nothing would mean
        a prompt with no method block at all."""
        assert constitution_for("domain.nonsense").domain == "atma"
        assert constitution_for("").domain == "atma"


class TestMethodBlock:
    def test_the_protocol_steps_appear_numbered_and_in_order(self):
        block = method_block(constitution_for("domain.relationship"))
        assert "1. promise" in block
        assert "4. D9 confirmation" in block
        assert block.index("1. promise") < block.index("4. D9 confirmation")

    def test_the_step_count_matches_the_constitution(self):
        c = constitution_for("domain.relationship")
        block = method_block(c)
        for index, step in enumerate(c.protocol, start=1):
            assert f"{index}. {step}" in block

    def test_the_dimension_names_what_is_being_read(self):
        assert "Love / Marriage / Relationships" in method_block(
            constitution_for("domain.relationship")
        )

    def test_an_unsupported_step_must_be_declared_not_skipped(self):
        """The failure mode is a model that quietly drops the step it has no
        facts for, which reads as a complete reading."""
        block = method_block(constitution_for("domain.career"))
        assert "unsupported" in block.lower()


class TestFramingBlock:
    def test_it_names_the_text_families_from_the_constitution(self):
        block = framing_block(constitution_for("domain.relationship"))
        assert "BPHS" in block
        assert "Phaladeepika" in block

    def test_citation_is_forbidden_outright(self):
        """The panel is gone in this lane, so a citation cannot be checked
        against anything, and an uncheckable citation is worse than none."""
        block = framing_block(constitution_for("domain.relationship"))
        assert "page number" in block.lower()
        assert "chapter" in block.lower()

    def test_forbidden_claims_are_carried_through(self):
        c = constitution_for("domain.health")
        block = framing_block(c)
        assert c.forbidden_claims  # guard: the fixture must be meaningful
        for claim in c.forbidden_claims:
            assert claim in block

    def test_it_does_not_mention_this_repos_corpus_gaps(self):
        """`unavailable_sources` and `blocked_concepts` describe gaps in THIS
        repo's corpus. A model reading from its own knowledge has no such gaps,
        and telling it about them would suppress knowledge it does have."""
        c = constitution_for("domain.temperament")
        block = framing_block(c)
        assert c.unavailable_sources  # guard
        for missing in c.unavailable_sources:
            assert f"do not have {missing}" not in block
        assert "Samudrika" not in block or "Samudrika" in ", ".join(c.source_families)

    def test_no_persona_leaks_in(self):
        block = framing_block(constitution_for("domain.relationship"))
        for word in ("Rishi", "seeker", "ancient sage", "warm"):
            assert word not in block
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rishivan.council.direct_prompt'`

- [ ] **Step 3: Write the implementation**

Create `rishivan/council/direct_prompt.py`:

```python
"""The direct lane's prompt: classical method, not classical documents.

The retrieval lane answers from twenty topically-similar pages and whatever
rules fired. This one answers from the model's own reading of the classical
literature — which is wider than this corpus and better organised — and spends
the prompt on telling it *which* part of that knowledge to reach for.

`constitution.protocol` is what makes that possible. It already holds the
classical reading order per domain, taken from Eight Rishis §4-11, and until now
it only decided which rules counted as a Rishi's evidence. Here it becomes the
procedure the model works through.

**No persona.** The Rishi voice, the seven movements and the speech example are
deliberately absent: this lane is being graded on astrological accuracy against
three other platforms, and prose quality would confound that. The voice returns
as a narration step over this same material.

Everything in this module is a pure function of state. No client, no network, no
database — which is what makes the golden-snapshot test possible and what
`test_no_network` pins.
"""

from __future__ import annotations

from rishivan.council.constitution import Constitution

DEFAULT_CONSTITUTION_KEY = "atma"
"""Where an unroutable question lands.

Atma's protocol is the whole-chart one (`chart framework → Lagna and Lagna lord
→ Sun and Moon → strength → Nakshatra → major combinations → relevant Vargas →
Jaimini → synthesis → uncertainty`), which is the correct reading order for a
question nobody could place. The alternative — no method block — is a prompt
that has given up the entire point of this lane.
"""


def constitution_for(koonji_domain: str) -> Constitution:
    """The constitution for a `domain.*` symbol.

    Two taxonomies meet here. `hierarchy_node` writes `koonji_domain` as a
    `domain.*` symbol because that is what the rule corpus is tagged with;
    `CONSTITUTIONS` is keyed by the client's eight life-domain keys because that
    is what Eight Rishis §21 names. `LIFE_DOMAIN_OF` is the existing bridge and
    is used rather than duplicated — a second mapping is a second thing to drift.

    First rather than all, matching `hierarchy_node`: a domain that maps to two
    life domains is primarily about the first.
    """
    from rishivan.council.constitution import CONSTITUTIONS
    from rishivan.council.hierarchy import LIFE_DOMAIN_OF

    keys = LIFE_DOMAIN_OF.get(koonji_domain or "", ())
    return CONSTITUTIONS[keys[0] if keys else DEFAULT_CONSTITUTION_KEY]


def framing_block(constitution: Constitution) -> str:
    """Who is answering, from what, and what they may not do.

    `source_families` is rendered rather than hardcoded so the framing tracks
    §4-11 the way the rest of the lane does.

    `unavailable_sources` and `blocked_concepts` are deliberately NOT rendered.
    They record what *this repo's corpus* lacks, which is meaningless to a model
    reading from its own knowledge — and naming them would talk it out of
    knowledge it actually has.
    """
    families = ", ".join(constitution.source_families)
    forbidden = ""
    if constitution.forbidden_claims:
        forbidden = "\n\nYou may not claim any of the following, in any form:\n" + "\n".join(
            f"  - {claim}" for claim in constitution.forbidden_claims
        )
    return f"""
You are an expert Vedic (Jyotish) astrologer working in the classical tradition.
Read the computed chart below and answer the question at the end.

Draw on the classical literature you know: {families}. Apply it from your own
knowledge of those texts.

DO NOT CITE. No page numbers, no chapter-and-verse references, no book titles in
your answer, no quoted verses, and no stock authority phrases ("the classical
texts say", "the old masters held"). You have not been given any text to quote
from, so a citation you produce cannot be checked by anyone — which makes it
worth less than no citation at all. State what the principle IS. Do not say
where you read it.

Never present a health diagnosis, a treatment, or death as a certainty. These
are traditional interpretations; keep their uncertainty intact.{forbidden}
""".strip()


def method_block(constitution: Constitution) -> str:
    """The classical reading order, as an instruction.

    The steps are `constitution.protocol` verbatim, numbered. Verbatim matters:
    they are §4-11's own words, and paraphrasing them here would make the
    instruction and the coverage gate two different methods with one name.
    """
    steps = "\n".join(
        f"  {index}. {step}"
        for index, step in enumerate(constitution.protocol, start=1)
    )
    last = len(constitution.protocol)
    return f"""
READING METHOD — {constitution.dimension}
{constitution.mission}

Work these steps, in this order:

{steps}

For each step, state the classical principle you are applying and what THIS
chart shows against it. Two sentences per step is usually enough.

Do not skip a step. If the computed facts below do not let you judge a step, say
that the step is unsupported and move to the next one — a step silently dropped
reads as a complete reading, which is the one outcome worse than an admitted gap.

Do not reach your verdict before step {last}. The order is the method: a promise
that was never established cannot be timed, and a window with no promise behind
it is arithmetic pretending to be a prediction.
""".strip()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_prompt.py -v`
Expected: PASS — 14 tests.

If `test_forbidden_claims_are_carried_through` fails on its `assert c.forbidden_claims` guard, the `aarogya` constitution has no `forbidden_claims`; switch that test to whichever constitution does (`grep -n "forbidden_claims=" rishivan/council/constitution.py`) rather than weakening the assertion.

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/direct_prompt.py tests/council/test_direct_prompt.py
git commit -m "feat(direct): the protocol tuples become the reading instruction

constitution.protocol has held the classical reading order per domain since
Phase 4 and only ever filtered which rules counted as evidence. It is a method,
and a method is exactly what a model that has already read these books needs
from us."
```

---

### Task 2: Chart facts in four labelled blocks

The failure mode to design against is dumping everything. Thirty natal facts plus six vargas plus a full mahadasha timeline plus ashtakavarga buries the 7th house for a marriage question, and burying the relevant fact is how an accurate model produces an inaccurate reading.

The spec describes three tiers. This implements **four blocks** — periods are split out of "always" into their own labelled block, because they are the only source of any date the model is permitted to write and the label has to say they are boundaries rather than predictions. That is a clarification of the spec, not a departure from it.

**Files:**
- Modify: `rishivan/council/direct_prompt.py`
- Test: `tests/council/test_direct_prompt.py`

**Interfaces:**
- Consumes: `constitution_for` (Task 1), `rishivan.council.prompts._FRAMEWORK`, `rishivan.council.prompts._SUBJECT_HOUSE`
- Produces: `scoped_chart(chart_facts: list[str], constitution: Constitution) -> str`

- [ ] **Step 1: Write the failing tests**

Append to `tests/council/test_direct_prompt.py`:

```python
from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.facts import derive_facts
from rishivan.council.direct_prompt import scoped_chart

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def facts():
    return derive_facts(compute_chart(BIRTH), when=WHEN)


def _block(text: str, heading: str) -> str:
    """The text under one heading, up to the next blank-line heading."""
    start = text.index(heading)
    rest = text[start + len(heading):]
    ends = [rest.index(h) for h in (
        "CHART FRAMEWORK", "PRIMARY EVIDENCE", "COMPUTED PERIODS", "WIDER CHART",
    ) if h in rest]
    return rest[:min(ends)] if ends else rest


class TestScopedChart:
    def test_all_four_blocks_are_present(self, facts):
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        for heading in ("CHART FRAMEWORK", "PRIMARY EVIDENCE",
                        "COMPUTED PERIODS", "WIDER CHART"):
            assert heading in text

    def test_the_lagna_and_birth_nakshatra_are_always_framework(self, facts):
        text = scoped_chart(facts, constitution_for("domain.career"))
        framework = _block(text, "CHART FRAMEWORK")
        assert "Ascendant (Lagna)" in framework
        assert "Birth nakshatra" in framework

    def test_the_luminaries_are_always_framework(self, facts):
        """Every §4-11 protocol opens on the chart framework, and no reading of
        any domain proceeds without the Sun and the Moon."""
        framework = _block(
            scoped_chart(facts, constitution_for("domain.wealth")),
            "CHART FRAMEWORK",
        )
        assert "Sun is in" in framework
        assert "Moon is in" in framework

    def test_a_marriage_question_puts_the_seventh_house_in_primary(self, facts):
        primary = _block(
            scoped_chart(facts, constitution_for("domain.relationship")),
            "PRIMARY EVIDENCE",
        )
        assert "The 7th house" in primary

    def test_a_marriage_question_puts_venus_and_jupiter_in_primary(self, facts):
        primary = _block(
            scoped_chart(facts, constitution_for("domain.relationship")),
            "PRIMARY EVIDENCE",
        )
        assert "Venus is in" in primary
        assert "Jupiter is in" in primary

    def test_a_career_question_puts_the_tenth_house_in_primary(self, facts):
        primary = _block(
            scoped_chart(facts, constitution_for("domain.career")),
            "PRIMARY EVIDENCE",
        )
        assert "The 10th house" in primary

    def test_a_career_question_leaves_an_uncovered_house_in_the_wider_chart(self, facts):
        """House 12, not house 7: `karma`'s coverage genuinely includes the 7th
        (§7 reads it for partnership in business), so asserting on 7 would prove
        nothing about whether the gate works."""
        primary = _block(
            scoped_chart(facts, constitution_for("domain.career")),
            "PRIMARY EVIDENCE",
        )
        assert "The 12th house" not in primary

    def test_the_house_a_fact_is_about_beats_the_house_a_planet_sits_in(self):
        """"Mars is in Virgo in the 7th house" is ABOUT Mars, not about the 7th.
        Filing it under house 7 is the bug `_SUBJECT_HOUSE`'s anchor exists to
        prevent, and this pins it from the direct lane's side.

        Synthetic facts, not the real chart: the real one puts these planets
        wherever the ephemeris puts them, and a test whose assertion depends on
        that is a test that passes for the wrong reason."""
        planet_in_seventh = (
            "Mars is in Virgo in the 7th house (Chitra nakshatra, pada 1)."
        )
        seventh_itself = (
            "The 7th house (marriage, spouse, partnerships) is ruled by Mars, "
            "placed in the 7th house."
        )
        text = scoped_chart(
            ["Ascendant (Lagna) is Pisces.", planet_in_seventh, seventh_itself],
            constitution_for("domain.relationship"),
        )
        primary = _block(text, "PRIMARY EVIDENCE")
        wider = _block(text, "WIDER CHART")
        # The house fact is about house 7, which prema owns.
        assert seventh_itself in primary
        # Mars is not in prema's planet set (venus, jupiter), so sitting in the
        # 7th must not promote it.
        assert planet_in_seventh in wider
        assert planet_in_seventh not in primary

    def test_the_mahadasha_timeline_lands_in_computed_periods(self, facts):
        periods = _block(
            scoped_chart(facts, constitution_for("domain.relationship")),
            "COMPUTED PERIODS",
        )
        assert "Mahadasha timeline from birth" in periods
        assert "Currently running" in periods

    def test_computed_periods_says_boundaries_not_predictions(self, facts):
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        assert "not predictions" in text.lower()

    def test_the_wider_chart_is_labelled_but_not_withheld(self, facts):
        """Every protocol ends in whole-chart synthesis, so nothing is dropped —
        it is demoted and labelled."""
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        assert "do not lead from these" in text.lower()
        wider = _block(text, "WIDER CHART")
        assert "The 3rd house" in wider

    def test_every_fact_appears_exactly_once(self, facts):
        """A fact in two blocks is a fact with two priorities."""
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        for fact in facts:
            assert text.count(fact) == 1, f"appears {text.count(fact)}x: {fact}"

    def test_no_facts_is_stated_rather_than_rendered_empty(self):
        text = scoped_chart([], constitution_for("domain.relationship"))
        assert "no chart" in text.lower()
        assert "CHART FRAMEWORK" not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_prompt.py -k Scoped -v`
Expected: FAIL — `ImportError: cannot import name 'scoped_chart'`

- [ ] **Step 3: Write the implementation**

Append to `rishivan/council/direct_prompt.py`:

```python
import re

from rishivan.council.prompts import _FRAMEWORK, _SUBJECT_HOUSE

"""`_FRAMEWORK` and `_SUBJECT_HOUSE` are imported from `prompts` rather than
copied, and the privacy is knowingly crossed. `_SUBJECT_HOUSE` encodes the
subject-versus-location distinction — "Sun is in Sagittarius in the 6th house"
is about the Sun, not about the 6th — and a second copy of that anchored regex
is a second thing that can drift away from the first. Same package, one
definition."""

_PLANET_FACT = re.compile(
    r"^(Sun|Moon|Mars|Mercury|Jupiter|Venus|Saturn|Rahu|Ketu) is in "
)
"""A per-planet placement line from `facts.derive_facts`. Anchored, so a
conjunction line naming several planets is not mistaken for one."""

_LUMINARIES = ("Sun is in", "Moon is in")
"""Framework whatever the domain. Every §4-11 protocol opens on the chart
framework, and no reading of any domain proceeds without the two lights."""

_PERIOD_PREFIXES = ("Mahadasha timeline", "Currently running")
"""The only lines carrying a date. They get their own labelled block because
every date the model is allowed to write has to be copied from one of them."""

_CONJUNCTION_HOUSE = re.compile(r"^Conjunction: .* in the (\d{1,2})(?:st|nd|rd|th) house")


def _tier(fact: str, constitution: Constitution) -> str:
    """Which block a fact belongs in. Checked in priority order.

    Framework first, so the lagna and the luminaries are never demoted by a
    domain that does not name them. Periods next, so a dated line is never
    filed as a placement.
    """
    if fact.startswith(_FRAMEWORK) or fact.startswith(_LUMINARIES):
        return "framework"
    if fact.startswith(_PERIOD_PREFIXES):
        return "periods"

    subject = _SUBJECT_HOUSE.match(fact)
    if subject is not None:
        house = int(subject.group(1))
        # The 1st house and its lord are the framework step in every protocol,
        # whether or not the domain lists house 1 in its coverage.
        if house == 1:
            return "framework"
        return "primary" if house in constitution.houses else "wider"

    planet = _PLANET_FACT.match(fact)
    if planet is not None:
        return (
            "primary"
            if planet.group(1).lower() in {p.lower() for p in constitution.planets}
            else "wider"
        )

    if fact.startswith("Yoga:"):
        # "major combinations" is a step in every protocol.
        return "primary"

    conjunction = _CONJUNCTION_HOUSE.match(fact)
    if conjunction is not None:
        return (
            "primary"
            if int(conjunction.group(1)) in constitution.houses
            else "wider"
        )

    return "wider"


_HEADINGS = (
    ("framework", "CHART FRAMEWORK — read these first, whatever the question:"),
    ("primary", None),  # filled in at render time; it names the houses
    ("periods",
     "COMPUTED PERIODS — boundaries, not predictions. Every date and clock time\n"
     "you write must be copied verbatim from these lines:"),
    ("wider",
     "WIDER CHART — real, and yours to synthesise at the end. Do not lead from these:"),
)


def scoped_chart(chart_facts: list[str], constitution: Constitution) -> str:
    """Chart facts in four labelled blocks, scoped to the question's domain.

    Nothing is withheld. Every §4-11 protocol ends in whole-chart synthesis, so
    the wider chart is demoted and labelled rather than dropped — the same
    decision `prompts.coverage_facts` made, for the same reason.
    """
    if not chart_facts:
        return "No chart was computed for this question."

    buckets: dict[str, list[str]] = {
        "framework": [], "primary": [], "periods": [], "wider": [],
    }
    for fact in chart_facts:
        buckets[_tier(fact, constitution)].append(fact)

    houses = ", ".join(str(h) for h in sorted(constitution.primary_houses))
    primary_heading = (
        f"PRIMARY EVIDENCE FOR THIS QUESTION — house {houses} is the subject; "
        "the rest is its context:"
    )

    sections = []
    for name, heading in _HEADINGS:
        facts = buckets[name]
        if not facts:
            continue
        sections.append(
            (primary_heading if name == "primary" else heading)
            + "\n"
            + "\n".join(f"  - {fact}" for fact in facts)
        )
    return "\n\n".join(sections)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_prompt.py -v`
Expected: PASS — all tests, Task 1's included.

Two tests are written to be informative if they fail. If `test_a_career_question_leaves_an_uncovered_house_in_the_wider_chart` fails, check `karma`'s `supporting_houses` — the assertion is about house 12 precisely because 7 is legitimately in coverage. If `test_the_house_a_fact_is_about_beats_the_house_a_planet_sits_in` fails, `_SUBJECT_HOUSE` is being applied unanchored somewhere.

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/direct_prompt.py tests/council/test_direct_prompt.py
git commit -m "feat(direct): the chart arrives scoped, not dumped

Thirty facts plus six vargas plus a full dasha timeline buries the 7th house on
a marriage question, and burying the relevant fact is how an accurate model
gives an inaccurate reading. Four labelled blocks: framework, the domain's own
evidence, the period boundaries every permitted date must be copied from, and
the wider chart — demoted and labelled, never withheld."
```

---

### Task 3: Assemble the whole prompt

**Files:**
- Modify: `rishivan/council/direct_prompt.py`
- Test: `tests/council/test_direct_prompt.py`
- Test: `tests/council/test_direct_prompt_golden.py`
- Modify: `tests/conftest.py` (register the `--golden-update` flag)
- Create: `tests/golden/direct_prompt_marriage.txt` (generated in Step 5)

**Interfaces:**
- Consumes: `framing_block`, `method_block`, `scoped_chart` (Tasks 1-2), `rishivan.council.prompts._GROUND_TRUTH_WARNING`, `rishivan.council.conversation.Conversation.render`, `rishivan.chart.local_varga.varga_facts`
- Produces:
  - `history_block(conversation) -> str`
  - `build_direct_prompt(state) -> str` — takes a `RishivanState` (or any mapping with the same keys), returns the complete prompt.

**Do not reuse `continuity_instruction`.** It is the retrieval lane's history
block and it carries voice instructions into its text — "you have already been
speaking with this seeker", "Do not greet them again", "End on a NEW hook, never
the same one twice". Every one of those is a persona instruction, and this lane
has no persona and does not end on a hook. `Conversation.render()` gives the
transcript without them, which is the part that is actually needed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/council/test_direct_prompt.py`:

```python
from rishivan.council.direct_prompt import build_direct_prompt
from rishivan.graph.state import initial_state


def _state(question="when will I marry?", **kw):
    s = initial_state(question, query_time=WHEN)
    s["koonji_domain"] = kw.pop("koonji_domain", "domain.relationship")
    s.update(kw)
    return s


class TestBuildDirectPrompt:
    def test_the_blocks_appear_in_order(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        order = [
            "expert Vedic (Jyotish) astrologer",
            "READING METHOD",
            "CHART FRAMEWORK",
            "OUTPUT",
            "THE QUESTION",
        ]
        positions = [prompt.index(marker) for marker in order]
        assert positions == sorted(positions), prompt[:400]

    def test_the_question_is_last_and_present(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert prompt.rstrip().endswith("when will I marry?")

    def test_the_ground_truth_warning_is_reused_verbatim(self, facts):
        """It is the one instruction in the existing prompt that exists because
        the model got it wrong in production. None of its reasons changed."""
        from rishivan.council.prompts import _GROUND_TRUTH_WARNING
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert _GROUND_TRUTH_WARNING in prompt

    def test_the_output_shape_asks_for_the_falsifier(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "falsif" in prompt.lower()

    def test_the_output_shape_asks_for_confidence(self, facts):
        assert "confidence" in build_direct_prompt(
            _state(chart_facts=facts)
        ).lower()

    def test_a_chartless_question_still_builds_a_prompt(self):
        prompt = build_direct_prompt(_state("what is a nakshatra?", chart_facts=None))
        assert "READING METHOD" in prompt
        assert "No chart was computed" in prompt

    def test_selected_vargas_are_rendered_with_their_placements(self, facts):
        """A varga CODE tells the model nothing. `varga_facts` gives the actual
        divisional placements, which is what a D9 confirmation step needs."""
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection

        chart = compute_chart(BIRTH)
        prompt = build_direct_prompt(_state(
            chart_facts=facts,
            chart=chart,
            vargas=VargaSelection(
                selected=("D9",), withheld=(),
                confidence=BirthConfidence.MINUTE,
            ),
        ))
        assert "(D9)" in prompt
        assert "Ascendant is" in prompt

    def test_withheld_vargas_are_stated_not_silent(self, facts):
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection, WithheldVarga

        withheld = WithheldVarga(
            code="D60", required=BirthConfidence.SECOND,
            actual=BirthConfidence.HOUR, reason="birth time recorded to the hour",
        )
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart=compute_chart(BIRTH),
            vargas=VargaSelection(
                selected=("D9",), withheld=(withheld,),
                confidence=BirthConfidence.HOUR,
            ),
        ))
        assert "D60" in prompt
        assert "not used" in prompt.lower()

    def test_conversation_history_is_included_when_present(self, facts):
        """Dropping it would make every follow-up answer as though asked cold,
        and the comparison would read that as a grounding failure."""
        from rishivan.council.conversation import Conversation

        conversation = Conversation()
        conversation.add("will I marry?", "Marriage is close.", rishi="medhan")
        prompt = build_direct_prompt(_state(
            "tell me more", chart_facts=facts, conversation=conversation,
        ))
        assert "Marriage is close." in prompt

    def test_no_history_block_on_a_first_turn(self, facts):
        assert "EARLIER IN THIS CONVERSATION" not in build_direct_prompt(
            _state(chart_facts=facts)
        )

    def test_the_history_block_carries_no_voice_instructions(self, facts):
        """`continuity_instruction` — the retrieval lane's version — ends with
        "End on a NEW hook, never the same one twice", which is a persona
        instruction. This lane has no persona and does not end on a hook."""
        from rishivan.council.conversation import Conversation

        conversation = Conversation()
        conversation.add("will I marry?", "Marriage is close.", rishi="medhan")
        prompt = build_direct_prompt(_state(
            "tell me more", chart_facts=facts, conversation=conversation,
        ))
        assert "hook" not in prompt.lower()
        assert "greet" not in prompt.lower()

    def test_no_persona_language_anywhere(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        for banned in ("Rishi", "seeker asks", "seven movements", "sign-off"):
            assert banned not in prompt

    def test_it_is_deterministic(self, facts):
        state = _state(chart_facts=facts)
        assert build_direct_prompt(state) == build_direct_prompt(state)


def test_no_network(monkeypatch, facts):
    """The proof the retrieval dependency is gone.

    Any stray import of the vector store or the database raises here rather than
    quietly working in a dev environment that happens to have credentials. This
    is the only test that would catch a re-introduction.
    """
    import builtins

    real_import = builtins.__import__
    forbidden = ("qdrant_client", "sqlalchemy", "psycopg", "google.genai")

    def guarded(name, *args, **kwargs):
        if any(name == f or name.startswith(f + ".") for f in forbidden):
            raise AssertionError(f"direct prompt assembly imported {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    prompt = build_direct_prompt(_state(chart_facts=facts))
    assert "READING METHOD" in prompt
```

Add to `tests/conftest.py` (a `pytest_addoption` hook is only honoured in
`conftest.py` or a registered plugin — in a test module it is silently ignored,
and `getoption` then raises `ValueError: no option named`):

```python
def pytest_addoption(parser):
    parser.addoption(
        "--golden-update", action="store_true", default=False,
        help="rewrite golden files instead of asserting against them",
    )
```

Create `tests/council/test_direct_prompt_golden.py`:

```python
"""The assembled prompt, pinned.

The prompt wording will be iterated on — that is the point of the experiment.
This is what makes an iteration visible instead of silent: a diff here is either
the change you meant or the one you did not.

Regenerate deliberately, never reflexively:

    ./.venv/bin/python -m pytest tests/council/test_direct_prompt_golden.py \
        --golden-update
"""

from datetime import datetime
from pathlib import Path

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.facts import derive_facts
from rishivan.council.direct_prompt import build_direct_prompt
from rishivan.graph.state import initial_state

GOLDEN = Path(__file__).parent.parent / "golden" / "direct_prompt_marriage.txt"

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture
def prompt():
    state = initial_state("when will I marry?", query_time=WHEN)
    state["koonji_domain"] = "domain.relationship"
    state["chart"] = compute_chart(BIRTH)
    state["chart_facts"] = derive_facts(state["chart"], when=WHEN)
    return build_direct_prompt(state)


def test_the_prompt_matches_the_golden_file(prompt, request):
    if request.config.getoption("--golden-update"):
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(prompt)
        pytest.skip(f"golden file rewritten: {GOLDEN}")
    assert GOLDEN.exists(), (
        f"{GOLDEN} missing — generate it with --golden-update"
    )
    assert prompt == GOLDEN.read_text()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_prompt.py -k Build -v`
Expected: FAIL — `ImportError: cannot import name 'build_direct_prompt'`

- [ ] **Step 3: Write the implementation**

Append to `rishivan/council/direct_prompt.py`:

```python
_OUTPUT_BLOCK = """
OUTPUT — write in this order, as plain analytical prose:

  1. The method steps, worked through in order. One short paragraph each,
     naming the principle and what this chart shows against it.
  2. THE ANSWER to the question actually asked, stated plainly and without
     hedging it into meaninglessness.
  3. Your confidence, and what it rests on. If two indications disagree, say
     so — a disagreement reported is worth more than a verdict averaged.
  4. The timing. Use ONLY dates and periods that appear verbatim in the
     COMPUTED PERIODS block. If nothing there supports a window, say that
     instead of estimating one.
  5. What would falsify this reading: one specific thing that, if it does not
     happen, means you were wrong.

No preamble. No headings beyond the step numbers. Do not describe your own
process or mention these instructions.
""".strip()


def _varga_block(chart, selection) -> str:
    """Divisional placements for the divisions §7 admitted, and why any were not.

    The placements rather than the codes. "D9 was selected" tells the model
    nothing it can read; a D9 confirmation step needs the actual signs.

    The withheld list is stated rather than dropped: "D60 needs a birth time to
    the minute and yours is recorded to the hour, so it was not used" is the
    sentence this selection exists to make available.
    """
    if chart is None or selection is None:
        return ""
    from rishivan.chart.local_varga import varga_facts

    lines: list[str] = []
    for code in selection.selected:
        facts = varga_facts(chart, code)
        if facts:
            lines.extend(f"  - {fact}" for fact in facts)
    blocks = []
    if lines:
        blocks.append(
            "DIVISIONAL CHARTS admitted for this question:\n" + "\n".join(lines)
        )
    if selection.withheld:
        blocks.append(
            "DIVISIONS NOT USED, and why — do not reason from these:\n"
            + "\n".join(
                f"  - {w.code}: {w.reason}" for w in selection.withheld
            )
        )
    return "\n\n".join(blocks)


def _timing_block(report) -> str:
    """The computed five-stage window, labelled as arithmetic.

    `promise` here came from `assume_promise=True`, not from a fired rule — the
    rule engine does not run in this lane. So the stages are period boundaries
    the model may time a judgement against, and the label has to say that
    plainly or they read as a forecast the system endorsed.
    """
    if report is None:
        return ""
    window = report.by_system.get(report.primary) if report.primary else None
    if window is None:
        return ""
    stages = [
        (label, getattr(window, label))
        for label in ("activation", "trigger", "peak", "fading")
    ]
    lines = [
        f"  - {label}: {r.start.date()} to {r.end.date()}"
        for label, r in stages if r is not None
    ]
    if not lines:
        return ""
    return (
        "CANDIDATE WINDOW — dasha arithmetic over the next ten years. These are\n"
        "period boundaries, not a prediction, and nothing has judged whether this\n"
        "chart promises the thing asked about. That judgement is yours:\n"
        + "\n".join(lines)
    )


def history_block(conversation) -> str:
    """The transcript, with none of the voice instructions around it.

    `conversation.continuity_instruction` is the retrieval lane's version and is
    deliberately not reused: it tells the model not to greet the seeker again and
    to end on a new hook, which are persona instructions for a lane that has a
    persona. This one has neither, and inheriting them would put voice rules back
    into a prompt built to be graded on accuracy.

    The history itself is kept, though. Without it a follow-up answers as though
    asked cold, and a comparison would read that as a grounding failure rather
    than a memory one.
    """
    if conversation is None or conversation.is_empty:
        return ""
    return (
        "EARLIER IN THIS CONVERSATION — already established, do not contradict "
        "it and do not repeat it back:\n\n" + conversation.render()
    )


def build_direct_prompt(state) -> str:
    """The whole prompt, from state, with no I/O.

    Pure so that the golden snapshot is a real snapshot and `test_no_network` is
    a real guarantee. The model call lives in `council/direct.py` — the same
    split `answer_plan` and `narrate` already use, for the same reason: what is
    said and how it is sent are separate concerns, and only one of them is
    testable without credentials.
    """
    from rishivan.council.prompts import _GROUND_TRUTH_WARNING

    constitution = constitution_for(state.get("koonji_domain") or "")

    parts = [framing_block(constitution)]

    history = history_block(state.get("conversation"))
    if history:
        parts.append(history)

    parts.append(method_block(constitution))
    parts.append(_GROUND_TRUTH_WARNING)
    parts.append(scoped_chart(state.get("chart_facts") or [], constitution))

    varga = _varga_block(state.get("chart"), state.get("vargas"))
    if varga:
        parts.append(varga)

    timing = _timing_block(state.get("timing"))
    if timing:
        parts.append(timing)

    if state.get("panchang"):
        parts.append(f"PANCHANG FOR THE DATE IN QUESTION:\n{state['panchang']}")

    parts.append(_OUTPUT_BLOCK)
    parts.append(f"THE QUESTION: {state['question']}")

    return "\n\n---\n\n".join(parts)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_prompt.py -v`
Expected: PASS.

If `test_conversation_history_is_included_when_present` fails on `Conversation()`'s signature, read `rishivan/council/conversation.py` and adapt the fixture — the assertion (prior answer text reaches the prompt) does not change.

- [ ] **Step 5: Generate the golden file and verify it locks**

```bash
./.venv/bin/python -m pytest tests/council/test_direct_prompt_golden.py --golden-update
./.venv/bin/python -m pytest tests/council/test_direct_prompt_golden.py -v
```

Expected: the first call skips with "golden file rewritten"; the second PASSES.

Then read the generated file — this is the one manual review gate in the plan, and it is the whole deliverable:

```bash
cat tests/golden/direct_prompt_marriage.txt
```

Check by eye: the 7th house and its lord are in PRIMARY EVIDENCE; the mahadasha timeline is in COMPUTED PERIODS and nowhere else; no Rishi persona language survives anywhere; the method steps read as an instruction a competent astrologer would follow.

- [ ] **Step 6: Commit**

```bash
git add rishivan/council/direct_prompt.py tests/council/test_direct_prompt.py \
        tests/council/test_direct_prompt_golden.py tests/golden/direct_prompt_marriage.txt
git commit -m "feat(direct): the whole prompt, assembled without touching the network

Pure by construction, which is what makes the golden snapshot a snapshot and
test_no_network a guarantee rather than a hope. The divisional placements go in
rather than the varga codes: 'D9 was selected' is not something a D9
confirmation step can read."
```

---

### Task 4: The node, the state key, and timing without a reading

`dasha_windows_node` computes `promise = bool(reading and reading.promises(domain))` and `windows_between(..., promise=promise)` yields no window when it is false. The rule engine does not run in this lane, so without a change here every timing answer silently loses its window — the exact failure that node's docstring was written to prevent.

**Files:**
- Create: `rishivan/graph/nodes/direct.py`
- Modify: `rishivan/graph/state.py` (add `direct_prompt` to `RishivanState`)
- Modify: `rishivan/graph/nodes/timing.py` (add `assume_promise`)
- Test: `tests/graph/test_nodes_direct.py`

**Interfaces:**
- Consumes: `build_direct_prompt` (Task 3)
- Produces:
  - `direct_read_node(state: RishivanState) -> dict` returning `{"direct_prompt": str}`
  - `dasha_windows_node(state, *, assume_promise: bool = False) -> dict`
  - `RishivanState["direct_prompt"]: str`

- [ ] **Step 1: Write the failing tests**

Create `tests/graph/test_nodes_direct.py`:

```python
"""The direct lane's node, and the timing node without a rule engine behind it."""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.facts import derive_facts
from rishivan.chartstate.build import build_chart_state
from rishivan.graph.nodes.direct import direct_read_node
from rishivan.graph.nodes.timing import dasha_windows_node
from rishivan.graph.state import RishivanState, initial_state

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


def _state(question="when will I marry?", **kw):
    s = initial_state(question, query_time=WHEN)
    s["koonji_domain"] = kw.pop("koonji_domain", "domain.relationship")
    s.update(kw)
    return s


class TestDirectReadNode:
    def test_it_writes_the_prompt_and_nothing_else(self, chart):
        out = direct_read_node(_state(
            chart=chart, chart_facts=derive_facts(chart, when=WHEN),
        ))
        assert set(out) == {"direct_prompt"}
        assert "READING METHOD" in out["direct_prompt"]

    def test_the_key_is_declared_in_the_state_schema(self):
        """LangGraph discards writes to undeclared channels SILENTLY. That has
        shipped here once: retrieve_node returned context_text, the schema did
        not declare it, and every answer was generated with an empty context
        block while the sources panel rendered normally."""
        assert "direct_prompt" in RishivanState.__annotations__

    def test_it_works_without_a_chart(self):
        out = direct_read_node(_state("what is a nakshatra?"))
        assert out["direct_prompt"]

    def test_it_makes_no_model_call(self, chart):
        """The signature takes no client, which is the guarantee. Asserted
        anyway, because a later edit adding one would be easy and silent."""
        import inspect
        assert list(inspect.signature(direct_read_node).parameters) == ["state"]


class TestTimingWithoutAReading:
    def test_no_window_without_a_promise_is_still_the_default(self, chart):
        """Unchanged behaviour for the retrieval lane. A dasha window with no
        grounded promise is how a period becomes a prediction nobody made."""
        state = _state(chart=chart, chart_state=build_chart_state(chart, when=WHEN))
        report = dasha_windows_node(state)["timing"]
        window = report.by_system[report.primary]
        assert window.promise is False

    def test_assume_promise_produces_a_window(self, chart):
        """The direct lane has no rule engine to establish a promise, so the
        arithmetic runs and the MODEL judges whether anything is promised."""
        state = _state(chart=chart, chart_state=build_chart_state(chart, when=WHEN))
        report = dasha_windows_node(state, assume_promise=True)["timing"]
        window = report.by_system[report.primary]
        assert window.promise is True
        assert window.activation is not None

    def test_assume_promise_still_returns_none_without_a_chart(self):
        assert dasha_windows_node(_state(), assume_promise=True)["timing"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_direct.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rishivan.graph.nodes.direct'`

- [ ] **Step 3: Add the state key**

In `rishivan/graph/state.py`, immediately after the `context_text` docstring block (the `life_domain: str | None` line follows it), insert:

```python
    direct_prompt: str
    """The whole prompt the direct lane sends, assembled by
    `council/direct_prompt.py`.

    In state rather than built at the call site for two reasons. It is what
    `council_consult` streams from, mirroring how narration already reads the
    `AnswerPlan` out of state instead of recomputing it. And it is what the
    console dump and the UI expander print, so what is shown is provably the
    string that was sent rather than a second assembly of it.

    Declared here because LangGraph discards writes to undeclared channels
    silently — see `context_text` above for what that cost last time.
    """
```

- [ ] **Step 4: Add `assume_promise` to the timing node**

In `rishivan/graph/nodes/timing.py`, change the signature and the promise line:

```python
def dasha_windows_node(state: RishivanState, *, assume_promise: bool = False) -> dict:
```

Replace:

```python
    reading = state.get("reading")
    promise = bool(reading and reading.promises(domain))
```

with:

```python
    reading = state.get("reading")
    # `assume_promise` is the direct lane, where no rule engine runs. Without it
    # `promise` is always False there and `windows_between` yields nothing, so
    # every timing answer would silently lose its window - the exact failure the
    # docstring above was written about, arriving by a different route.
    #
    # It is not a loosening of the grounding rule, it is a relocation of it: the
    # arithmetic still owns every date, and the prompt hands the model the
    # stages labelled as boundaries rather than as a forecast. Who judges
    # whether the chart promises anything moves from the rule base to the model,
    # which is precisely the change being measured.
    promise = assume_promise or bool(reading and reading.promises(domain))
```

Add to that module's docstring, after the existing "**The promise comes from the reading, not from here.**" paragraph:

```
The direct lane has no reading, and passes `assume_promise=True` so the
arithmetic runs anyway. That lane's prompt labels the result as period
boundaries and asks the model for the promise judgement, which is the trade it
was designed to make - see
`docs/superpowers/specs/2026-08-27-direct-call-reading-design.md`.
```

- [ ] **Step 5: Write the node**

Create `rishivan/graph/nodes/direct.py`:

```python
"""Assemble the direct lane's prompt. Make no call.

The node writes a string; `council/direct.py` sends it. That split is the same
one `answer_plan` and `narrate` already make and it buys the same two things: a
graph whose final state is plain data a checkpointer can persist, and a prompt
that can be asserted against without credentials.

This node is where the retrieval lane's four steps - grounding, council routing,
page retrieval and rule matching - are replaced by one: describe the method, and
hand over the chart.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState


def direct_read_node(state: RishivanState) -> dict:
    from rishivan.council.direct_prompt import build_direct_prompt

    return {"direct_prompt": build_direct_prompt(state)}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_direct.py tests/graph/test_nodes_varga_timing.py tests/graph/test_state.py -v`
Expected: PASS. `test_nodes_varga_timing.py` is included because it covers the node whose signature just changed — the keyword-only default keeps every existing caller valid.

- [ ] **Step 7: Commit**

```bash
git add rishivan/graph/nodes/direct.py rishivan/graph/nodes/timing.py \
        rishivan/graph/state.py tests/graph/test_nodes_direct.py
git commit -m "feat(graph): a node that assembles the reading instead of retrieving it

Also fixes the casualty of dropping the rule engine: promise came only from a
fired rule, so a lane without rules produced no timing window at all - silently,
and looking exactly like a chart with nothing to say. assume_promise moves that
judgement to the model while the arithmetic keeps every date."
```

---

### Task 5: Wire the lane into the graph

`EDGE_MAPS` already separates a router's return label from the node it lands on — `route_after_intake` returns `"retrieve"` and lands on `ground`. That indirection is what makes this task small: direct mode is a second pair of tables, and no router changes.

**Files:**
- Modify: `rishivan/graph/build.py`
- Test: `tests/graph/test_build_direct.py`

**Interfaces:**
- Consumes: `direct_read_node` (Task 4)
- Produces:
  - `build_graph(*, store, client, checkpointer=None, trace_sink=None, direct: bool = False)`
  - `DIRECT_EDGE_MAPS: dict[str, dict[str, str]]`, `DIRECT_STATIC_EDGES: dict[str, str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/graph/test_build_direct.py`:

```python
"""The direct lane's topology.

Asserted on the compiled graph rather than by running it, because the thing that
can be wrong is a destination, and a mistyped destination is a KeyError on a
branch nobody takes until a user does.
"""

import pytest

from rishivan.graph.build import (
    DIRECT_EDGE_MAPS, DIRECT_STATIC_EDGES, EDGE_MAPS, STATIC_EDGES, build_graph,
)


@pytest.fixture
def direct_graph():
    return build_graph(store=None, client=None, direct=True)


@pytest.fixture
def default_graph():
    return build_graph(store=None, client=None)


def _nodes(graph):
    return set(graph.get_graph().nodes)


def _edge_pairs(graph):
    return {(e.source, e.target) for e in graph.get_graph().edges}


class TestDirectTopology:
    def test_direct_read_is_reachable_in_direct_mode(self, direct_graph):
        assert "direct_read" in _nodes(direct_graph)

    def test_retrieval_and_the_council_are_absent_in_direct_mode(self, direct_graph):
        nodes = _nodes(direct_graph)
        for gone in ("retrieve", "ground", "council_routing", "koonji_read",
                     "fan_out", "rishi", "sakshi", "re_examine", "synthesis",
                     "answer_plan", "insufficient"):
            assert gone not in nodes, f"{gone} should not exist in the direct lane"

    def test_the_computational_nodes_all_survive(self, direct_graph):
        nodes = _nodes(direct_graph)
        for kept in ("intake", "warmth", "chart_natal", "chart_moment", "panchang",
                     "chart_state", "hierarchy", "varga_select", "dasha_windows",
                     "chart_render", "render_varga", "render_dasha",
                     "render_ashtakavarga", "render_numerology", "persist"):
            assert kept in nodes, f"{kept} must survive into the direct lane"

    def test_the_reading_chain_skips_koonji(self, direct_graph):
        assert ("varga_select", "dasha_windows") in _edge_pairs(direct_graph)

    def test_dasha_windows_leads_to_the_direct_read(self, direct_graph):
        assert ("dasha_windows", "direct_read") in _edge_pairs(direct_graph)

    def test_the_lane_is_traced_like_any_other(self, direct_graph):
        """persist_node reads reading and answer_plan with .get() and tolerates
        both being None. Why a question produced the reading it did is exactly
        what a trace is for, and this lane is the one being evaluated."""
        assert ("direct_read", "persist") in _edge_pairs(direct_graph)

    def test_a_chartless_question_reaches_the_diagnosis_not_grounding(self):
        """In the retrieval lane intake's "retrieve" lands on `ground`. Here it
        lands on `chart_state`, so hierarchy still runs and the method block
        still gets a domain - a chartless question needs a protocol too."""
        assert DIRECT_EDGE_MAPS["intake"]["retrieve"] == "chart_state"

    def test_every_direct_destination_is_a_real_node(self, direct_graph):
        nodes = _nodes(direct_graph)
        destinations = {
            d for table in DIRECT_EDGE_MAPS.values() for d in table.values()
        } | set(DIRECT_STATIC_EDGES)
        assert destinations <= nodes


class TestTheDefaultLaneIsUntouched:
    def test_the_default_tables_still_hold_the_retrieval_topology(self):
        assert EDGE_MAPS["intake"]["retrieve"] == "ground"
        assert STATIC_EDGES["varga_select"] == "koonji_read"
        assert STATIC_EDGES["koonji_read"] == "dasha_windows"

    def test_the_default_graph_still_has_the_council(self, default_graph):
        nodes = _nodes(default_graph)
        for kept in ("retrieve", "ground", "koonji_read", "rishi", "sakshi"):
            assert kept in nodes

    def test_the_default_graph_has_no_direct_read(self, default_graph):
        assert "direct_read" not in _nodes(default_graph)

    def test_the_routers_were_not_edited(self):
        """The whole reason this task is small. Both retrieval routers return
        the label "retrieve"; only the table it resolves through changes."""
        import inspect
        from rishivan.graph import edges

        source = inspect.getsource(edges)
        assert 'return "retrieve"' in source
        assert "direct_read" not in source
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/graph/test_build_direct.py -v`
Expected: FAIL — `ImportError: cannot import name 'DIRECT_EDGE_MAPS'`

- [ ] **Step 3: Write the implementation**

In `rishivan/graph/build.py`, add `direct` to the node imports:

```python
from rishivan.graph.nodes import (
    answer, answer_plan, chart, diagnosis, direct, ground, hierarchy, intake,
    koonji, persist, rishi, sakshi, synthesis, timing, varga,
)  # noqa: F401 - `answer` re-exported for callers still importing it
```

After the `STATIC_EDGES` definition, add:

```python
DIRECT_NODE_NAMES = (
    "intake", "warmth",
    "chart_natal", "chart_moment", "panchang", "chart_state", "hierarchy",
    "varga_select", "dasha_windows",
    "chart_render", "render_varga", "render_dasha", "render_ashtakavarga",
    "render_numerology",
    "direct_read", "persist",
)
"""The direct lane's nodes. Every computational one survives; retrieval, the
rule engine and the council do not."""

DIRECT_EDGE_MAPS: dict[str, dict[str, str]] = {
    # The routers are not edited, and that is the point of this table. Both
    # retrieval routers return the label "retrieve", meaning "go and do the
    # reading"; which node begins that reading is the graph's business. So the
    # direct lane is a different resolution of the same vocabulary, and
    # `tests/graph/test_edges.py`'s table stays valid as written.
    "intake": {
        "warmth": "warmth",
        "chart_natal": "chart_natal",
        "chart_moment": "chart_moment",
        "panchang": "panchang",
        # `ground` in the default lane. Here the chartless path goes through the
        # diagnosis so `hierarchy_node` still runs and the method block still
        # gets a domain - a question with no chart needs a protocol too.
        "retrieve": "chart_state",
    },
    "chart_natal": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "chart_state",
    },
    "chart_moment": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "chart_state",
    },
    "chart_render": {
        "render_varga": "render_varga",
        "render_dasha": "render_dasha",
        "render_ashtakavarga": "render_ashtakavarga",
        "render_numerology": "render_numerology",
    },
}

DIRECT_STATIC_EDGES: dict[str, str] = {
    "warmth": END,
    "panchang": "chart_state",
    "chart_state": "hierarchy",
    "hierarchy": "varga_select",
    # koonji_read is gone, so the chain shortens by one. `dasha_windows` is
    # bound with `assume_promise=True` below, because the promise it used to
    # read came from the reading this lane does not take.
    "varga_select": "dasha_windows",
    "dasha_windows": "direct_read",
    "render_varga": END,
    "render_dasha": END,
    "render_ashtakavarga": END,
    "render_numerology": END,
    # Traced like any other lane. `persist_node` reads `reading` and
    # `answer_plan` with `.get()` and tolerates both being None, and this is the
    # lane under evaluation - the one whose traces are most worth having.
    "direct_read": "persist",
    "persist": END,
}
```

Then replace the body of `build_graph` with a two-branch version:

```python
def build_graph(*, store, client, checkpointer=None, trace_sink=None,
                direct: bool = False):
    """The council graph, or the direct lane.

    Two topologies over one node set rather than two builders, so a change to a
    shared node cannot land in one lane and miss the other.

    `direct=True` drops retrieval, the rule engine and the council, and sends
    one prompt built from the classical method. See
    `docs/superpowers/specs/2026-08-27-direct-call-reading-design.md`.
    """
    if direct:
        return _build_direct(
            store=store, client=client, checkpointer=checkpointer,
            trace_sink=trace_sink,
        )
    return _build_council(
        store=store, client=client, checkpointer=checkpointer,
        trace_sink=trace_sink,
    )


def _build_direct(*, store, client, checkpointer, trace_sink):
    g = StateGraph(RishivanState)

    g.add_node("intake", partial(intake.intake_node, client=client))
    g.add_node("warmth", intake.warmth_node)
    g.add_node("chart_natal", chart.chart_natal_node)
    g.add_node("chart_moment", chart.chart_moment_node)
    g.add_node("panchang", chart.panchang_node)
    g.add_node("chart_state", diagnosis.chart_state_node)
    g.add_node("hierarchy", hierarchy.hierarchy_node)
    g.add_node("varga_select", varga.varga_select_node)
    # The promise the retrieval lane reads off a fired rule has no source here.
    g.add_node(
        "dasha_windows",
        partial(timing.dasha_windows_node, assume_promise=True),
    )
    g.add_node("chart_render", _chart_render_passthrough)
    g.add_node("render_varga", chart.render_varga_node)
    g.add_node("render_dasha", chart.render_dasha_node)
    g.add_node("render_ashtakavarga", chart.render_ashtakavarga_node)
    g.add_node("render_numerology", chart.render_numerology_node)
    g.add_node("direct_read", direct.direct_read_node)
    g.add_node("persist", partial(persist.persist_node, sink=trace_sink))

    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake", R.route_after_intake, DIRECT_EDGE_MAPS["intake"]
    )
    for node in ("chart_natal", "chart_moment"):
        g.add_conditional_edges(
            node, R.route_after_chart, DIRECT_EDGE_MAPS[node]
        )
    g.add_conditional_edges(
        "chart_render", R.route_chart_kind, DIRECT_EDGE_MAPS["chart_render"]
    )
    for source, destination in DIRECT_STATIC_EDGES.items():
        g.add_edge(source, destination)

    return g.compile(checkpointer=checkpointer)
```

Rename the existing builder body to `_build_council(*, store, client, checkpointer, trace_sink)`, leaving every line of it otherwise untouched.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/graph/ -v`
Expected: PASS — the new file plus every existing graph test, `test_parity.py` and `test_build.py` included. Those two are the proof the default lane did not move.

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/build.py tests/graph/test_build_direct.py
git commit -m "feat(graph): a second topology over the same nodes

EDGE_MAPS already kept a router's return label separate from the node it lands
on, which is the whole reason this is a table and not a refactor: both retrieval
routers still return \"retrieve\", and the direct lane just resolves that label
somewhere else. No router edited, no router test touched."
```

---

### Task 6: The model call, and the console dump

**Files:**
- Create: `rishivan/council/direct.py`
- Test: `tests/council/test_direct_call.py`

**Interfaces:**
- Consumes: `rishivan.council.client.model_name`
- Produces: `stream_direct(prompt: str, *, client, echo: bool = True) -> Generator[str, None, None]`

- [ ] **Step 1: Write the failing tests**

Create `tests/council/test_direct_call.py`:

```python
"""The one call, its config, and the dump that makes the comparison possible."""

import pytest

from rishivan.council.direct import stream_direct


class _Chunk:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, chunks=("Marriage ", "is close."), explode_after=None):
        self.chunks, self.explode_after = chunks, explode_after
        self.calls = []

    def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)
        for index, text in enumerate(self.chunks):
            if self.explode_after is not None and index == self.explode_after:
                raise RuntimeError("the model fell over")
            yield _Chunk(text)


class FakeClient:
    def __init__(self, **kw):
        self.models = FakeModels(**kw)


class TestStreamDirect:
    def test_it_streams_the_chunks(self):
        client = FakeClient()
        assert "".join(stream_direct("PROMPT", client=client)) == "Marriage is close."

    def test_it_sends_the_prompt_verbatim(self):
        client = FakeClient()
        list(stream_direct("PROMPT", client=client))
        assert client.models.calls[0]["contents"] == "PROMPT"

    def test_temperature_is_zero(self):
        """Reproducibility is the point: the same prompt must give the same
        reading twice, or a comparison against three other platforms is
        measuring sampling noise."""
        client = FakeClient()
        list(stream_direct("PROMPT", client=client))
        config = client.models.calls[0]["config"]
        assert config.temperature == 0.0

    def test_thinking_is_on(self):
        client = FakeClient()
        list(stream_direct("PROMPT", client=client))
        config = client.models.calls[0]["config"]
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_budget != 0

    def test_it_uses_the_flash_tier(self):
        from rishivan.council.client import model_name
        client = FakeClient()
        list(stream_direct("PROMPT", client=client))
        assert client.models.calls[0]["model"] == model_name("flash")

    def test_a_midstream_failure_discards_the_partial(self):
        """Half a sentence on a reader's screen is worse than a stated failure.
        Same decision narrate.stream_answer makes, minus the template - there is
        no AnswerPlan in this lane to render one from."""
        client = FakeClient(chunks=("Marriage ", "is close."), explode_after=1)
        out = "".join(stream_direct("PROMPT", client=client))
        assert "is close." not in out
        assert "could not" in out.lower()

    def test_a_failure_before_the_first_chunk_says_so(self):
        client = FakeClient(explode_after=0)
        out = "".join(stream_direct("PROMPT", client=client))
        assert out.strip()
        assert "could not" in out.lower()


class TestTheConsoleDump:
    def test_the_whole_prompt_is_printed(self, capsys):
        list(stream_direct("THE ENTIRE PROMPT", client=FakeClient()))
        assert "THE ENTIRE PROMPT" in capsys.readouterr().out

    def test_it_is_delimited_so_it_can_be_copied(self, capsys):
        list(stream_direct("PROMPT", client=FakeClient()))
        out = capsys.readouterr().out
        assert "DIRECT PROMPT" in out
        assert "END DIRECT PROMPT" in out

    def test_it_prints_before_the_call_not_after(self, capsys):
        """So a prompt that makes the model fail is still on screen."""
        list(stream_direct("PROMPT", client=FakeClient(explode_after=0)))
        assert "PROMPT" in capsys.readouterr().out

    def test_it_reports_the_size(self, capsys):
        list(stream_direct("PROMPT", client=FakeClient()))
        assert "chars" in capsys.readouterr().out

    def test_echo_can_be_turned_off(self, capsys):
        list(stream_direct("PROMPT", client=FakeClient(), echo=False))
        assert "DIRECT PROMPT" not in capsys.readouterr().out
```

- [ ] **Step 2: Verify the thinking sentinel against the installed SDK**

Before implementing, confirm `-1` is accepted:

```bash
./.venv/bin/python -c "
from google.genai import types
c = types.GenerateContentConfig(
    temperature=0.0,
    thinking_config=types.ThinkingConfig(thinking_budget=-1),
)
print('accepted:', c.thinking_config.thinking_budget)"
```

Expected: `accepted: -1`.

If it raises a validation error, use `thinking_budget=8192` instead and change the constant plus its docstring in Step 3 — `test_thinking_is_on` asserts only that the budget is non-zero, so it passes either way. Record which you used in the commit message.

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_call.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rishivan.council.direct'`

- [ ] **Step 4: Write the implementation**

Create `rishivan/council/direct.py`:

```python
"""One call, one answer, and the prompt on screen.

The dump is not debug output. This lane exists to be compared against ChatGPT,
Gemini and Claude in a browser, and a comparison is only worth running if the
prompt can be pasted into all four places unchanged. So it goes to stdout, it is
delimited, and it is not gated on DEBUG.

Printed immediately BEFORE the call, so what is on screen is provably the string
that was sent - and so a prompt that makes the model fall over is still there to
look at afterwards.
"""

from __future__ import annotations

import logging
from typing import Generator

logger = logging.getLogger(__name__)

MODEL_TIER = "flash"
"""Same tier as the retrieval lane, deliberately. The comparison is about
grounding and the model's own knowledge; changing the tier at the same time
would leave two variables and one result."""

THINKING_BUDGET = -1
"""Dynamic. The right budget for "what colour should I wear" and for "will I
have children" are not the same number, and the model is better placed to judge
that than a constant is."""

FAILED = (
    "I could not complete this reading — the model call failed partway through. "
    "Nothing here is a partial answer; please ask again."
)
"""What a failure says.

There is no template fallback in this lane. `narrate.render_template` composes
prose from an `AnswerPlan`, and this lane has no plan - so the honest option is
to say the call failed rather than to compose something over nothing.
"""


def _echo(prompt: str) -> None:
    """The prompt, delimited for copying.

    `print` rather than the logger on purpose: a logger's level, handlers and
    format are all things that can silence this, and being silenced defeats the
    only reason it exists. Under Streamlit this lands in the terminal running
    the server, which is where it is wanted.
    """
    banner = f"DIRECT PROMPT — {len(prompt):,} chars, ~{len(prompt) // 4:,} tokens"
    print(f"\n{'=' * 78}\n{banner}\n{'=' * 78}\n{prompt}\n{'=' * 78}\nEND DIRECT PROMPT\n{'=' * 78}\n", flush=True)


def stream_direct(prompt: str, *, client, echo: bool = True) -> Generator[str, None, None]:
    """The reading, chunk by chunk.

    A mid-stream failure discards whatever accumulated rather than leaving half
    a sentence on the reader's screen - the same call `narrate.stream_answer`
    makes, and for the same reason: losing three good words costs less than an
    answer that stops mid-clause.
    """
    from google.genai import types

    from rishivan.council.client import model_name

    if echo:
        _echo(prompt)

    emitted: list[str] = []
    try:
        for chunk in client.models.generate_content_stream(
            model=model_name(MODEL_TIER),
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=THINKING_BUDGET
                ),
            ),
        ):
            if chunk.text:
                emitted.append(chunk.text)
                yield chunk.text
    except Exception:  # noqa: BLE001
        logger.warning("the direct reading call failed", exc_info=True)
        if emitted:
            # Already on the reader's screen and unretractable. Mark the seam
            # rather than pretending the sentence finished.
            yield "\n\n---\n\n"
        yield FAILED
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_call.py -v`
Expected: PASS — 12 tests.

`test_a_midstream_failure_discards_the_partial` asserts `"is close."` is absent while `"Marriage "` was already yielded. That is correct: the first chunk cannot be unsent, so the guarantee is that no *further* partial arrives and the failure is stated.

- [ ] **Step 6: Commit**

```bash
git add rishivan/council/direct.py tests/council/test_direct_call.py
git commit -m "feat(direct): one call at temperature 0, with the prompt on screen

The dump is the deliverable, not debug output: this lane exists to be compared
against three browser platforms, and that only works if the exact prompt can be
pasted into all of them. stdout, delimited, printed before the call so a prompt
that kills the request is still readable afterwards."
```

- [ ] **Step 7: Quiet the debug print that would interleave with the dump**

`rishivan/graph/nodes/intake.py` has a stray debug `print` — an f-string opening
`===============classify returned the below details:-` — that fires on every
request and lands on the same stdout as the dump. Since the whole point of the
dump is a clean copy-paste, this competes with the deliverable.

Demote it to the logger rather than deleting it; somebody put it there for a
reason and `logger.debug` keeps that reason available:

```python
    logger.debug(
        "classified: rishi=%s domain=%s classification=%s",
        rishi, domain, classification,
    )
```

Verify nothing else prints to stdout on the reading path:

```bash
grep -rn "^\s*print(" rishivan/ | grep -v "direct.py"
```

Expected: no hits on any module the request path imports. Commit separately:

```bash
git add rishivan/graph/nodes/intake.py
git commit -m "fix(intake): the classifier debug goes to the log, not to stdout

It fired on every request and shared stdout with the direct lane's prompt dump,
which exists to be copy-pasted. Demoted rather than deleted - the information is
still there at debug level."
```

---

### Task 7: Thread the mode through the adapter

**Files:**
- Modify: `rishivan/council/orchestrator.py`
- Test: `tests/graph/test_adapter_direct.py`

**Interfaces:**
- Consumes: `build_graph(..., direct=...)` (Task 5), `stream_direct` (Task 6)
- Produces: `council_consult(..., direct: bool = False) -> dict`, with `result["direct_prompt"]` set on the direct path only.

- [ ] **Step 1: Write the failing tests**

Create `tests/graph/test_adapter_direct.py`:

```python
"""The adapter's contract, on the direct path.

The default path's contract is covered by `test_adapter.py` and must not move;
one test here asserts that from the other side.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


class _Chunk:
    def __init__(self, text):
        self.text = text


class FakeModels:
    """Only the reading call. The classifier is stubbed at its own seam — see
    `stub_classifier` below."""

    def __init__(self):
        self.stream_prompts = []

    def generate_content_stream(self, **kwargs):
        self.stream_prompts.append(kwargs.get("contents"))
        yield _Chunk("Marriage is close.")


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture(autouse=True)
def stub_classifier(monkeypatch):
    """Stub the classifier at its own seam, not through a fake response body.

    `intake_node` does `from rishivan.council.classifier import classify_query`
    at call time, so patching the module attribute takes effect. Faking
    `client.models.generate_content` instead would mean encoding the
    classifier's JSON contract into this test — a second copy of a schema that
    lives somewhere else, and one that fails confusingly when that schema moves.
    """
    def fake_classify(client, question, model="", conversation=None):
        return {
            "query_domain": "natal",
            "intent": "reading",
            "is_smalltalk_or_gibberish": False,
            "primary_rishi": "medhan",
            "search_query": question,
            "stated_facts": [],
        }

    monkeypatch.setattr(
        "rishivan.council.classifier.classify_query", fake_classify
    )


def _consult(client, **kw):
    from rishivan.council.orchestrator import council_consult

    return council_consult(
        client, None, kw.pop("question", "when will I marry?"),
        birth_data=BIRTH, query_time=WHEN, **kw,
    )


class TestDirectPath:
    def test_it_returns_the_prompt_it_sent(self, client):
        result = _consult(client, direct=True)
        assert "READING METHOD" in result["direct_prompt"]

    def test_the_prompt_returned_is_the_prompt_sent(self, client):
        """Two assemblies of "the same" prompt is how a UI panel starts lying
        about what the model saw."""
        result = _consult(client, direct=True)
        list(result["answer_stream"])
        assert client.models.stream_prompts == [result["direct_prompt"]]

    def test_the_answer_streams(self, client):
        result = _consult(client, direct=True)
        assert "".join(result["answer_stream"]) == "Marriage is close."

    def test_the_result_keys_are_still_the_declared_contract(self, client):
        from rishivan.graph.state import RESULT_KEYS

        result = _consult(client, direct=True)
        assert RESULT_KEYS <= set(result)

    def test_the_retrieval_panels_get_nothing_to_render(self, client):
        """No panel work is needed in the UI: both expanders are guarded on
        these being non-empty, so they disappear on their own."""
        result = _consult(client, direct=True)
        assert result["sources"] == []
        assert result["matched_rules"] == []

    def test_a_chart_is_still_computed(self, client):
        result = _consult(client, direct=True)
        assert result["chart_facts"]
        assert result["chart_summary"]


class TestTheDefaultPathIsUnchanged:
    def test_no_direct_prompt_leaks_onto_the_default_path(self, client, monkeypatch):
        """The key is set conditionally. Promising it unconditionally would be a
        new contract, and callers read the optional keys with .get()."""
        import rishivan.graph.nodes.retrieve as retrieve_module

        monkeypatch.setattr(
            retrieve_module, "retrieve_node",
            lambda state, **kw: {"sources": [], "context_text": "",
                                 "matched_rules": [], "contributors": [],
                                 "contributor_reports": ()},
        )
        result = _consult(client)
        assert "direct_prompt" not in result
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/graph/test_adapter_direct.py -v`
Expected: FAIL — `TypeError: council_consult() got an unexpected keyword argument 'direct'`

- [ ] **Step 3: Write the implementation**

In `rishivan/council/orchestrator.py`, add the parameter after `thread_id`:

```python
    thread_id: str | None = None,
    direct: bool = False,
) -> dict:
```

Add to the docstring, before the "Returns a dict with keys" paragraph:

```
    `direct=True` runs the direct lane: no page retrieval, no rule engine, no
    council, and one call carrying the classical method plus a question-scoped
    chart. The result adds `direct_prompt` — the exact string that was sent, so
    a panel showing it cannot drift from what the model saw. Default False, so
    every existing caller is unaffected. See
    `docs/superpowers/specs/2026-08-27-direct-call-reading-design.md`.
```

Change the graph construction:

```python
    graph = build_graph(
        store=store, client=client, checkpointer=checkpointer, direct=direct,
    )
```

Replace the narration line:

```python
    result = {key: final.get(key) for key in RESULT_KEYS}
    if direct:
        # Narration is the same one call that did the reading, so there is no
        # plan to stream from - the prompt itself is what leaves the graph.
        from rishivan.council import direct as direct_call

        result["direct_prompt"] = final.get("direct_prompt") or ""
        result["answer_stream"] = direct_call.stream_direct(
            result["direct_prompt"], client=client
        )
    else:
        result["answer_stream"] = narrate.stream_for(final, client=client)
        result["answer_plan"] = final.get("answer_plan")
```

Note `answer_plan` moves inside the `else`: the direct lane produces none, and returning a `None` under that key would invite a caller to render an empty plan panel.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/graph/test_adapter_direct.py tests/graph/test_adapter.py tests/graph/test_parity.py -v`
Expected: PASS.

If `test_adapter.py` fails on `answer_plan`, it asserts that key on the default path — which still sets it. If it asserts the key on *every* path, keep the assertion honest by leaving `answer_plan` set unconditionally and revert that one line.

- [ ] **Step 5: Run the whole suite**

Run: `./.venv/bin/python -m pytest tests/ -x -q`
Expected: PASS, or only pre-existing failures. Capture the baseline first if unsure:

```bash
git stash && ./.venv/bin/python -m pytest tests/ -q 2>&1 | tail -5 && git stash pop
```

- [ ] **Step 6: Commit**

```bash
git add rishivan/council/orchestrator.py tests/graph/test_adapter_direct.py
git commit -m "feat(council): council_consult can take the direct lane

One keyword, defaulting False, so run_eval and streamlit_app are untouched. The
prompt comes back in the result rather than being rebuilt for display: two
assemblies of the same prompt is how a panel starts lying about what the model
actually saw."
```

---

### Task 8: The prompt-generating script

This is the path for building the comparison set: generate a prompt, paste it into four places, grade four answers. No model call, no credentials, no network.

**Files:**
- Create: `scripts/direct_prompt.py`
- Test: `tests/council/test_direct_prompt_cli.py`

**Interfaces:**
- Consumes: `build_direct_prompt` (Task 3), `rishivan.chart.ephemeris.compute_chart`, `rishivan.chart.facts.derive_facts`
- Produces: `main(argv: list[str] | None = None) -> int`, `prompt_for(question, *, dob, tob, place, lat, lon, tz_offset, when) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/council/test_direct_prompt_cli.py`:

```python
"""The script that makes the browser comparison mechanical."""

import pytest

from scripts.direct_prompt import main, prompt_for


class TestPromptFor:
    def test_it_builds_a_natal_prompt(self):
        prompt = prompt_for(
            "when will I marry?", dob="1990-01-01", tob="12:00",
            place="New Delhi", lat=28.6139, lon=77.2090, tz_offset=5.5,
            when="2026-08-25",
        )
        assert "READING METHOD" in prompt
        assert "when will I marry?" in prompt

    def test_the_question_routes_the_method(self):
        marriage = prompt_for(
            "when will I marry?", dob="1990-01-01", tob="12:00",
            place="New Delhi", lat=28.6139, lon=77.2090, tz_offset=5.5,
            when="2026-08-25",
        )
        career = prompt_for(
            "will I get a promotion?", dob="1990-01-01", tob="12:00",
            place="New Delhi", lat=28.6139, lon=77.2090, tz_offset=5.5,
            when="2026-08-25",
        )
        assert "Love / Marriage / Relationships" in marriage
        assert "Love / Marriage / Relationships" not in career

    def test_it_works_without_birth_data(self):
        prompt = prompt_for("what is a nakshatra?", dob=None, tob=None,
                            place="", lat=None, lon=None, tz_offset=5.5,
                            when="2026-08-25")
        assert "No chart was computed" in prompt

    def test_it_is_deterministic_for_a_fixed_when(self):
        kw = dict(dob="1990-01-01", tob="12:00", place="New Delhi",
                  lat=28.6139, lon=77.2090, tz_offset=5.5, when="2026-08-25")
        assert prompt_for("when will I marry?", **kw) == prompt_for(
            "when will I marry?", **kw
        )


class TestCli:
    def test_it_prints_the_prompt_and_exits_zero(self, capsys):
        code = main([
            "--question", "when will I marry?",
            "--dob", "1990-01-01", "--tob", "12:00",
            "--place", "New Delhi", "--lat", "28.6139", "--lon", "77.2090",
            "--when", "2026-08-25",
        ])
        assert code == 0
        assert "READING METHOD" in capsys.readouterr().out

    def test_a_question_is_required(self):
        with pytest.raises(SystemExit):
            main([])

    def test_it_makes_no_model_call(self, monkeypatch, capsys):
        """No credentials, no network. This script must run on a laptop with
        nothing configured, which is where the comparison set gets built."""
        import builtins

        real_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.startswith(("google.genai", "qdrant_client")):
                raise AssertionError(f"the CLI imported {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", guarded)
        assert main(["--question", "when will I marry?"]) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_prompt_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.direct_prompt'`

- [ ] **Step 3: Write the implementation**

Create `scripts/direct_prompt.py`:

```python
"""Print the exact prompt the direct lane would send. Make no call.

This is how the comparison set gets built: generate a prompt, paste it into
ChatGPT, Gemini and Claude, grade the four answers side by side. No credentials,
no network, no model - so it runs anywhere.

    python -m scripts.direct_prompt \
        --question "when will I marry?" \
        --dob 1990-01-01 --tob 12:00 --place "New Delhi" \
        --lat 28.6139 --lon 77.2090

`--when` fixes the moment the chart is read at, and defaults to now. Fix it when
generating a set you intend to keep: the running dasha and the transiting Moon
both move, so two prompts generated a week apart are not the same prompt.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime


def prompt_for(
    question: str,
    *,
    dob: str | None,
    tob: str | None,
    place: str = "",
    lat: float | None = None,
    lon: float | None = None,
    tz_offset: float = 5.5,
    when: str | None = None,
) -> str:
    """The prompt, from plain strings.

    Runs the same nodes the graph would, in the same order, rather than calling
    the graph: `intake` needs a model to classify, and this script exists
    precisely for the case where there is no model. `hierarchy_node` is
    deterministic and keyword-driven, so the routed domain here is the one the
    app would reach.
    """
    from rishivan.council.direct_prompt import build_direct_prompt
    from rishivan.graph.nodes.hierarchy import hierarchy_node
    from rishivan.graph.nodes.timing import dasha_windows_node
    from rishivan.graph.nodes.varga import varga_select_node
    from rishivan.graph.state import initial_state

    moment = datetime.fromisoformat(when) if when else datetime.now()

    birth = None
    if dob and tob:
        date = datetime.fromisoformat(dob)
        time = datetime.strptime(tob, "%H:%M")
        from rishivan.chart.ephemeris import BirthData

        birth = BirthData(
            year=date.year, month=date.month, day=date.day,
            hour=time.hour, minute=time.minute,
            tz_offset_hours=tz_offset,
            lat=lat or 0.0, lon=lon or 0.0, place=place,
        )

    state = initial_state(
        question, birth_data=birth, query_time=moment,
        lat=lat, lon=lon, tz_offset=tz_offset, place=place,
    )

    if birth is not None:
        from rishivan.chart.ephemeris import compute_chart
        from rishivan.chart.facts import derive_facts
        from rishivan.chartstate.build import build_chart_state

        chart = compute_chart(birth)
        state["chart"] = chart
        state["chart_facts"] = derive_facts(chart, when=moment)
        state["chart_state"] = build_chart_state(chart, when=moment)

    state.update(hierarchy_node(state))
    state.update(varga_select_node(state))
    state.update(dasha_windows_node(state, assume_promise=True))

    return build_direct_prompt(state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.direct_prompt",
        description="Print the direct lane's prompt for one question.",
    )
    parser.add_argument("--question", required=True)
    parser.add_argument("--dob", help="birth date, YYYY-MM-DD")
    parser.add_argument("--tob", help="birth time, HH:MM (24h, local)")
    parser.add_argument("--place", default="")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--tz-offset", type=float, default=5.5,
                        dest="tz_offset", help="hours from UT (default IST)")
    parser.add_argument("--when", help="read the chart at this date "
                                      "(YYYY-MM-DD), default now")
    args = parser.parse_args(argv)

    print(prompt_for(
        args.question, dob=args.dob, tob=args.tob, place=args.place,
        lat=args.lat, lon=args.lon, tz_offset=args.tz_offset, when=args.when,
    ))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/council/test_direct_prompt_cli.py -v`
Expected: PASS — 7 tests.

If the import of `scripts.direct_prompt` fails, check `scripts/__init__.py` exists (`ls scripts/__init__.py`); other scripts in that directory are run as `python -m scripts.<name>`, so it should.

- [ ] **Step 5: Run it for real and read the output**

```bash
./.venv/bin/python -m scripts.direct_prompt \
  --question "when will I marry?" \
  --dob 1990-01-01 --tob 12:00 --place "New Delhi" \
  --lat 28.6139 --lon 77.2090 --when 2026-08-25
```

Expected: a complete prompt on stdout, no traceback, no credential error. Read it. This is the artefact the whole plan is for — if it does not read like something you would hand a competent astrologer, the wording needs another pass before the comparison is worth running.

- [ ] **Step 6: Commit**

```bash
git add scripts/direct_prompt.py tests/council/test_direct_prompt_cli.py
git commit -m "feat(scripts): generate the comparison prompt without credentials

Runs the deterministic nodes directly rather than the graph, because intake
needs a model to classify and this script exists for the case where there is no
model. hierarchy_node is a keyword table, so the domain it routes to is the one
the app would reach."
```

---

### Task 9: The UI switch

**Files:**
- Modify: `streamlit_app.py`
- Test: manual (Streamlit UI has no test harness in this repo)

**Interfaces:**
- Consumes: `council_consult(..., direct=...)` (Task 7)
- Produces: nothing other modules read.

- [ ] **Step 1: Find the sidebar and the consult call**

```bash
grep -n "council_consult\|st.sidebar\|with st.sidebar" streamlit_app.py
```

Note the line numbers. The sidebar block holds the birth-details expander at `streamlit_app.py:258`.

- [ ] **Step 2: Add the toggle to the sidebar**

Inside the sidebar block, after the birth-details expander closes, add:

```python
    direct_mode = st.toggle(
        "Direct reading (no corpus)",
        value=False,
        help=(
            "Answer from the model's own knowledge of the classical texts, with "
            "the computed chart and the classical method in one prompt — no page "
            "retrieval, no rule engine, no council. The full prompt is printed "
            "to the terminal so it can be pasted into other platforms."
        ),
    )
    st.session_state["direct_mode"] = direct_mode
```

- [ ] **Step 3: Pass it to the consult call**

At the `council_consult(...)` call site, add the keyword:

```python
        direct=st.session_state.get("direct_mode", False),
```

- [ ] **Step 4: Add the prompt expander**

Immediately before the citation strip (`page_groups = result.get("sources", [])`, `streamlit_app.py:712`), add:

```python
            # For running the comparison from the deployed app rather than a
            # terminal. This renders the string the model was sent, taken from
            # the result rather than rebuilt - a second assembly is how a panel
            # starts lying about what the model saw.
            if result.get("direct_prompt"):
                with st.expander("📋 The exact prompt", expanded=False):
                    st.caption(
                        f"{len(result['direct_prompt']):,} characters. Paste this "
                        "into another platform to compare."
                    )
                    st.code(result["direct_prompt"], language="text")
```

- [ ] **Step 5: Verify by hand**

```bash
./.venv/bin/python -m streamlit run streamlit_app.py
```

Check, in this order:

1. Toggle **off**, ask "when will I marry?" with birth details — the citation strip and the rules panel appear as they do today. This is the regression check.
2. Toggle **on**, same question — the answer streams; the citation strip and rules panel are both **gone** (they are guarded on `sources` and `matched_rules`, which are empty); the "📋 The exact prompt" expander is present and holds the whole prompt.
3. Look at the terminal running the server — the delimited prompt dump is there, and matches the expander byte for byte.
4. Toggle **on**, ask "hi" — the warmth path still short-circuits and no prompt is built.
5. Toggle **on**, ask "show me my D9" — the chart table renders and no model is called.

- [ ] **Step 6: Commit**

```bash
git add streamlit_app.py
git commit -m "feat(ui): a switch between the two lanes, and the prompt beside the answer

No panel work was needed: the citation strip and the rules panel are guarded on
sources and matched_rules, both empty in the direct lane, so they disappear on
their own."
```

---

## Verification

Run before declaring this done:

```bash
./.venv/bin/python -m pytest tests/ -q
./.venv/bin/python -m pytest tests/graph/test_parity.py tests/graph/test_adapter.py -v
./.venv/bin/python -m scripts.direct_prompt --question "when will I marry?" \
  --dob 1990-01-01 --tob 12:00 --place "New Delhi" --lat 28.6139 --lon 77.2090
```

The middle command is the one that matters most: it is the proof the retrieval lane still works, which is what makes the comparison possible at all.

## What this deliberately leaves undone

- **The two-call design** (structured analysis, then narration) is the shape most likely to be right for production, because separating what is true from how it is said is the largest available quality lever with these models. It cannot be pasted into a browser chat, which is why it is not this. `build_direct_prompt` returns a string and takes no client, so adding an analysis call later changes what consumes the prompt rather than how it is built.
- **The persona.** It returns as a narration step over this same material. Nothing here blocks it.
- **The citations panel, the rules panel, the sakshi auditor, the prediction ledger's licensing checks.** All still work on the default lane. None is wired into this one.
