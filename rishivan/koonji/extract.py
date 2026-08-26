"""koonji.extract - the six-call pipeline that turns a passage into candidates.

    classify -> extract x2 -> reconcile -> verify -> back-translate -> validate

Six model calls per rule-bearing passage, roughly 8-14K tokens, dominated by the
two extractions. For a 4,000-passage text that is on the order of tens of
millions of tokens - a few hundred dollars, against two reviewer-months for the
same corpus. Extraction compute is a rounding error next to reviewer time, so
this pipeline is deliberately not optimised: the dual extraction and the
adversarial verifier pay for themselves many times over in review saved.

This module is the ONLY place in `koonji` that talks to a language model, and it
never runs in the serving path. The client is injected rather than constructed,
so the orchestration above is testable without a network or a key - which
matters, because the orchestration is where the interesting mistakes are.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Protocol

from rishivan.koonji import prompts
from rishivan.koonji.registry import Registry
from rishivan.koonji.urf import ExtensionProposal, Rule
from rishivan.koonji.validate import (
    ExtractionCandidate,
    ExtractionFlags,
    Finding,
    is_blocked,
    review_priority,
    validate_candidate,
)

PROMPT_VERSION = "1.0.0"

JSON_OBJECT: dict = {}
"""Ask the provider for JSON without constraining its shape.

Every stage below parses its response as JSON, and until this was passed
nothing told the model to produce any. The prompts describe a field list under
the word "Report:", a model reads that as a request for a report, and
`_parse_json` then fails on the first character. Invisible under test, because a
scripted client returns whatever the test wrote - and total in production.

Empty rather than a real schema: a rule document is open by construction (seven
consequent shapes, an extensible predicate vocabulary), so a response schema
tight enough to be worth having would reject valid extractions.
"""

#: The two temperatures. Where they agree, confidence is high; where they differ
#: materially is exactly where a reviewer is needed.
EXTRACTION_TEMPERATURES = (0.0, 0.4)


class ModelClient(Protocol):
    """Whatever calls the model. Injected so the pipeline is testable."""

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        json_schema: Optional[dict] = None,
        model: str = "",
    ) -> str:
        ...


@dataclass(slots=True)
class Passage:
    passage_id: str
    text: str
    book_id: str
    edition_id: str
    locator: str
    context: str = ""


@dataclass(slots=True)
class Usage:
    calls: int = 0
    by_stage: dict[str, int] = field(default_factory=dict)

    def record(self, stage: str) -> None:
        self.calls += 1
        self.by_stage[stage] = self.by_stage.get(stage, 0) + 1


@dataclass(slots=True)
class PassageResult:
    passage: Passage
    classification: dict[str, Any] = field(default_factory=dict)
    candidates: list[ExtractionCandidate] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    """Material differences between the two extraction runs. Every one of these
    is a reviewer decision, not something the pipeline should resolve itself."""

    proposals: list[ExtensionProposal] = field(default_factory=list)
    findings: dict[str, list[Finding]] = field(default_factory=dict)
    back_translations: dict[str, str] = field(default_factory=dict)
    unbuildable: list[str] = field(default_factory=list)
    """Documents the model returned that would not parse as rules, with the
    reason. Silently dropping these was hiding an entire class of prompt bug:
    the run reported "0 candidates" after six paid calls and said nothing about
    why, which reads as "the passage had no rules in it"."""

    usage: Usage = field(default_factory=Usage)
    skipped: str = ""

    @property
    def blocked(self) -> list[str]:
        return [rid for rid, fs in self.findings.items() if is_blocked(fs)]

    def queue(self) -> list[tuple[float, ExtractionCandidate]]:
        return sorted(
            (
                (review_priority(c, self.findings.get(c.rule.rule_id, [])), c)
                for c in self.candidates
            ),
            key=lambda row: -row[0],
        )


def _parse_json(raw: str) -> Any:
    """Models fence JSON whatever the instructions say."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    return json.loads(text)


