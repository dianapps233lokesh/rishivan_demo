"""koonji.prompts - the extraction prompts.

Five ideas do most of the work here, and each is a response to a specific way
models fail on this task.

**A closed vocabulary with an escape hatch.** The extractor may only emit
predicates from the registry, and it is given an explicit way to say "I cannot
express this". Models approximate when they have no way to report a gap; give
them one and they use it honestly. Crucially the prompt frames proposing an
extension as a *correct and expected outcome*, not a failure. That single
reframing converts an extractor that quietly approximates into one that reports,
and it is worth more than any amount of additional vocabulary.

**A verbatim quote as a fabrication tripwire.** Every rule must carry text that
appears in the passage, checked afterwards by string match at zero cost.

**Dual extraction at two temperatures, then reconcile.** Where the runs agree,
confidence is high. Where they differ materially - a dropped exception, a
different reference point, an inverted polarity - is exactly where a human is
needed. Cheap ensembling, and the largest single accuracy lever in the pipeline.

**Adversarial verification with the reasoning hidden.** The verifier sees the
source and the JSON but not the extractor's reasoning, and is told to assume the
extraction is wrong. Asking a model to "check this" yields agreement; asking it
to "find what is wrong with this" yields findings.

**Back-translation without the source.** A third pass renders the JSON back to
prose having never seen the verse. Divergence means meaning was lost or added
while structuring - it catches the quiet scope inflation that direct comparison
misses.
"""

from __future__ import annotations

import json

from typing import Iterable

from rishivan.koonji.registry import Registry
from rishivan.koonji.urf import AssertionKind, RegistryKind

# ==========================================================================
# Shared preamble - the frame, stated once
# ==========================================================================

FRAME_BRIEFING = """\
You are extracting executable rules from a classical Jyotish text.

A rule has exactly one ASSERTION KIND. There are seven and the list is closed:

  derive_fact        writes a new, CONTESTED fact about the chart
                     (temporary friendship, functional malefic, Arudha)
  compute_value      writes an UNCONTESTED computed value
                     (planetary longitude, dasha boundaries, D9 construction)
  assert_claim       says something about the person's life
  define_attribute   says something about the VOCABULARY, not about any person
                     ("the Sun is the soul"; the 11th house's significations)
  direct_subject     tells the person to act or refrain (remedies, prohibitions)
  direct_interpreter tells the reader how to reason ("the wise astrologer should…")
  record_application a worked example: a chart plus an authority's reading of it

The boundary between derive_fact and compute_value is exactly this: could two
respected authorities disagree? If yes it is a derivation, and it must be sourced
and versioned like any other rule. If no, it belongs in the chart engine.

Most verses are not rules. Invocation, dialogue framing and praise are not
extracted at all - return an empty rule list and say so.
"""

POLARITY_NOTE = """\
POLARITY IS A STANCE, NOT A VALENCE.
  positive = this rule ASSERTS the claim
  negative = this rule DENIES the claim
A verse saying "the native has no gain despite effort" ASSERTS the claim
`wealth.loss`, so its polarity is positive. Polarity never describes whether the
outcome is welcome.
"""

REFERENCE_POINT_NOTE = """\
REFERENCE POINTS. "The 7th house" may mean the 7th from the Lagna, from the
Moon, from the Sun, from a karaka or from the Arudha. Choosing wrong produces a
rule that fires on the wrong charts forever and never looks wrong, so:

  - `occupies_bhava` means FROM THE LAGNA, always, by definition.
  - Any other reference point must use `occupies_bhava_from` and name it.
  - A reference point the registry cannot express is an extension proposal.
  - If the text genuinely does not settle it, set ambiguous_reference_point.

Never default silently to the Lagna.
"""

EXTENSION_NOTE = """\
WHEN THE VOCABULARY FALLS SHORT.

Emitting an extension proposal is a CORRECT AND EXPECTED OUTCOME. It is not a
failure, and it is not something to avoid. The corpus is supposed to tell us
what the vocabulary is missing.

Three things are forbidden:
  - approximating into the nearest existing predicate
  - dropping the content
  - inventing a predicate that is not in the registry

One thing is required: emit an ExtensionProposal with a signature, the passages
that motivated it, the nearest existing entry, and - the field a reviewer
actually reads - why that nearest entry cannot express this.

If you find yourself thinking "this is close enough", it is not. Propose.
"""


def vocabulary_block(registry: Registry, *, school: str = "school.parashari") -> str:
    """The registry, rendered for a prompt. Nothing outside this may be used."""
    lines = ["AVAILABLE PREDICATES (you may use no others):"]
    for name, spec in sorted(registry.predicates().items()):
        if spec.schools and school not in spec.schools:
            continue
        if spec.derived:
            continue
        args = ", ".join(f"{a.name}: {'|'.join(a.kinds)}" for a in spec.args)
        label = f"  # {spec.label}" if spec.label else ""
        lines.append(f"  {name}({args}){label}")

    lines.append("\nAVAILABLE CLAIMS (you may use no others):")
    for claim in sorted(registry.symbols(RegistryKind.CLAIM)):
        entry = registry.entry(RegistryKind.CLAIM, claim)
        lines.append(f"  {claim}" + (f"  # {entry.label}" if entry and entry.label else ""))
    return "\n".join(lines)


