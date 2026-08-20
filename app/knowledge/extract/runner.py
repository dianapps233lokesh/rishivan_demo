"""S5 — run extraction over rule-bearing units, with a cached prefix.

Two things make this cheap and safe rather than one:

* **The prefix is cached once per run**, not sent per call. It is ~19.6k tokens of
  invariant instructions, vocabulary, examples and schema, and at 1,144 units that is
  the difference between $12 and $3.
* **Nothing the model returns is trusted.** `validate_rule` decides whether an
  extraction is usable, and it demonstrably has to: the model returns schema-valid
  atoms with fields belonging to other condition types and required fields missing.
  Rules failing validation are recorded with their reasons rather than persisted, so a
  bad batch is visible instead of silently thin.

Deliberately does not write to `rule` yet. This stage is for inspecting output on a
small sample; persistence lands once a human has confirmed the extractions are worth
keeping.
"""

import json
import time
from dataclasses import dataclass, field

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.extract.prompt import (
    INSTRUCTIONS,
    MODEL,
    TOOL_NAME,
    cached_contents,
    emit_rules_tool,
    verse_block,
)
from app.knowledge.extract.validate import ValidationResult, validate_rule
from app.models.knowledge.book import Book
from app.models.knowledge.triage import UnitTriage
from app.models.knowledge.unit import SutraUnit

CACHE_TTL_SECONDS = 6 * 3600
"""Long enough to outlast a whole-book run.

This was one hour, which is fine for a 20-unit sample and silently wrong for the real
thing: 963 units at ~3s each plus retries runs past 60 minutes, and when the cache
expires mid-run the remaining calls are billed at the full input rate instead of the
cached one — roughly a 20x jump on input, with no error to notice. Storage is billed per
token-hour and the prefix is ~5.2k tokens, so six hours of headroom costs a rounding
error."""
MAX_RETRIES = 1
"""One bounded second look, never a loop.

The validator emits precise, mechanical faults -- "field 'houses' does not belong to
this condition type", "required field 'planet' is missing" -- and handing those back is
far more effective than another round of prompt tuning, which is where three successive
failure modes had led. Bounded at one because an unbounded correction loop makes cost
unpredictable and lets the model argue itself into a worse answer; a rule that fails
twice is filed with its faults rather than retried again."""


GROUNDING_MARKERS = (
    "is never mentioned in the verse",
    "is never named in the verse",
    "is never stated in the verse",
)
"""Faults where the only correct second answer is a decline, not another atom.

A grounding fault means the verse needs a concept the vocabulary does not have -- "a
benefic", "the strong 9th lord" -- and the model reached for the nearest planet. Told
only "that was rejected", it substitutes a different planet and fails again: the first
graded sample spent 15 retries and fixed 0 rules. So the note names the remedy
explicitly instead of leaving the model to infer it."""


def retryable(problems) -> bool:
    """Whether a second call could plausibly change the answer.

    Every fault the validator emits is actionable -- structural ones by supplying the
    missing field, grounding ones by declining -- so this is true whenever there is a
    fault at all. It exists as a named gate because that was not obvious: the earlier
    loop retried on declines too, spending a call to re-refuse a verse the model had
    already correctly refused.
    """
    return bool(problems)


def correction_note(problems) -> str:
    """Turn validation faults into a correction instruction for the retry."""
    faults = "\n".join(f"  - {p.reason}" for p in problems)
    note = (
        "\n\nYOUR PREVIOUS ATTEMPT AT THIS VERSE WAS REJECTED by the deterministic "
        "validator:\n"
        f"{faults}\n"
        "Fix exactly these faults. Supply every required field for each condition "
        "type, and remove any field that does not belong to it. If the verse genuinely "
        "cannot be expressed with the available atoms, set `expressible: false` with "
        "an `out_of_scope_reason` instead of emitting an incomplete atom."
    )
    if any(marker in p.reason for p in problems for marker in GROUNDING_MARKERS):
        note += (
            "\nAt least one fault above is a GROUNDING failure: you named a planet, "
            "sign or dignity the verse does not. That is not a typo to correct with a "
            "different planet -- it means the verse depends on a concept the "
            "vocabulary cannot express (most often 'a benefic'/'a malefic', or the "
            "dignity or strength of a house lord). The ONLY correct fix is "
            "`expressible: false` with `out_of_scope_reason` naming that concept. Do "
            "NOT substitute another planet."
        )
    return note


PIPELINE_TAG = "koonji-extract"
"""Helicone `pipeline` property, so extraction spend is separable from chat traffic."""