class Extractor:
    """The pipeline. Stateless between passages except for the proposal queue."""

    def __init__(
        self,
        client: ModelClient,
        registry: Registry,
        *,
        fast_model: str = "gemini-2.5-flash",
        deep_model: str = "gemini-2.5-pro",
        rule_builder: Optional[Callable[[dict, Registry], Rule]] = None,
    ) -> None:
        self.client = client
        self.registry = registry
        self.fast_model = fast_model
        self.deep_model = deep_model
        if rule_builder is None:
            from rishivan.koonji.compiler import parse_rule

            rule_builder = parse_rule
        self._build_rule = rule_builder

    # -- stages ------------------------------------------------------------

    def classify(self, passage: Passage, usage: Usage) -> dict[str, Any]:
        usage.record("classify")
        return _parse_json(self.client.complete(
            system=prompts.CLASSIFIER_SYSTEM,
            json_schema=prompts.CLASSIFIER_SCHEMA,
            prompt=prompts.extraction_prompt(passage.text, passage.passage_id),
            temperature=0.0,
            model=self.fast_model,
        ))

    def extract_once(
        self, passage: Passage, temperature: float, usage: Usage
    ) -> dict[str, Any]:
        usage.record(f"extract@{temperature}")
        return _parse_json(self.client.complete(
            system=prompts.extractor_system(self.registry),
            json_schema=JSON_OBJECT,
            prompt=prompts.extraction_prompt(
                passage.text, passage.passage_id, passage.context
            ),
            temperature=temperature,
            model=self.deep_model,
        ))

    def reconcile(
        self, passage: Passage, a: dict, b: dict, usage: Usage
    ) -> dict[str, Any]:
        usage.record("reconcile")
        payload = json.dumps({"passage": passage.text, "run_a": a, "run_b": b})
        return _parse_json(self.client.complete(
            system=prompts.RECONCILER_SYSTEM,
            json_schema=JSON_OBJECT,
            prompt=payload,
            temperature=0.0,
            model=self.deep_model,
        ))

    def verify(self, passage: Passage, rules: list[dict], usage: Usage) -> dict[str, Any]:
        usage.record("verify")
        # The extractor's reasoning is deliberately NOT in this payload. Showing
        # it to the verifier turns an adversary into an agreeing reader.
        payload = json.dumps({"passage": passage.text, "extracted": rules})
        return _parse_json(self.client.complete(
            system=prompts.VERIFIER_SYSTEM,
            json_schema=JSON_OBJECT,
            prompt=payload,
            temperature=0.0,
            model=self.deep_model,
        ))

    def back_translate(self, rule: dict, usage: Usage) -> str:
        usage.record("back_translate")
        # No passage in the payload, deliberately.
        return self.client.complete(
            system=prompts.BACK_TRANSLATOR_SYSTEM,
            prompt=json.dumps(rule),
            temperature=0.0,
            model=self.fast_model,
        ).strip()

    # -- the whole path ----------------------------------------------------

    def process(self, passage: Passage, *, skip_dual: bool = False) -> PassageResult:
        result = PassageResult(passage=passage)
        usage = result.usage

        result.classification = self.classify(passage, usage)
        if not result.classification.get("is_rule_bearing", True):
            result.skipped = "not rule-bearing"
            return result

        first = self.extract_once(passage, EXTRACTION_TEMPERATURES[0], usage)
        if skip_dual:
            merged = first
        else:
            second = self.extract_once(passage, EXTRACTION_TEMPERATURES[1], usage)
            reconciled = self.reconcile(passage, first, second, usage)
            merged = reconciled
            result.disagreements = [
                str(d) for d in (
                    reconciled.get("disagreements")
                    or reconciled.get("material_disagreements")
                    or []
                )
            ]

        raw_rules = list(merged.get("rules", []))
        result.proposals = [
            ExtensionProposal.model_validate(p) for p in merged.get("proposals", [])
        ]

        if not raw_rules:
            result.skipped = result.skipped or "no rules extracted"
            return result

        verification = self.verify(passage, raw_rules, usage)
        verdicts = {v.get("rule_id"): v for v in verification.get("verdicts", [])}

        for raw in raw_rules:
            candidate, why = self._to_candidate(passage, raw, result.proposals)
            if candidate is None:
                result.unbuildable.append(why)
                continue
            result.candidates.append(candidate)

            findings = validate_candidate(candidate)
            verdict = verdicts.get(candidate.rule.rule_id, {})
            for problem in verdict.get("findings", []):
                findings.append(Finding(
                    code=problem.get("category", "verifier"),
                    severity=problem.get("severity", "warning"),
                    message=problem.get("message", ""),
                    blocking=verdict.get("verdict") == "REJECT",
                ))
            result.findings[candidate.rule.rule_id] = findings

            result.back_translations[candidate.rule.rule_id] = self.back_translate(
                raw, usage
            )

        return result

    def _to_candidate(
        self, passage: Passage, raw: dict, proposals: list[ExtensionProposal]
    ) -> tuple[Optional[ExtractionCandidate], str]:
        raw = dict(raw)
        raw.setdefault("status", "candidate")
        source = dict(raw.get("source") or {})
        source.setdefault("book", passage.book_id)
        source.setdefault("edition", passage.edition_id)
        source.setdefault("locator", passage.locator)
        raw["source"] = source

        flags = ExtractionFlags(
            confidence=float(raw.get("confidence", 0.5)),
            approximated=bool(raw.get("approximated", False)),
            ambiguous_reference_point=bool(raw.get("ambiguous_reference_point", False)),
            anaphora_unresolved=bool(raw.get("anaphora_unresolved", False)),
            translation_uncertainty=bool(raw.get("translation_uncertainty", False)),
            continues_previous=bool(raw.get("continues_previous", False)),
        )
        # Popped as a set rather than one at a time, so the list cannot drift
        # from the one the prompt tells the model to send.
        for key in prompts.EXTRACTOR_FLAG_KEYS:
            raw.pop(key, None)
        try:
            rule = self._build_rule(raw, self.registry)
        except Exception as exc:  # noqa: BLE001 - the reason is the payload
            # A candidate that will not parse is not a candidate, and it does
            # not go into the review queue - it would cost a reviewer time to
            # reach the same conclusion. But it is reported, because a document
            # the model produced and the frame refused is a prompt bug or a
            # missing predicate, and both are things somebody needs to see.
            return None, f"{raw.get('id', '<no id>')}: {type(exc).__name__}: {exc}"

        return ExtractionCandidate(
            passage_id=passage.passage_id,
            passage_text=passage.text,
            rule=rule,
            flags=flags,
            proposals=proposals,
        ), ""


def form_distribution(results: Iterable[PassageResult]) -> dict[str, float]:
    """Share of extractions by projected T-code.

    Cheap, effective regression signal. If lordship rules come out at 5% or
    named yogas at 30%, something is wrong with the prompt or the OCR, and this
    catches it faster than reading individual rules does.
    """
    from rishivan.koonji.urf import project_tcode

    counts: dict[str, int] = {}
    total = 0
    for result in results:
        for candidate in result.candidates:
            code = project_tcode(candidate.rule)
            counts[code] = counts.get(code, 0) + 1
            total += 1
    if not total:
        return {}
    return {code: round(n / total, 4) for code, n in sorted(counts.items())}


def approximation_rate(results: Iterable[PassageResult]) -> float:
    """Must be exactly 0.0. Anything above it is silent corpus corruption."""
    total = approximated = 0
    for result in results:
        for candidate in result.candidates:
            total += 1
            approximated += int(candidate.flags.approximated)
    return (approximated / total) if total else 0.0