# ==========================================================================
# Stage 1 - classify
# ==========================================================================

CLASSIFIER_SYSTEM = f"""\
{FRAME_BRIEFING}

Classify this passage. Do not extract anything yet.

Report:
  assertion_kinds        which of the seven kinds the passage contains (may be
                         several; may be none)
  is_rule_bearing        false for invocation, framing, praise, transitions
  continues_previous     true if it depends on the preceding passage to be read
  has_unresolved_pronoun true for "that planet", "the same", with no antecedent
  reference_points       any non-Lagna reference the passage counts from
  estimated_rule_count   how many distinct rules it yields
  note                   one sentence, only if something is unusual

A classifier that routes correctly is worth more than a better extractor. Filing
a definition as a predictive rule pollutes the corpus permanently; filing a
computation as a rule produces something that will never fire.
"""


CLASSIFIER_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "assertion_kinds": {"type": "array", "items": {"type": "string"}},
        "is_rule_bearing": {"type": "boolean"},
        "continues_previous": {"type": "boolean"},
        "has_unresolved_pronoun": {"type": "boolean"},
        "reference_points": {"type": "array", "items": {"type": "string"}},
        "estimated_rule_count": {"type": "integer"},
        "note": {"type": "string"},
    },
    "required": ["is_rule_bearing", "estimated_rule_count"],
}
"""The one stage whose output shape is genuinely closed, so it gets a real
schema rather than only a JSON mime type.

It is also the stage that most needs one. Everything downstream is gated on
`is_rule_bearing`, and a classifier that returns prose means the passage is
never read at all - which reads in the report as "not rule bearing" rather than
as a failure."""


# ==========================================================================
# The output contract
#
# Everything below was missing, and its absence was total: the prompts
# described fields in prose, the model invented a plausible dialect for them
# ("assertion_kind", "when.all_of", a bare top-level array), and `parse_rule`
# rejected every document. Under test this never showed, because a scripted
# client returns whatever the test author wrote.
#
# `RULE_SHAPE` is checked against the real compiler by
# `tests/koonji/test_prompts.py`. If the frame changes and this example stops
# compiling, that test fails - which is the only way to stop a prompt and a
# parser drifting apart.
# ==========================================================================

RULE_SHAPE: dict = {
    "id": "BPHS.WEALTH.10L11H.0001",
    "assertion": "assert_claim",
    "domains": {"domain.wealth": 0.95, "domain.career": 0.35},
    "source": {"quote": "verbatim text copied from the passage"},
    "when": {
        "all": [
            {"occupies_bhava": {"subject": "10th lord", "bhava": 11}},
            {"dignity": {"subject": "10th lord", "dignity": "exalted"}},
        ]
    },
    "indicates": {
        "claim": "wealth.accumulation",
        "polarity": "positive",
        "magnitude": "strong",
        "text": "the native is a possessor of precious stones",
    },
    "confidence": 0.85,
}

EXTRACTOR_FLAG_KEYS: frozenset[str] = frozenset({
    "confidence",
    "approximated",
    "ambiguous_reference_point",
    "anaphora_unresolved",
    "translation_uncertainty",
    "continues_previous",
})
"""Keys the extractor reports about itself, not about the rule.

They ride on the rule document because that is the natural place for the model
to put them, and `extract.py` pops them into `ExtractionFlags` before the
document reaches `parse_rule` - which would reject them, since `confidence` on a
rule means something else entirely.

Named once, here, because three places have to agree on the list: this prompt,
the pop in `_to_candidate`, and the test that proves `RULE_SHAPE` compiles.
"""

def _literal(field: str) -> str:
    """The allowed values for a closed field, read off the frame itself.

    Written out rather than described, and read from `ClaimConsequent` rather
    than retyped, so the prompt cannot list a value the validator rejects. Every
    one of these was a discarded extraction before it was a line in a prompt.
    """
    import typing

    from rishivan.koonji.urf import ClaimConsequent

    values = typing.get_args(ClaimConsequent.model_fields[field].annotation)
    return " | ".join(repr(v) for v in values)


_SHAPE_JSON = json.dumps(RULE_SHAPE, indent=2)

OUTPUT_CONTRACT = f"""\
OUTPUT SHAPE - follow it exactly. A document in any other shape is discarded
without being read, so an approximation here costs the whole extraction.

Return a JSON object with a single key `rules`, whose value is an array of rule
documents. Not a bare array. Not `reconciled_rules`. `rules`.

Each document looks exactly like this:

{_SHAPE_JSON}

  `assertion`   singular, and one of the seven kinds. Not `assertion_kind`.
  `when`        `all`, `any`, `not`, `count` - not `all_of`, not `operator`.
                Each condition is a SINGLE-KEY mapping whose key IS the
                predicate name. There is no `predicate:` wrapper.
  arguments     named as the predicate declares them above.
  `source.quote` verbatim from the passage. Checked by string match.

CLOSED VALUE SETS - a value outside these discards the document:

  polarity    {_literal("polarity")}
  magnitude   {_literal("magnitude")}
  `domains`   keys begin `domain.` and come from the domain list above. A claim
              id is NOT a domain: `obstacle.general` in that slot makes the rule
              unreachable by every filter.
  `claim`     one of the claim ids listed above, exactly.

Omit any block you have nothing to say in. Do not invent keys.
"""


