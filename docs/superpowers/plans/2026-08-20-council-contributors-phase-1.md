# Council Contributors (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the second generated Rishi voice with deterministic evidence contributors, so one Rishi answers using computed facts and coverage-gated rules supplied by others.

**Architecture:** Five "domain" Rishis may speak; three "service" Rishis (vyom/ritam/tejan) may only compute. The routed client life domain now selects the persona, so the coverage gate and the voice can no longer disagree. Each contributor is a pure function returning a frozen `ContributorReport`; empty reports never reach the prompt. The primary's prompt gains coverage-ordered facts, labelled contributor blocks, and per-source tier/school.

**Tech Stack:** Python 3.12, pytest, SQLAlchemy (knowledge layer only), Qdrant (`rishivan/rag/vector_store.py`), Streamlit, Vertex AI via `google-genai`.

**Spec:** `docs/superpowers/specs/2026-08-20-council-contributors-design.md`

## Global Constraints

- **TDD is mandatory.** Write the test, run it, watch it fail for the right reason, then implement. A test that passes on first run is a plan failure — delete the implementation and start over.
- **Run tests with:** `.venv/bin/python -m pytest` from the repo root. `PYTHONPATH=.` is required for ad-hoc scripts, not for pytest.
- **No new LLM calls.** Every contributor is deterministic. Adding a generation call to a contributor violates the spec's Section 3 rationale.
- **Two taxonomies, never conflated.** *Life domain* = the client's eight (`atma prema artha karma vansh aarogya yatra dharma`), from `domains.LIFE_DOMAIN_KEYS`. *Persona* = the eight voices (`agam vyom dhruvan ritam tejan medhan tattvan pragnav`), from `personas.ALL_RISHI_NAMES`. Never name a variable `domain` when it holds a persona.
- **Do not edit `rishivan/council/domains.py`'s `RISHI_LIFE_DOMAINS` table.** The weights are already correct and derived from ER §4–11. This plan only changes who consumes them.
- **`from __future__ import annotations` at the top of every new module**, matching every existing module in `rishivan/`.
- **Docstrings are short and state the why**, matching the surrounding code. A docstring that restates the signature is noise.
- **Commit after every task.** Message style: `feat(council): ...`, `fix(rag): ...`, `test: ...` — see `git log`.

---

### Task 1: Rishi classes — who may speak

**Files:**
- Modify: `rishivan/council/domains.py` (append after `RISHI_LIFE_DOMAINS`, around line 155)
- Test: `tests/council/test_domains.py` (create if absent)

**Interfaces:**
- Consumes: `RISHI_LIFE_DOMAINS`, `LIFE_DOMAIN_KEYS` (both already in `domains.py`)
- Produces: `DOMAIN_RISHIS: frozenset[str]`, `SERVICE_RISHIS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

Create or append to `tests/council/test_domains.py`:

```python
"""Which personas may answer, and which may only compute.

The split is not new information -- it is already latent in RISHI_LIFE_DOMAINS, where
vyom and ritam rate every domain exactly MEDIUM and tejan rates every domain LOW-MEDIUM,
so none of the three owns anything. These tests pin that reading down so a future edit to
the weights cannot silently promote a service Rishi to a voice.
"""

from rishivan.council.domains import (
    DOMAIN_RISHIS,
    LIFE_DOMAIN_KEYS,
    RISHI_LIFE_DOMAINS,
    SERVICE_RISHIS,
)


def test_the_two_classes_partition_every_persona():
    assert DOMAIN_RISHIS | SERVICE_RISHIS == set(RISHI_LIFE_DOMAINS)
    assert not (DOMAIN_RISHIS & SERVICE_RISHIS)


def test_a_service_rishi_owns_no_life_domain():
    """The definition of the class: no HIGH weight anywhere."""
    for rishi in SERVICE_RISHIS:
        weights = RISHI_LIFE_DOMAINS[rishi]
        assert max(weights.values(), default=0.0) < 1.0, rishi


def test_every_domain_rishi_owns_at_least_one_life_domain():
    for rishi in DOMAIN_RISHIS:
        weights = RISHI_LIFE_DOMAINS[rishi]
        assert max(weights.values(), default=0.0) == 1.0, rishi


def test_every_life_domain_has_a_domain_rishi_that_owns_it():
    """ER 20: no orphan questions. Every domain must reach a persona that can SPEAK,
    not merely one that can contribute."""
    for domain in LIFE_DOMAIN_KEYS:
        owners = [
            r for r in DOMAIN_RISHIS
            if RISHI_LIFE_DOMAINS[r].get(domain, 0.0) == 1.0
        ]
        assert owners, domain
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/council/test_domains.py -v`
Expected: FAIL — `ImportError: cannot import name 'DOMAIN_RISHIS'`

- [ ] **Step 3: Write minimal implementation**

Append to `rishivan/council/domains.py`, after the `RISHI_LIFE_DOMAINS` docstring:

```python
SERVICE_RISHIS: frozenset[str] = frozenset({"vyom", "ritam", "tejan"})
"""Personas that compute for another Rishi and never speak.

Not a new distinction -- the table above already says it. These three rate every life
domain uniformly (vyom and ritam MEDIUM, tejan LOW-MEDIUM) because they are technique
lenses, not life domains: cosmic patterns, timing, remedies. The client agrees --
ER 13 calls Muhurta a "cross-domain timing service" and BP 17 puts remedies in a
separate corpus.

Letting one of them answer defeats the coverage gate: a persona rating all eight
domains MEDIUM gates nothing, so `ritam` answering "when will I marry?" meant PREMA's
houses filtered no rules at all.
"""