@dataclass
class ExtractedRule:
    unit_id: int
    chapter: str
    verse_ref: str
    rule: dict
    validation: ValidationResult
    translation: str = ""
    """The verse the rule claims to come from, carried so review does not need a
    database. The first review artefact omitted it, which made the one question a
    reviewer has to answer -- "does the text say this?" -- unanswerable from the file."""

    @property
    def ok(self) -> bool:
        return self.validation.ok

    @property
    def declined(self) -> bool:
        return self.validation.declined


@dataclass
class ExtractionReport:
    units: int = 0
    calls: int = 0
    retries: int = 0
    fixed_by_retry: int = 0
    rules: int = 0
    valid: int = 0
    invalid: int = 0
    declined: int = 0
    declined_without_reason: int = 0
    timing_atoms_moved: int = 0
    atoms_merged: int = 0
    stripped_atoms: int = 0
    prompt_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    failures: list[str] = field(default_factory=list)
    extracted: list[ExtractedRule] = field(default_factory=list)

    @property
    def billed_input(self) -> int:
        return self.prompt_tokens - self.cached_tokens

    @property
    def attempted(self) -> int:
        """Rules the extractor actually tried to express -- the denominator precision is
        measured over. Declines are excluded because a decline is an outcome, not an
        attempt: counting them as failed rules is what reported 29% for a sample whose
        real rule precision was more than twice that."""
        return self.rules - self.declined

    @property
    def precision(self) -> float:
        return self.valid / self.attempted if self.attempted else 0.0

    def line(self) -> str:
        return (
            f"units={self.units} calls={self.calls} retries={self.retries} "
            f"fixed_by_retry={self.fixed_by_retry} rules={self.rules} "
            f"declined={self.declined} attempted={self.attempted} "
            f"valid={self.valid} invalid={self.invalid} "
            f"precision={self.precision:.0%} | "
            f"timing_moved={self.timing_atoms_moved} "
            f"merged={self.atoms_merged} stripped={self.stripped_atoms} "
            f"no_reason={self.declined_without_reason} | "
            f"prompt={self.prompt_tokens:,} cached={self.cached_tokens:,} "
            f"billed_in={self.billed_input:,} out={self.output_tokens:,}"
        )


async def rule_bearing_units(
    session: AsyncSession,
    *,
    book_slug: str,
    limit: int,
    offset: int = 0,
    nth: int | None = 1,
) -> list[SutraUnit]:
    """Units triage routed to destination A, in chapter then verse order.

    `nth=None` takes EVERY rule-destined unit -- the whole-book mode. An integer takes
    one unit per chapter, the `nth` within each, which is the review sampler.

    That distinction is load-bearing and was originally missing: with only the sampler,
    `--limit 2000` still returned one verse per chapter, so a run intended to cover 485
    units processed 30 and exited cleanly, looking like success.

    Three things this query has to get right for a review sample to be worth reviewing:

    `chapter` is a varchar, so a plain `ORDER BY chapter` sorts '10' before '2'. The
    first sample drawn that way was twelve consecutive verses from chapter 10 -- all
    longevity and death rules, from one chapter, which tells a reviewer almost nothing
    about the extractor's behaviour on the rest of the book.

    So: cast to integer for ordering, and take one unit per chapter, giving `limit`
    distinct chapters instead of `limit` neighbours.

    And `nth`, because one-per-chapter is not enough on its own. Taking the FIRST unit
    of each chapter samples exactly where BPHS puts "O Brahmin, now I explain to you the
    effects of the Nth house" -- preamble, not rules. A 20-chapter sample drawn that way
    declined 17 of 30 extractions, which reads as a vocabulary crisis and is partly an
    artefact of asking the extractor to parse tables of contents. `nth` moves the probe
    into the body of the chapter, where the if-then verses are.
    """
    chapter_no = cast(SutraUnit.chapter, Integer)
    ranked = (
        select(
            SutraUnit.id,
            func.row_number()
            .over(partition_by=chapter_no, order_by=SutraUnit.id)
            .label("rank"),
        )
        .join(UnitTriage, UnitTriage.unit_id == SutraUnit.id)
        .join(Book, Book.id == SutraUnit.book_id)
        .where(
            Book.slug == book_slug,
            UnitTriage.destination == "rule",
            UnitTriage.deleted_at.is_(None),
            SutraUnit.deleted_at.is_(None),
            SutraUnit.translation != "",
            SutraUnit.chapter.op("~")("^[0-9]+$"),
        )
        .subquery()
    )
    query = select(ranked.c.id)
    if nth is not None:
        query = query.where(ranked.c.rank == nth)
    ids = list((await session.execute(query)).scalars())
    if not ids:
        return []
    return list(
        (
            await session.execute(
                select(SutraUnit)
                .where(SutraUnit.id.in_(ids))
                .order_by(cast(SutraUnit.chapter, Integer), SutraUnit.id)
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
    )


def build_client():
    """Inference client, routed through Helicone when a key is configured."""
    from rishivan.council.client import get_vertex_client

    return get_vertex_client(helicone_model=MODEL, helicone_pipeline=PIPELINE_TAG)


def build_admin_client():
    """Direct Vertex client for cache management -- deliberately NOT via Helicone.

    Creating and deleting a cache is control plane, not inference: there is nothing to
    observe and no tokens to attribute. Routing it through the gateway also breaks --
    `caches.delete` is a body-less DELETE and Helicone returns
    `500 Body has already been used`, which silently leaks the cache. Cache storage is
    billed per token-hour, so a leaked 19.6k-token cache keeps costing until its TTL
    expires.
    """
    from rishivan.council.client import get_vertex_client

    return get_vertex_client()


def create_prefix_cache(client):
    """Cache everything invariant: instructions, vocabulary, examples, and the output
    contract as a forced tool. Returns (cache_name, cached_token_count).

    `tool_config` goes here rather than on the request -- the API rejects it in both
    places at once.
    """
    from google.genai import types

    cache = client.caches.create(
        model=MODEL,
        config=types.CreateCachedContentConfig(
            system_instruction=INSTRUCTIONS,
            contents=[
                types.Content(
                    role="user", parts=[types.Part(text=cached_contents())]
                )
            ],
            tools=[emit_rules_tool()],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY", allowed_function_names=[TOOL_NAME]
                )
            ),
            ttl=f"{CACHE_TTL_SECONDS}s",
            display_name="koonji-s5-prefix",
        ),
    )
    total = cache.usage_metadata.total_token_count if cache.usage_metadata else 0
    return cache.name, total