# ==========================================================================
# Stage 2 - extract (run twice, at two temperatures)
# ==========================================================================

def extractor_system(registry: Registry, *, school: str = "school.parashari") -> str:
    return f"""\
{FRAME_BRIEFING}
{POLARITY_NOTE}
{REFERENCE_POINT_NOTE}
{EXTENSION_NOTE}

{vocabulary_block(registry, school=school)}

{OUTPUT_CONTRACT}

For every rule you extract:

  quoted_text   MUST appear VERBATIM in the passage. Copy it, do not retype it.
                This is checked by string match, so a paraphrase will be caught.
  when          a boolean tree using only the predicates above
  confidence    your own, honestly

  plus the consequent block for the assertion kind you chose. The block name is
  NOT the kind name, and a rule that carries the wrong one is discarded whole:

    assert_claim        -> "indicates"
    derive_fact         -> "derives"
    define_attribute    -> "defines"
    direct_subject      -> "remedy"
    compute_value       -> "computes"
    direct_interpreter  -> "guidance"
    record_application  -> "example"

One verse often yields several rules - "Jupiter in the 2nd gives wealth; in the
6th, debt" is two. Split them.

Extract what the text says, at the scope the text says it. Do not generalise a
condition to make the rule more useful, and do not add a condition the text does
not state to make it more plausible.
"""


def extraction_prompt(passage_text: str, passage_id: str, context: str = "") -> str:
    parts = [f"PASSAGE {passage_id}:\n{passage_text}"]
    if context:
        parts.append(
            f"\nSURROUNDING CONTEXT (for resolving pronouns only - do NOT extract "
            f"rules from it):\n{context}"
        )
    return "\n".join(parts)


# ==========================================================================
# Stage 3 - reconcile the two extractions
# ==========================================================================

RECONCILER_SYSTEM = """\
Two independent extractions were run over the same passage at different
temperatures. Compare them.

For each difference decide: MATERIAL or COSMETIC.

  COSMETIC   different wording of quoted_text that is still verbatim; different
             ordering of conjuncts; a different but equivalent claim id
  MATERIAL   a dropped or added condition; a different reference point; an
             inverted polarity; a different claim; a missing exception or
             cancellation; a different scope

Cosmetic differences: pick the better rendering and move on.
Material differences: this is exactly where a human is needed. Say so, name the
difference precisely, and do not split it yourself.

Return a JSON object with exactly two keys:

  `rules`           the reconciled rule documents, in the same shape the
                    extractor was given. Not `reconciled_rules`.
  `disagreements`   an array of strings, one per material difference.

A material disagreement does not remove the rule from `rules` - it travels with
it, so a reviewer sees the rule and the doubt together.
"""


# ==========================================================================
# Stage 4 - adversarial verification
# ==========================================================================

VERIFIER_SYSTEM = f"""\
{POLARITY_NOTE}
{REFERENCE_POINT_NOTE}

Assume this extraction is WRONG. Your job is to find what is wrong with it, not
to confirm it.

You are given the source passage and the extracted JSON. You are NOT given the
extractor's reasoning, deliberately - reading it would make you agree with it.

Check, specifically:
  - does quoted_text appear verbatim in the passage?
  - does the condition say what the passage says, at the same scope?
  - is any condition present in the passage but missing from the extraction?
  - is any condition in the extraction absent from the passage?
  - is the reference point right, and stated?
  - is the polarity a stance toward the claim, not a valence judgement?
  - is an exception, cancellation or "unless" clause dropped?
  - is a restriction missing on longevity, death timing or health material?

Return ACCEPT, REVISE or REJECT, with a categorised finding for each problem.
Return a JSON object with one key `verdicts`, an array of
`{{"rule_id": ..., "verdict": "ACCEPT"|"REVISE"|"REJECT", "findings": [...]}}`,
each finding `{{"category": ..., "severity": "error"|"warning", "message": ...}}`.

An extraction with no problems is possible; say ACCEPT plainly when you find
none. Do not invent findings to appear thorough.
"""


# ==========================================================================
# Stage 5 - back-translation
# ==========================================================================

BACK_TRANSLATOR_SYSTEM = """\
Render this structured rule back into a single plain English sentence, as a
classical text would state it.

You have NOT been shown the source verse and you must not ask for it. Write only
what the JSON says - no more, no less. Do not add a condition to make the
sentence read naturally, and do not drop one to make it read cleanly.

The rendering will be compared to the original verse. Divergence is the signal
we are looking for, so an awkward faithful sentence is far more useful than a
smooth one.
"""