DOMAIN_RISHIS: frozenset[str] = frozenset(RISHI_LIFE_DOMAINS) - SERVICE_RISHIS
"""Personas that own at least one life domain and may therefore answer."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/council/test_domains.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/domains.py tests/council/test_domains.py
git commit -m "feat(council): split personas into domain voices and service computers"
```

---

### Task 2: The life domain picks the persona

**Files:**
- Modify: `rishivan/council/domains.py` (append)
- Test: `tests/council/test_domains.py` (append)

**Interfaces:**
- Consumes: `DOMAIN_RISHIS`, `RISHI_LIFE_DOMAINS`, `LIFE_DOMAIN_KEYS` (Task 1 and existing)
- Produces: `primary_rishi_for(domain: str | None, *, classifier_pick: str | None = None) -> str`

Spec Section 2. Today `route_question()` picks the life domain (which gates rules) and the classifier LLM picks the persona (which owns the voice), independently — in the billionaire reading they agreed by luck. This makes the domain authoritative and demotes the LLM to a tiebreak.

- [ ] **Step 1: Write the failing test**

Append to `tests/council/test_domains.py`:

```python
from rishivan.council.domains import primary_rishi_for


def test_a_single_owner_domain_resolves_to_that_persona():
    assert primary_rishi_for("artha") == "dhruvan"
    assert primary_rishi_for("prema") == "medhan"
    assert primary_rishi_for("karma") == "dhruvan"
    assert primary_rishi_for("vansh") == "medhan"
    assert primary_rishi_for("aarogya") == "medhan"
    assert primary_rishi_for("yatra") == "dhruvan"


def test_a_two_owner_domain_lets_the_classifier_break_the_tie():
    """ATMA is owned HIGH by both agam and tattvan; DHARMA by agam and pragnav."""
    assert primary_rishi_for("atma", classifier_pick="tattvan") == "tattvan"
    assert primary_rishi_for("atma", classifier_pick="agam") == "agam"
    assert primary_rishi_for("dharma", classifier_pick="pragnav") == "pragnav"


def test_a_tie_ignores_a_classifier_pick_that_does_not_own_the_domain():
    """The LLM breaks ties; it does not override coverage. `medhan` owns no ATMA."""
    assert primary_rishi_for("atma", classifier_pick="medhan") in {"agam", "tattvan"}


def test_a_tie_is_deterministic_without_a_classifier_pick():
    assert primary_rishi_for("atma") == primary_rishi_for("atma")
    assert primary_rishi_for("atma") in {"agam", "tattvan"}


def test_an_unrouted_question_falls_back_to_a_domain_rishi():
    """Spec Section 2 step 5. Never vyom -- an all-MEDIUM fallback gates nothing."""
    assert primary_rishi_for(None) == "tattvan"
    assert primary_rishi_for(None, classifier_pick="dhruvan") == "dhruvan"


def test_a_service_rishi_is_never_returned():
    for domain in (*LIFE_DOMAIN_KEYS, None):
        for pick in ("vyom", "ritam", "tejan", None):
            assert primary_rishi_for(domain, classifier_pick=pick) in DOMAIN_RISHIS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/council/test_domains.py -v`
Expected: FAIL — `ImportError: cannot import name 'primary_rishi_for'`

- [ ] **Step 3: Write minimal implementation**

Append to `rishivan/council/domains.py`:

```python
FALLBACK_RISHI = "tattvan"
"""Who speaks when routing finds no life domain.