RATE_LIMIT_BACKOFF = (4, 15, 45)
"""Waits after a 429, in seconds.

Not a nicety. A 20-unit sample lost 3 calls to `429 RESOURCE_EXHAUSTED`, and the loop
records a failure and moves on -- so at 963 units that silently thins the rule base by
roughly 15% while every visible number still looks healthy. The gap would only show up
later as chapters that mysteriously produced nothing.

Three waits totalling ~64s, because the limit is per-minute: the point is to outlast one
window, not to retry forever.
"""


def call_with_backoff(call, *, describe: str):
    """Run `call`, waiting out rate limits. Any other error is raised immediately --
    a malformed request will not fix itself, and retrying it just burns money."""
    for wait in (*RATE_LIMIT_BACKOFF, None):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001 - classified by message, not type
            transient = "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)
            if not transient or wait is None:
                raise
            print(f"  rate limited on {describe}; waiting {wait}s")
            time.sleep(wait)
    raise AssertionError("unreachable")


def extract_unit(
    client, cache_name: str, unit: SutraUnit, *, correction: str = ""
) -> tuple[list[dict], object]:
    """One verse in, rules out. The request carries ONLY the verse (plus a correction
    note on retry) -- everything else is already in the cache, which is why billed
    input is ~557 tokens rather than ~6,000."""
    from google.genai import types

    response = call_with_backoff(
        lambda: client.models.generate_content(
            model=MODEL,
            contents=verse_block(
                chapter=str(unit.chapter),
                verse_ref=str(unit.verse_ref_local),
                verse_devanagari=unit.verse_devanagari,
                translation=unit.translation,
                commentary=unit.commentary,
            )
            + correction,
            config=types.GenerateContentConfig(
                cached_content=cache_name,
                # Thinking off: measured `thoughts_token_count=None` and
                # total == prompt + candidates, so there is no hidden billing, and the
                # graded run scored identically with it disabled.
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        ),
        describe=f"ch{unit.chapter}:v{unit.verse_ref_local}",
    )
    rules: list[dict] = []
    for candidate in response.candidates or []:
        for part in (candidate.content.parts if candidate.content else None) or []:
            call = part.function_call
            if call and call.name == TOOL_NAME:
                rules.extend(dict(rule) for rule in dict(call.args).get("rules") or [])
    return rules, response.usage_metadata


async def run_extraction(
    session: AsyncSession,
    *,
    book_slug: str,
    limit: int,
    offset: int = 0,
    nth: int | None = 1,
    on_result=None,
    on_start=None,
) -> ExtractionReport:
    """`on_result(ExtractedRule, ExtractionReport)` is called as each rule is validated,
    so a long run can checkpoint and report progress instead of buffering 485 units of
    output and losing all of it if the process dies at unit 484. `on_start(total)` fires
    once the work is counted, so a monitor can show progress against a denominator."""
    report = ExtractionReport()
    units = await rule_bearing_units(
        session, book_slug=book_slug, limit=limit, offset=offset, nth=nth
    )
    report.units = len(units)
    if on_start is not None:
        on_start(len(units))
    if not units:
        return report

    client = build_client()
    admin = build_admin_client()
    cache_name, cached_total = create_prefix_cache(admin)
    print(f"prefix cached: {cached_total:,} tokens (ttl {CACHE_TTL_SECONDS}s)")

    try:
        for unit in units:
            try:
                rules, usage = extract_unit(client, cache_name, unit)
            except Exception as exc:  # noqa: BLE001 - one bad unit must not stop the run
                report.failures.append(
                    f"unit {unit.id} (ch{unit.chapter}:v{unit.verse_ref_local}): "
                    f"{type(exc).__name__}: {str(exc)[:120]}"
                )
                continue
            report.calls += 1
            report.prompt_tokens += usage.prompt_token_count or 0
            report.cached_tokens += usage.cached_content_token_count or 0
            report.output_tokens += usage.candidates_token_count or 0

            # The grounding check needs the source text: a substituted planet is only
            # detectable by comparing the rule against the verse it claims to come from.
            source_text = f"{unit.translation} {unit.commentary}"
            validated = [
                (rule, validate_rule(rule, source_text=source_text)) for rule in rules
            ]

            # One second look, and only when a retry can actually change the answer.
            # The retry re-extracts the whole verse rather than patching one atom,
            # because a wrong condition type usually means the verse was misread, not
            # mistyped.
            faults = [p for _, v in validated if not v.declined for p in v.problems]
            if retryable(faults) and MAX_RETRIES:
                try:
                    retried, retry_usage = extract_unit(
                        client, cache_name, unit, correction=correction_note(faults)
                    )
                except Exception as exc:  # noqa: BLE001
                    report.failures.append(f"unit {unit.id} retry: {type(exc).__name__}")
                else:
                    report.calls += 1
                    report.retries += 1
                    report.prompt_tokens += retry_usage.prompt_token_count or 0
                    report.cached_tokens += (
                        retry_usage.cached_content_token_count or 0
                    )
                    report.output_tokens += retry_usage.candidates_token_count or 0
                    revalidated = [
                        (r, validate_rule(r, source_text=source_text)) for r in retried
                    ]
                    before_ok = sum(1 for _, v in validated if v.ok and not v.declined)
                    after_ok = sum(1 for _, v in revalidated if v.ok and not v.declined)
                    before_bad = sum(1 for _, v in validated if not v.ok)
                    after_bad = sum(1 for _, v in revalidated if not v.ok)
                    # Keep the retry when it is genuinely better; a retry that produces
                    # fewer valid rules is a regression, not a correction.
                    #
                    # Equal-valid-but-fewer-invalid counts as better, and that clause is
                    # not hypothetical: told its atom was ungrounded, the model's usual
                    # second answer is an honest `expressible: false`. That is the
                    # outcome we want and it scores 0 valid, so the strict
                    # `after_ok > before_ok` test threw it away and kept the fabricated
                    # rule instead.
                    better = after_ok > before_ok or (
                        after_ok == before_ok and after_bad < before_bad
                    )
                    if revalidated and better:
                        report.fixed_by_retry += max(after_ok - before_ok, 0)
                        validated = revalidated

            for rule, validation in validated:
                report.rules += 1
                report.timing_atoms_moved += validation.timing_atoms_moved
                report.atoms_merged += validation.atoms_merged
                report.stripped_atoms += validation.stripped_atoms
                if validation.declined:
                    report.declined += 1
                    if not validation.ok:
                        report.declined_without_reason += 1
                elif validation.ok:
                    report.valid += 1
                else:
                    report.invalid += 1
                extracted_rule = ExtractedRule(
                    unit_id=unit.id,
                    chapter=str(unit.chapter),
                    verse_ref=str(unit.verse_ref_local),
                    rule=rule,
                    validation=validation,
                    translation=unit.translation,
                )
                report.extracted.append(extracted_rule)
                if on_result is not None:
                    on_result(extracted_rule, report)
    finally:
        # Cache storage is billed per token-hour; a sample run should not leave it.
        try:
            admin.caches.delete(name=cache_name)
        except Exception as exc:  # noqa: BLE001
            print(f"warning: leaked cache {cache_name}: {type(exc).__name__}")
    return report