`tattvan` because ATMA is the broadest domain -- "who is this person" is answerable from
any chart. Deliberately NOT the previous default `vyom`, which rates all eight domains
MEDIUM and so gates no rules at all.
"""


def primary_rishi_for(
    domain: str | None, *, classifier_pick: str | None = None
) -> str:
    """The persona that answers a question routed to `domain`.

    The domain is authoritative because it is what the coverage gate uses; the
    classifier's own pick only breaks a tie between two personas that both own the
    domain outright. Before this, routing chose the domain and the classifier chose the
    voice independently, so the rules could be gated on ARTHA while `ritam` spoke.
    """
    pick = (classifier_pick or "").lower() or None
    owners = [
        rishi
        for rishi in sorted(DOMAIN_RISHIS)
        if RISHI_LIFE_DOMAINS[rishi].get((domain or "").lower(), 0.0) == DOMAIN_HIGH
    ]
    if not owners:
        return pick if pick in DOMAIN_RISHIS else FALLBACK_RISHI
    if pick in owners:
        return pick
    return owners[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/council/test_domains.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/domains.py tests/council/test_domains.py
git commit -m "feat(council): the routed life domain picks the voice, LLM only breaks ties"
```

---

### Task 3: Routing gains real secondaries

**Files:**
- Modify: `rishivan/council/routing.py` (add `merge_supporting`, around line 216)
- Test: `tests/council/test_routing.py` (append)

**Interfaces:**
- Consumes: `Routing`, `MAX_DOMAINS`, `QUESTION_KEYWORDS` (existing in `routing.py`); `RISHI_LIFE_DOMAINS`, `SERVICE_RISHIS` (Task 1)
- Produces: `merge_supporting(routing: Routing, supporting_rishis: list[str]) -> Routing`

Spec Section 4, "Prerequisite, in scope". Verified today: `route_question("Will I become a billionaire?")` returns `secondary=()` because only the single word "billionaire" matches. ER §12 prescribes ARTHA primary with KARMA / ATMA / YATRA secondary. Without this, domain contributors almost never fire and the whole change is inert.

The second source is the classifier's existing `supporting_rishis` field (`classifier.py:158`, surfaced at `classifier.py:260`) — already computed, no new call. Those are *personas*, so they must be mapped back to life domains before merging.

- [ ] **Step 1: Write the failing test**

Append to `tests/council/test_routing.py`:

```python
from rishivan.council.routing import MAX_DOMAINS, merge_supporting


def test_a_single_keyword_question_gains_secondaries_from_the_classifier():
    """The gap this exists to close: 'billionaire' matches one phrase, so the keyword
    table alone returns no secondary at all, and ER 12 asks for three."""
    base = route_question("Will I become a billionaire?")
    assert base.primary == "artha"
    assert base.secondary == ()

    merged = merge_supporting(base, ["tattvan", "dhruvan"])
    assert merged.primary == "artha"
    assert "atma" in merged.secondary


def test_merging_never_displaces_the_keyword_primary():
    merged = merge_supporting(route_question("Will I marry?"), ["dhruvan"])
    assert merged.primary == "prema"


def test_a_supporting_persona_that_repeats_the_primary_is_dropped():
    merged = merge_supporting(route_question("Will I be wealthy?"), ["dhruvan"])
    assert "artha" not in merged.secondary


def test_service_personas_contribute_no_life_domain():
    """vyom and ritam rate all eight domains MEDIUM -- mapping them back would add
    every domain as a secondary and make the cap meaningless."""
    merged = merge_supporting(route_question("Will I marry?"), ["vyom", "ritam"])
    assert merged.secondary == ()


def test_the_minimum_set_cap_still_holds():
    """ER 12: 'Do not invoke all eight by default.'"""
    merged = merge_supporting(
        route_question("Will I become a billionaire?"),
        ["tattvan", "medhan", "agam", "pragnav", "dhruvan"],
    )
    assert len(merged.secondary) <= MAX_DOMAINS - 1


def test_merging_preserves_application_and_universes():
    base = route_question("When will I marry?")
    merged = merge_supporting(base, ["dhruvan"])
    assert merged.application == base.application == "timing"
    assert merged.universes == base.universes


def test_an_unrouted_question_stays_unrouted():
    """ER 20: a question outside the eight domains must not be rescued into one by a
    persona guess."""
    base = route_question("What is the airspeed velocity of an unladen swallow?")
    merged = merge_supporting(base, ["dhruvan", "tattvan"])
    assert merged.primary is None
    assert merged.unsupported is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/council/test_routing.py -v`
Expected: FAIL — `ImportError: cannot import name 'merge_supporting'`

- [ ] **Step 3: Write minimal implementation**

Append to `rishivan/council/routing.py`:

```python
def merge_supporting(routing: Routing, supporting_rishis: list[str]) -> Routing:
    """Add life domains implied by the classifier's supporting personas.

    The keyword table alone cannot produce secondaries on a short question: "Will I
    become a billionaire?" matches one phrase, so it routed to ARTHA with nothing
    beside it, while ER 12 asks for KARMA, ATMA and YATRA as well. The classifier
    already returns `supporting_rishis` on every call, so this is a second source at no
    extra cost.

    Those are PERSONAS, so they are mapped back through the weighted table. Only
    domains a persona owns outright count -- a service persona rates all eight MEDIUM,
    and admitting those would add every domain and make MAX_DOMAINS meaningless.

    An unrouted question stays unrouted (ER 20): a persona guess is not evidence that
    the question falls inside the supported boundary.
    """
    from rishivan.council.domains import DOMAIN_HIGH, RISHI_LIFE_DOMAINS

    if routing.primary is None:
        return routing

    extra: list[str] = []
    for rishi in supporting_rishis or []:
        weights = RISHI_LIFE_DOMAINS.get(str(rishi).strip().lower(), {})
        for domain, weight in weights.items():
            if weight < DOMAIN_HIGH:
                continue
            if domain == routing.primary or domain in routing.secondary:
                continue
            if domain not in extra:
                extra.append(domain)

    if not extra:
        return routing

    secondary = (*routing.secondary, *extra)[: MAX_DOMAINS - 1]
    return Routing(
        primary=routing.primary,
        secondary=secondary,
        universes=routing.universes,
        application=routing.application,
        scores=routing.scores,
        matched=routing.matched,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/council/test_routing.py -v`
Expected: all pass, including the pre-existing §12 tests

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/routing.py tests/council/test_routing.py
git commit -m "fix(routing): secondaries were empty on most questions, collapsing ER 12"
```

---

### Task 4: Publish `remedies` to the rule payload

**Files:**
- Modify: `scripts/embed_rules.py:168-181` (the `metadatas` dict)
- Modify: `rishivan/rag/rules.py` (`RuleHit` around line 78, `_payload_to_hit` around line 100)
- Test: `tests/rag/test_rules.py` (append)

**Interfaces:**
- Consumes: `RuleHit`, `_payload_to_hit` (existing)
- Produces: `RuleHit.remedies: list[dict]`

Spec Section 3. `knowledge/compile/persist.py:94` already writes a `remedies` list onto every compiled rule (extractor Example 4: *"recitation of hymns in praise of Lord Shiva, charity of white cow and silver"*). But `scripts/embed_rules.py` never copies it into the Qdrant payload and `rag/rules.py` never reads it — so it is unreachable at query time. Without this, the tejan contributor in Task 6 can only ever return `None`.

This is the same reader/writer gap `test_every_payload_key_retrieval_reads_is_a_key_the_embedder_writes` (`tests/rag/test_rules.py:397`) was written to catch. That test only catches keys the reader reads, so it cannot see a field neither side handles — hence the explicit test below.

- [ ] **Step 1: Write the failing test**

Append to `tests/rag/test_rules.py`:

```python
def test_remedies_survive_the_store_boundary():
    """BP 6 lists REMEDIES as a Koonji field and the extractor populates it, but it was
    written to Postgres and dropped at the Qdrant boundary -- unreachable at query time,
    exactly as `exceptions` and `modifiers` were."""
    remedy = [{"kind": "mantra", "detail": "hymns to Shiva"}]
    payload = {
        "rule_key": "r",
        "condition": json.dumps(CONDITION),
        "remedies": json.dumps(remedy),
    }
    hit = _payload_to_hit(payload, relevance=1.0)
    assert hit is not None
    assert hit.remedies == remedy


def test_a_rule_with_no_remedies_gets_an_empty_list_not_none():
    hit = _payload_to_hit(
        {"rule_key": "r", "condition": json.dumps(CONDITION)}, relevance=1.0
    )
    assert hit is not None
    assert hit.remedies == []


def test_the_embedder_writes_the_remedies_key():
    """The generic contract test cannot catch this: it compares keys the READER reads,
    so a field neither side handles passes silently."""
    from pathlib import Path

    writer = Path("scripts/embed_rules.py").read_text()
    assert '"remedies"' in writer
```

Add `_payload_to_hit` to the imports at the top of `tests/rag/test_rules.py` if it is not already there.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/rag/test_rules.py -k remed -v`
Expected: FAIL — `AttributeError: 'RuleHit' object has no attribute 'remedies'`

- [ ] **Step 3: Write minimal implementation**

In `rishivan/rag/rules.py`, add a field to `RuleHit` after `merged_from`:

```python
    remedies: list[dict] = field(default_factory=list)
    """BP 6's REMEDIES field. Extracted and stored in Postgres from the start, but
    dropped at the Qdrant boundary until now, so the remedy contributor had nothing to
    read."""
```

In `_payload_to_hit`, add to the `RuleHit(...)` call:

```python
            remedies=json.loads(payload.get("remedies") or "[]"),
```

In `scripts/embed_rules.py`, add to the `metadatas` dict beside `"exceptions"`:

```python
            # BP 6 lists REMEDIES alongside MODIFIERS and EXCEPTIONS. Compiled onto the
            # rule by `knowledge/compile/persist.py` and stored in Postgres, but never
            # published here -- so no consumer could reach it.
            "remedies": json.dumps((rule.effect or {}).get("remedies") or []),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/rag/test_rules.py -v`
Expected: all pass, including `test_every_payload_key_retrieval_reads_is_a_key_the_embedder_writes`

- [ ] **Step 5: Commit**

```bash
git add rishivan/rag/rules.py scripts/embed_rules.py tests/rag/test_rules.py
git commit -m "fix(rag): remedies were extracted and stored but never published"
```

**Note for the reviewer:** this makes the *code* able to carry remedies. Existing published points do not have the field until `scripts/embed_rules.py` is re-run, which revokes nothing but does cost a re-embed. `_payload_to_hit` defaults to `[]`, so an un-refreshed collection keeps working — tejan just returns `None`.

---

### Task 5: The `ContributorReport` type and the domain contributor

**Files:**
- Create: `rishivan/council/contributors.py`
- Test: `tests/council/test_contributors.py`

**Interfaces:**
- Consumes: `RuleHit` (`rag/rules.py`), `concepts_of` (`knowledge/concepts.py`), `CONSTITUTIONS` (`council/constitution.py`), `primary_rishi_for` (Task 2)
- Produces:
  - `ContributorReport(rishi: str, computed: dict[str, str], rules: tuple[RuleHit, ...], note: str = "")`
  - `ContributorReport.is_empty -> bool`
  - `domain_contribution(domain: str, applicable: list[RuleHit]) -> ContributorReport | None`

- [ ] **Step 1: Write the failing test**

Create `tests/council/test_contributors.py`:

```python
"""Contributors compute evidence for the Rishi who speaks.

Deterministic by design (spec Section 3): N generation calls before the first token is
latency the reading cannot absorb, and a generated briefing paraphrases -- the same
failure that already forces nakshatra names to be printed outside the Rishi's voice.
"""

from rishivan.council.contributors import ContributorReport, domain_contribution
from rishivan.rag.rules import RuleHit

LAGNA_RULE = RuleHit(
    rule_key="lagna",
    condition={"atoms": [{"type": "lord_of_house_in_house", "lord_of": 1, "house": 7}]},
    effects=[{"polarity": "positive", "statement": "the native is resolute"}],
    source={"chapter": "12", "verse_ref": "2"},
    relevance=0.0,
)
CAREER_RULE = RuleHit(
    rule_key="career",
    condition={"atoms": [{"type": "lord_of_house_in_house", "lord_of": 10, "house": 11}]},
    effects=[{"polarity": "positive", "statement": "gains through profession"}],
    source={"chapter": "34", "verse_ref": "5"},
    relevance=0.0,
)


def test_a_domain_contributor_returns_only_rules_inside_its_coverage():
    """ATMA's coverage is house 1 alone, so the 10th-house rule must not appear."""
    report = domain_contribution("atma", [LAGNA_RULE, CAREER_RULE])
    assert report is not None
    assert [r.rule_key for r in report.rules] == ["lagna"]


def test_the_report_names_the_persona_that_owns_the_domain():
    report = domain_contribution("atma", [LAGNA_RULE])
    assert report.rishi in {"agam", "tattvan"}
    report = domain_contribution("karma", [CAREER_RULE])
    assert report.rishi == "dhruvan"


def test_a_contributor_with_nothing_in_coverage_returns_none():
    """Spec Section 3: an empty report never reaches the prompt, so a thin corpus
    cannot pad an answer with noise."""
    assert domain_contribution("atma", [CAREER_RULE]) is None


def test_a_contributor_given_no_rules_returns_none():
    assert domain_contribution("atma", []) is None


def test_an_unknown_domain_returns_none_rather_than_everything():
    assert domain_contribution("nonsense", [LAGNA_RULE, CAREER_RULE]) is None


def test_an_empty_report_is_empty():
    assert ContributorReport(rishi="ritam", computed={}, rules=()).is_empty is True
    assert ContributorReport(
        rishi="ritam", computed={"Mahadasha": "Saturn"}, rules=()
    ).is_empty is False
    assert ContributorReport(
        rishi="tattvan", computed={}, rules=(LAGNA_RULE,)
    ).is_empty is False


def test_a_report_is_frozen():
    import dataclasses
    import pytest

    report = ContributorReport(rishi="ritam", computed={}, rules=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.rishi = "vyom"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/council/test_contributors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rishivan.council.contributors'`

- [ ] **Step 3: Write minimal implementation**

Create `rishivan/council/contributors.py`:

```python
"""Evidence one Rishi computes for another.

Eight Rishis 12 asks for a primary Rishi with supporting ones, but a supporting Rishi
that SPEAKS produces two opinions rather than one grounded answer. Here a supporting
Rishi computes instead: it reports what it alone can establish -- the running dasha, the
rules inside its own coverage -- and the primary writes the single reply.

Every contributor is deterministic. No LLM call, so a report is reproducible, unit
testable, and cannot paraphrase a computed value into flavour text.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rishivan.council.constitution import CONSTITUTIONS
from rishivan.council.domains import primary_rishi_for
from rishivan.knowledge.concepts import concepts_of
from rishivan.rag.rules import RuleHit


@dataclass(frozen=True)
class ContributorReport:
    """What one supporting Rishi established, ready to label in the primary's prompt."""

    rishi: str
    computed: dict[str, str] = field(default_factory=dict)
    """Label -> value. Ground truth, copied verbatim into the prompt, never paraphrased."""
    rules: tuple[RuleHit, ...] = ()
    note: str = ""
    """One templated sentence. Never generated."""

    @property
    def is_empty(self) -> bool:
        return not self.computed and not self.rules


def domain_contribution(
    domain: str, applicable: list[RuleHit]
) -> ContributorReport | None:
    """Rules a secondary life domain can add, gated on ITS OWN coverage.

    The gate is the same one the primary's rules pass through -- a rule whose subject
    house sits outside the domain's houses is not evidence for that domain, whatever its
    affinity tag says. So a secondary broadens the houses consulted without loosening
    the standard on any of them.
    """
    constitution = CONSTITUTIONS.get((domain or "").lower())
    if constitution is None:
        return None

    houses = constitution.houses
    inside = tuple(
        rule
        for rule in applicable
        if concepts_of(rule.condition).subject_houses & houses
    )
    if not inside:
        return None
    return ContributorReport(
        rishi=primary_rishi_for(domain),
        rules=inside,
        note=f"{len(inside)} rules on the houses {domain.upper()} owns",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/council/test_contributors.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/contributors.py tests/council/test_contributors.py
git commit -m "feat(council): ContributorReport and the domain contributor"
```

---

### Task 6: The three service contributors

**Files:**
- Modify: `rishivan/council/contributors.py` (append)
- Test: `tests/council/test_contributors.py` (append)

**Interfaces:**
- Consumes: `ContributorReport` (Task 5), `current_periods` (`chart/dasha.py`, returns `dict[str, Period | None]` with keys `maha`/`antar`/`pratyantar`; each `Period` has `.lord: str` and `.end: datetime`), `RuleHit.rule_category`, `RuleHit.remedies` (Task 4)
- Produces:
  - `timing_contribution(chart, applicable, *, when=None) -> ContributorReport | None`
  - `pattern_contribution(chart, applicable) -> ContributorReport | None`
  - `remedy_contribution(applicable) -> ContributorReport | None`

- [ ] **Step 1: Write the failing test**

Append to `tests/council/test_contributors.py`:

```python
from datetime import datetime

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.council.contributors import (
    pattern_contribution,
    remedy_contribution,
    timing_contribution,
)

CHART = compute_chart(
    BirthData(1990, 1, 1, 6, 29, 0, 5.5, 28.6139, 77.2090, "New Delhi")
)
WHEN = datetime(2026, 8, 20, 12, 0)

TIMING_RULE = RuleHit(
    rule_key="t", condition={"atoms": []}, effects=[], source={},
    relevance=0.0, rule_category="timing",
)
REMEDY_RULE = RuleHit(
    rule_key="rem", condition={"atoms": []}, effects=[], source={},
    relevance=0.0, remedies=[{"kind": "mantra", "detail": "hymns to Shiva"}],
)


def test_the_timing_contributor_reports_the_running_periods():
    report = timing_contribution(CHART, [], when=WHEN)
    assert report is not None
    assert report.rishi == "ritam"
    assert "Mahadasha" in report.computed
    # Verified against chart/dasha.py for this chart and date.
    assert report.computed["Mahadasha"].startswith("Saturn until 2037-06-07")


def test_the_timing_contributor_carries_only_timing_rules():
    report = timing_contribution(CHART, [TIMING_RULE, LAGNA_RULE], when=WHEN)
    assert [r.rule_key for r in report.rules] == ["t"]


def test_the_pattern_contributor_reports_the_janma_nakshatra():
    report = pattern_contribution(CHART, [])
    assert report is not None
    assert report.rishi == "vyom"
    assert report.computed["Janma nakshatra"] == "Dhanishta"


def test_the_remedy_contributor_returns_none_when_no_rule_carries_one():
    """Not a corpus gap -- remedies are extracted. Before Task 4 they were never
    published, so this returned None on every chart."""
    assert remedy_contribution([LAGNA_RULE, CAREER_RULE]) is None


def test_the_remedy_contributor_reports_a_published_remedy():
    report = remedy_contribution([LAGNA_RULE, REMEDY_RULE])
    assert report is not None
    assert report.rishi == "tejan"
    assert [r.rule_key for r in report.rules] == ["rem"]


def test_no_service_contributor_claims_a_domain_persona():
    reports = [
        timing_contribution(CHART, [], when=WHEN),
        pattern_contribution(CHART, []),
        remedy_contribution([REMEDY_RULE]),
    ]
    assert {r.rishi for r in reports if r} == {"ritam", "vyom", "tejan"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/council/test_contributors.py -v`
Expected: FAIL — `ImportError: cannot import name 'timing_contribution'`

- [ ] **Step 3: Write minimal implementation**

Append to `rishivan/council/contributors.py`:

```python
def timing_contribution(
    chart, applicable: list[RuleHit], *, when=None
) -> ContributorReport | None:
    """Ritam: which dasha periods are running, and the rules that activate a promise.

    ER 13 calls Muhurta and timing a cross-domain service, which is exactly this shape:
    every domain's 4-11 protocol ends in a Dasha step, so the timing values belong in
    any reading that asks WHEN -- supplied to whoever owns the subject, not spoken by
    Ritam directly.
    """
    from datetime import datetime

    from rishivan.chart.dasha import current_periods

    periods = current_periods(chart, when or datetime.now())
    computed = {
        label: f"{period.lord} until {period.end.date().isoformat()}"
        for label, period in (
            ("Mahadasha", periods.get("maha")),
            ("Antardasha", periods.get("antar")),
            ("Pratyantardasha", periods.get("pratyantar")),
        )
        if period is not None
    }
    rules = tuple(r for r in applicable if r.rule_category == "timing")
    report = ContributorReport(
        rishi="ritam",
        computed=computed,
        rules=rules,
        note=f"{len(rules)} timing rules true of this chart" if rules else "",
    )
    return None if report.is_empty else report


def pattern_contribution(chart, applicable: list[RuleHit]) -> ContributorReport | None:
    """Vyom: the chart's pattern layer -- nakshatra and conjunctions.

    Every 4-11 protocol has a "major combinations" step, and yoga recognition does not
    exist in this repo. Reporting only what IS computed keeps the gap visible rather
    than letting the primary infer combinations nobody verified.
    """
    moon = chart.planets["Moon"]
    computed = {"Janma nakshatra": f"{moon.nakshatra}"}
    rules = tuple(
        r for r in applicable
        if any(
            atom.get("type") in {"conjunct", "planet_in_nakshatra"}
            for atom in (r.condition.get("atoms") or [])
        )
    )
    report = ContributorReport(
        rishi="vyom",
        computed=computed,
        rules=rules,
        note="yoga recognition is not implemented; combinations are unverified",
    )
    return None if report.is_empty else report


def remedy_contribution(applicable: list[RuleHit]) -> ContributorReport | None:
    """Tejan: rules that carry their own remedy.

    BP 17 keeps remedies in a separate corpus and out of the Rishi set, which is why
    Tejan contributes rather than speaks. A remedy is only ever offered attached to the
    rule that diagnosed the affliction -- detached, it is advice with no evidence.
    """
    rules = tuple(r for r in applicable if r.remedies)
    if not rules:
        return None
    return ContributorReport(
        rishi="tejan",
        rules=rules,
        note=f"{len(rules)} of the matched rules state their own remedy",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/council/test_contributors.py -v`
Expected: 13 passed

If `test_the_pattern_contributor_reports_the_janma_nakshatra` fails on capitalisation, read the actual value from `chart.planets["Moon"].nakshatra` and fix the *test* to match the engine — the engine's spelling is ground truth.

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/contributors.py tests/council/test_contributors.py
git commit -m "feat(council): ritam, vyom and tejan compute instead of speaking"
```

---

### Task 7: Contributor selection

**Files:**
- Modify: `rishivan/council/contributors.py` (append)
- Test: `tests/council/test_contributors.py` (append)

**Interfaces:**
- Consumes: all four contributor functions (Tasks 5–6), `Routing` (`council/routing.py`)
- Produces: `gather(chart, applicable, *, routing, question, when=None) -> tuple[ContributorReport, ...]`

Spec Section 4. Triggers are deterministic. `vyom` always fires because every ER §4–11 protocol contains a combinations step and a Nakshatra step — it is not selective and must not pretend to be.

**Remedy questions:** routing must NOT gain remedy keywords — a remedy is not a life domain, and making "remedy" compete with "health" for ownership would repeat the `book_domain` category error. The question's subject routes it; tejan contributes regardless. Verified: *"What remedies should I do for my health?"* → `aarogya`; *"What remedies for Saturn?"* → `None` → `tattvan` by fallback.

- [ ] **Step 1: Write the failing test**

Append to `tests/council/test_contributors.py`:

```python
from rishivan.council.contributors import gather
from rishivan.council.routing import route_question


def test_a_timing_question_invokes_ritam():
    routing = route_question("When will I marry?")
    reports = gather(CHART, [TIMING_RULE], routing=routing,
                     question="When will I marry?", when=WHEN)
    assert "ritam" in {r.rishi for r in reports}


def test_a_potential_question_does_not_invoke_ritam():
    """BP 8 rule 2: potential and timing are different reasoning problems. A 'whether'
    question must not be handed a period it did not ask about."""
    routing = route_question("Will I marry?")
    reports = gather(CHART, [TIMING_RULE], routing=routing,
                     question="Will I marry?", when=WHEN)
    assert "ritam" not in {r.rishi for r in reports}


def test_vyom_always_contributes():
    for question in ("Will I marry?", "What career suits me?", "Will I be wealthy?"):
        routing = route_question(question)
        reports = gather(CHART, [], routing=routing, question=question, when=WHEN)
        assert "vyom" in {r.rishi for r in reports}, question


def test_a_secondary_domain_contributes_its_own_rules():
    """The billionaire case: ER 12 asks for ATMA beside ARTHA, so tattvan or agam must
    appear as a contributor."""
    from rishivan.council.routing import merge_supporting

    routing = merge_supporting(
        route_question("Will I become a billionaire?"), ["tattvan"]
    )
    reports = gather(CHART, [LAGNA_RULE, CAREER_RULE], routing=routing,
                     question="Will I become a billionaire?", when=WHEN)
    assert {"tattvan", "agam"} & {r.rishi for r in reports}


def test_the_primary_domain_is_never_also_a_contributor():
    """Its rules are the primary's own evidence, not a contribution."""
    routing = route_question("What career suits me?")
    reports = gather(CHART, [CAREER_RULE], routing=routing,
                     question="What career suits me?", when=WHEN)
    assert "dhruvan" not in {r.rishi for r in reports}


def test_no_empty_report_is_ever_returned():
    routing = route_question("Will I marry?")
    reports = gather(CHART, [], routing=routing, question="Will I marry?", when=WHEN)
    assert all(not r.is_empty for r in reports)


def test_a_remedy_question_routes_by_its_subject_not_by_the_word_remedy():
    assert route_question("What remedies should I do for my health?").primary == "aarogya"
    assert route_question("What remedies for Saturn?").primary is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/council/test_contributors.py -v`
Expected: FAIL — `ImportError: cannot import name 'gather'`

- [ ] **Step 3: Write minimal implementation**

Append to `rishivan/council/contributors.py`:

```python
DASHA_WORDS = ("dasha", "mahadasha", "antardasha", "bhukti", "pratyantar")


def gather(
    chart, applicable: list[RuleHit], *, routing, question: str, when=None
) -> tuple[ContributorReport, ...]:
    """Every non-empty contribution for this question, primary's own rules excluded.

    Triggers are deterministic so a reading is reproducible. `vyom` fires on every
    question because every 4-11 protocol contains a combinations step and a Nakshatra
    step -- pretending that is selective would be a lie about what it does.
    """
    text = (question or "").lower()
    reports: list[ContributorReport | None] = []

    if routing.application == "timing" or any(word in text for word in DASHA_WORDS):
        reports.append(timing_contribution(chart, applicable, when=when))

    reports.append(pattern_contribution(chart, applicable))
    reports.append(remedy_contribution(applicable))

    for domain in routing.secondary:
        reports.append(domain_contribution(domain, applicable))

    return tuple(r for r in reports if r is not None and not r.is_empty)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/council/test_contributors.py -v`
Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/contributors.py tests/council/test_contributors.py
git commit -m "feat(council): deterministic contributor selection"
```

---

### Task 8: Coverage-ordered facts and labelled evidence in the prompt

**Files:**
- Modify: `rishivan/council/prompts.py` (`rule_context` at 214, `_natal_context` at 115, `build_rishi_prompt` at 238)
- Test: `tests/council/test_prompts.py` (create if absent)

**Interfaces:**
- Consumes: `ContributorReport` (Task 5), `CONSTITUTIONS`, `authority_tier`/`school_for` (`council/source_matrix.py`), `RuleHit.tier`, `RuleHit.school`
- Produces:
  - `coverage_facts(chart_facts: list[str], domain: str | None) -> str`
  - `contributor_context(reports: tuple[ContributorReport, ...]) -> str`
  - `build_rishi_prompt(..., life_domain: str | None = None, contributors: tuple = ())`

Spec Section 5. Two existing defects close here. First, ATMA's rules are gated to house 1 and then all twelve house lords arrive as prose, so the model reasons from evidence no rule licensed — nothing is deleted (every §4–11 protocol ends in whole-chart synthesis), it is demoted and labelled. Second, in the billionaire reading the model named S3 *Hindu Predictive Astrology* a "classic text" while S0 BPHS sat unnamed in the same page set; BP §8 rule 4 has nothing to act on when tier is invisible.

- [ ] **Step 1: Write the failing test**

Create `tests/council/test_prompts.py`:

```python
"""What the primary Rishi is allowed to see, and in what order.

BP 8 rule 4 is a hierarchy of evidence. It cannot hold when a flat fact dump sits beside
cited rules with equal visibility, or when an S3 source and an S0 source look identical.
"""

from rishivan.council.contributors import ContributorReport
from rishivan.council.prompts import contributor_context, coverage_facts, rule_context
from rishivan.rag.rules import RuleHit

FACTS = [
    "Ascendant (Lagna) is Cancer.",
    "The 1st house (self, body, personality) is ruled by Moon, placed in the 8th house.",
    "The 10th house (career, status, public life) is ruled by Mars, placed in the 5th house.",
]


def test_facts_inside_coverage_come_before_the_wider_chart():
    text = coverage_facts(FACTS, "atma")
    assert text.index("WITHIN YOUR COVERAGE") < text.index("WIDER CONTEXT")


def test_a_fact_about_an_owned_house_lands_inside_coverage():
    """ATMA owns house 1 alone."""
    inside = coverage_facts(FACTS, "atma").split("WIDER CONTEXT")[0]
    assert "1st house" in inside
    assert "10th house" not in inside


def test_a_planet_the_constitution_owns_lands_inside_coverage():
    """ATMA owns the Sun and Moon outright (ER 4). A house-only reading of coverage
    filed "Sun is in ..." under the wider chart -- demoting the single most important
    fact for a personality question."""
    facts = [*FACTS, "Sun is in Sagittarius in the 6th house (Purva Ashadha, pada 2)."]
    inside = coverage_facts(facts, "atma").split("WIDER CONTEXT")[0]
    assert "Sun is in Sagittarius" in inside


def test_a_planet_fact_is_not_filed_by_where_the_planet_sits():
    """The 6th is the Sun's location, not the fact's subject. ATMA does not own house 6,
    but it does own the Sun, and the fact must not be claimed by house 6 for a domain
    that owns that house instead."""
    facts = ["Sun is in Sagittarius in the 6th house (Purva Ashadha, pada 2)."]
    inside = coverage_facts(facts, "aarogya").split("WIDER CONTEXT")[0]
    assert "Sun is in Sagittarius" not in inside


def test_the_chart_framework_is_always_inside_coverage():
    """Step 1 of every 4-11 protocol is "chart framework"."""
    for domain in ("atma", "artha", "prema"):
        inside = coverage_facts(FACTS, domain).split("WIDER CONTEXT")[0]
        assert "Ascendant (Lagna) is Cancer." in inside, domain


def test_no_fact_is_dropped():
    """Every 4-11 protocol ends in whole-chart synthesis, so demote -- never delete."""
    text = coverage_facts(FACTS, "atma")
    for fact in FACTS:
        assert fact in text


def test_an_unrouted_question_gets_the_facts_unsplit():
    text = coverage_facts(FACTS, None)
    assert "WIDER CONTEXT" not in text
    for fact in FACTS:
        assert fact in text


def test_a_contributor_block_names_the_rishi_and_its_values():
    report = ContributorReport(
        rishi="ritam",
        computed={"Mahadasha": "Saturn until 2037-06-07"},
        rules=(),
        note="3 timing rules true of this chart",
    )
    text = contributor_context((report,))
    assert "RITAM" in text
    assert "Saturn until 2037-06-07" in text
    assert "3 timing rules" in text


def test_no_contributors_renders_nothing():
    assert contributor_context(()) == ""


def test_a_rule_carries_its_tier_and_school():
    """The billionaire reading named an S3 source a 'classic text' while S0 BPHS sat
    unnamed beside it. BP 8 rule 5 also forbids mixing schools silently."""
    hit = RuleHit(
        rule_key="r", condition={}, effects=[{"polarity": "positive", "statement": "x"}],
        source={"chapter": "1", "verse_ref": "1", "translation": "t"},
        relevance=1.0, tier="S3", school="prashna",
    )
    text = rule_context([hit])
    assert "S3" in text
    assert "prashna" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/council/test_prompts.py -v`
Expected: FAIL — `ImportError: cannot import name 'coverage_facts'`

- [ ] **Step 3: Write minimal implementation**

In `rishivan/council/prompts.py`, add before `rule_context`:

```python
import re

_SUBJECT_HOUSE = re.compile(r"^The (\d{1,2})(?:st|nd|rd|th) house\b")
"""The house a house-lord fact is ABOUT.

Anchored at the start on purpose. A planet fact reads "Sun is in Sagittarius in the 6th
house", where the 6th is where the planet SITS, not what the fact is about -- the same
subject-versus-location distinction `knowledge/concepts.py` makes for rule atoms. An
unanchored pattern would file the Sun under house 6.
"""

_FRAMEWORK = ("Ascendant (Lagna)", "Birth nakshatra")
"""Facts every 4-11 protocol opens with -- step 1 is always "chart framework"."""


def coverage_facts(chart_facts: list[str], domain: str | None) -> str:
    """Chart facts ordered by the answering Rishi's own coverage.

    The coverage gate drops rules whose subject house sits outside the routed domain,
    then the prompt handed over all twelve house lords anyway -- so the model could
    reason from placements no rule licensed, which defeats the gate. Nothing is
    dropped here: every 4-11 protocol ends in whole-chart synthesis, so the wider chart
    is demoted and labelled rather than withheld.
    """
    from rishivan.council.constitution import CONSTITUTIONS

    constitution = CONSTITUTIONS.get((domain or "").lower())
    if constitution is None:
        return "\n".join(f"- {fact}" for fact in chart_facts)

    houses = constitution.houses
    planets = {p.lower() for p in constitution.planets}
    inside, wider = [], []
    for fact in chart_facts:
        match = _SUBJECT_HOUSE.match(fact)
        first_word = fact.split(" ", 1)[0].rstrip(".,").lower()
        owned = (
            fact.startswith(_FRAMEWORK)
            or (match is not None and int(match.group(1)) in houses)
            or first_word in planets
        )
        (inside if owned else wider).append(fact)

    lines = [
        f"CHART — WITHIN YOUR COVERAGE (houses "
        f"{', '.join(str(h) for h in sorted(constitution.primary_houses))} primary):",
        *(f"- {fact}" for fact in inside),
        "",
        "CHART — WIDER CONTEXT (real, but do not lead from these):",
        *(f"- {fact}" for fact in wider),
    ]
    return "\n".join(lines)


def contributor_context(reports) -> str:
    """Each supporting Rishi's computed evidence, labelled with who established it.

    Labelled rather than merged so the seeker (and 21's traceability requirement) can
    see which Rishi is answerable for which value.
    """
    if not reports:
        return ""
    from rishivan.council.personas import get_persona

    blocks = []
    for report in reports:
        persona = get_persona(report.rishi)
        lines = [f"EVIDENCE FROM {report.rishi.upper()} ({persona.title}):"]
        lines += [f"  - {label}: {value}" for label, value in report.computed.items()]
        if report.rules:
            lines.append(f"  - {len(report.rules)} matched rules under its coverage")
        if report.note:
            lines.append(f"  - {report.note}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
```

Change the `blocks.append(...)` inside `rule_context` to carry tier and school:

```python
        blocks.append(
            f"RULE {index} — {getattr(hit, 'citation', '')} "
            f"[{getattr(hit, 'tier', 'S5')} · {getattr(hit, 'school', 'unknown')}]\n"
            f'  The text says: "{(source.get("translation") or "").strip()}"\n'
            f"  Stated outcome: {effects or 'none recorded'}"
        )
```

In `build_rishi_prompt`, add two keyword parameters and use them:

```python
def build_rishi_prompt(
    rishi_name: str,
    domain: QueryDomain,
    question: str,
    context: str,
    chart_facts: list[str] | None = None,
    conversation=None,
    rules: str = "",
    life_domain: str | None = None,
    contributors: tuple = (),
) -> str:
```

Replace the `facts_text` assignment with:

```python
    facts_text = (
        coverage_facts(chart_facts, life_domain)
        if chart_facts
        else "No personal chart data was provided for this reading."
    )
    contributor_block = contributor_context(contributors)
    if contributor_block:
        facts_text = f"{facts_text}\n\n{contributor_block}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/council/test_prompts.py -v`
Expected: 10 passed

Then run the whole suite: `.venv/bin/python -m pytest -q`
Expected: no regressions. `build_rishi_prompt`'s new parameters are keyword-only with defaults, so existing callers are unaffected.

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/prompts.py tests/council/test_prompts.py
git commit -m "feat(prompts): order facts by coverage, label every source with tier and school"
```

---

### Task 9: Wire the orchestrator, delete the second voice

**Files:**
- Modify: `rishivan/council/orchestrator.py` (Step 3b at 366, Step 4b at 442, Step 5 at 492)
- Modify: `streamlit_app.py:655-668` (remove the second-voice expander)
- Delete: `rishivan/council/lens.py`
- Modify: `tests/eval/run_eval.py:31,229-233,263-264` (drops the deleted import)
- Test: `tests/council/test_orchestrator_wiring.py` (create)

**Interfaces:**
- Consumes: `primary_rishi_for` (Task 2), `merge_supporting` (Task 3), `gather` (Task 7), `coverage_facts`/`contributor_context` via `build_rishi_prompt` (Task 8)
- Produces: `result["contributors"]`, `result["life_domain"]`; `result["secondary_voice"]` removed

- [ ] **Step 1: Write the failing test**

Create `tests/council/test_orchestrator_wiring.py`:

```python
"""The end-to-end routing contract, without an LLM or a vector store.

These assert the specific inversions this change exists to fix, which
`scripts/eval_rules.py` cannot see -- it grades `primary` only.
"""

from rishivan.council.domains import DOMAIN_RISHIS, primary_rishi_for
from rishivan.council.routing import merge_supporting, route_question
from tests.eval.questions import QUESTIONS


def voice_for(question: str, supporting=()) -> str:
    routing = merge_supporting(route_question(question), list(supporting))
    return primary_rishi_for(routing.primary)


def test_a_marriage_timing_question_is_answered_by_the_marriage_rishi():
    """It routed to ritam, whose all-MEDIUM weights gate nothing."""
    assert voice_for("When will I marry?") == "medhan"


def test_the_billionaire_question_is_answered_by_dhruvan():
    assert voice_for("Will I become a billionaire?") == "dhruvan"


def test_the_billionaire_question_gains_atma_as_a_secondary():
    """ER 12 prescribes ARTHA primary with KARMA / ATMA / YATRA secondary."""
    routing = merge_supporting(
        route_question("Will I become a billionaire?"), ["tattvan"]
    )
    assert "atma" in routing.secondary


def test_no_eval_question_is_answered_by_a_service_rishi():
    for entry in QUESTIONS:
        assert voice_for(entry.question) in DOMAIN_RISHIS, entry.question


def test_lens_is_gone():
    import importlib
    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("rishivan.council.lens")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/council/test_orchestrator_wiring.py -v`
Expected: FAIL — `test_lens_is_gone` fails (the module still imports); the routing tests pass already because Tasks 2–3 landed. That is correct: they are regression guards for this task's edits.

- [ ] **Step 3: Write minimal implementation**

**3a.** In `orchestrator.py` Step 3b (around line 372), replace the `routing = route_question(question)` block:

```python
    from rishivan.council.domains import primary_rishi_for
    from rishivan.council.routing import merge_supporting, route_question

    routing = merge_supporting(
        route_question(question), classification.get("supporting_rishis") or []
    )
    # The routed life domain, not the classifier, decides who speaks: the coverage gate
    # keys off the domain, so letting the LLM pick the voice independently allowed a
    # persona with no coverage of the subject to answer.
    rishi = primary_rishi_for(routing.primary, classifier_pick=rishi)
    persona = get_persona(rishi)
    result["primary_rishi"] = rishi
    result["rishi_title"] = persona.title
    result["life_domain"] = routing.primary
    result["routing"] = {
        "primary": routing.primary,
        "secondary": list(routing.secondary),
        "matched": {k: list(v) for k, v in routing.matched.items()},
        "unsupported": routing.unsupported,
    }
```

**3b.** In Step 4b, after `matched_rules = rank_true_rules(...)`, inside the same `try`:

```python
            from rishivan.council.contributors import gather

            contributors = gather(
                chart, applicable, routing=routing,
                question=question, when=query_time,
            )
            result["contributors"] = [
                {"rishi": r.rishi, "computed": r.computed,
                 "rules": len(r.rules), "note": r.note}
                for r in contributors
            ]
```

Initialise `contributors: tuple = ()` beside `matched_rules = []` before the `try`, and add `"contributors": []` to the `result` dict at line 79 beside `"matched_rules": []`. Remove `"secondary_voice": None` from that dict.

**3c.** In Step 5, pass both new arguments:

```python
    prompt = build_rishi_prompt(
        rishi_name=rishi,
        domain=domain,
        question=question,
        context=context_text,
        chart_facts=chart_facts,
        conversation=conversation,
        rules=rule_context(matched_rules),
        life_domain=routing.primary,
        contributors=contributors,
    )
```

**3d.** Update the module docstring's step 7 (line 21–23) to:

```
  7. Supporting Rishis contribute COMPUTED evidence, never a second voice
     (rishivan.council.contributors) -- gathered in step 4b and labelled in
     the primary's prompt.
```

**3e.** Delete `rishivan/council/lens.py` and remove `streamlit_app.py:655-668` (the `secondary = None` block through `st.markdown(_md(secondary["body"]))`). Replace it with an attribution panel:

```python
            contributors = result.get("contributors") or []
            if contributors:
                with st.expander(
                    f"🔭 {len(contributors)} Rishis contributed to this reading",
                    expanded=False,
                ):
                    st.caption(
                        "Each contributor computes; only the primary Rishi speaks. "
                        "Values here are deterministic, not generated."
                    )
                    for entry in contributors:
                        persona = get_persona(entry["rishi"])
                        st.markdown(f"**{persona.display_name}** — {persona.title}")
                        for label, value in (entry.get("computed") or {}).items():
                            st.markdown(f"- {label}: `{value}`")
                        if entry.get("rules"):
                            st.markdown(f"- {entry['rules']} matched rules supplied")
                        if entry.get("note"):
                            st.caption(entry["note"])
```

This deletes rather than patches a live bug: `st.markdown(_md(secondary["body"]))` had no `unsafe_allow_html=True`, and `_MD` is built with `html: False`, so markdown-it escaped the model's `<p>`/`<em>` tags and the second voice rendered its HTML as literal text.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/council/test_orchestrator_wiring.py -v`
Expected: 5 passed

Run the full suite: `.venv/bin/python -m pytest -q`
Expected: all pass.

**`tests/eval/run_eval.py` will break** — it imports `maybe_generate_secondary_voice` at line 31, calls it at 233, and writes `has_secondary_voice` / `secondary_voice_rishi` into its report at 263–264. It is a script, not a pytest module, so the suite will not catch this. Fix it in this task:

- delete the import at line 31 and the call block around 229–233
- replace the two report keys with `"contributors": [c["rishi"] for c in result.get("contributors") or []]`

Leave `tests/eval/last_run_report.json` alone — it is a record of a past run, not live code.

Then confirm nothing else references the deleted module: `grep -rn "council.lens\|maybe_generate_secondary_voice\|pick_secondary_rishi\|secondary_voice" rishivan/ tests/ streamlit_app.py --include=*.py` should return nothing.

Then check the app still boots: `.venv/bin/python -c "import streamlit_app"` — expect no ImportError.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(council): one voice, many computers -- delete the second-voice path"
```

---

### Task 10: Verify against the eval set

**Files:**
- Modify: `scripts/eval_rules.py:66-69` (use the new routing and voice)
- Test: none new — this task is verification

**Interfaces:**
- Consumes: `merge_supporting` (Task 3), `primary_rishi_for` (Task 2), `gather` (Task 7)
- Produces: an eval run showing routing accuracy has not fallen and no service Rishi speaks

- [ ] **Step 1: Update the eval script**

In `scripts/eval_rules.py`, replace `routing = route_question(q.question)` in the loop with:

```python
        routing = route_question(q.question)
        voice = primary_rishi_for(routing.primary)
```

Add to the printed routing line: `f"voice={voice} "`. Add `"voice": voice` to the CSV row dict. Import `primary_rishi_for` from `rishivan.council.domains` at the top.

`merge_supporting` is deliberately NOT called here — the eval has no classifier output, so this measures the keyword table alone, which is the honest baseline.

- [ ] **Step 2: Run the eval and record the numbers**

Run: `.venv/bin/python -m scripts.eval_rules --csv /tmp/eval-after.csv`

Record: routing accuracy, and confirm no row shows `voice=` as `vyom`, `ritam` or `tejan`.

Expected: routing accuracy unchanged from before this change (the keyword table was not altered — only who consumes it). The two known routing misses persist and are out of scope: *"What are my natural strengths?"* routes nowhere, and *"What is my relationship with my father?"* routes to `prema` because "relationship" outscores "father".

- [ ] **Step 3: Commit**

```bash
git add scripts/eval_rules.py
git commit -m "test(eval): report which Rishi actually speaks"
```

- [ ] **Step 4: Report to the human**

State plainly: the routing accuracy number, whether any service Rishi still speaks, and that the secondary-contributor fix is invisible to this metric because it grades `primary` only — Task 9's assertions cover it instead.

---

## Out of scope, deliberately

- **Phase 2** — the `QueryDomain` split (`ChartEpoch` + `QuestionSchool`) and the school filter on retrieval. Spec Section 7. Nothing in Phase 1 reads `QueryDomain` except `prompts.py:263`'s three-way branch, which keeps working unchanged.
- **YATRA has no real owner.** Assigned to `dhruvan`, whose coverage is wealth and career, so *"Should I settle abroad?"* is answered using wealth houses. Fixing it means a ninth persona or resplitting `dhruvan` — a separate decision. Yatra questions stay weak after this lands.
- **Yoga recognition.** `pattern_contribution` reports only what is computed and says so in its note.
- **The two known routing misses** named in Task 10.
