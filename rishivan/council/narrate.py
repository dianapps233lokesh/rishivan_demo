"""Prose, generated from the plan — and a template when the model is not there.

**This runs outside the graph, and that is the whole structural point of Phase
5.** A live generator in state is not serialisable, so a graph that builds one
cannot be checkpointed. Building it here, after `graph.invoke` returns, means
the graph's final state is plain data and the checkpointer that has been sitting
unused starts working. The caller contract is unchanged - `council_consult`
still hands back a generator of text chunks.

**The gate is subtractive.** Only `plan.allowed` reaches the prompt. A claim
that did not clear the evidence floor is not down-weighted or hedged, it is
absent, and a model cannot cite what it was never shown. That is why this works
where "please do not over-claim" does not.

**The fallback is the argument for the architecture.** `render_template` writes
a real answer with real citations from the plan alone. When the model is down,
the system still answers and the answer is still grounded - which is possible
only because the evidence was structured before anything tried to narrate it.
"""

from __future__ import annotations

from typing import Generator

MODEL_TIER = "flash"

INSUFFICIENT = (
    "I don't have material in the ingested books that speaks to this clearly "
    "enough to answer. Saying so is the answer — I'd rather not compose "
    "something that reads like a reading and isn't one."
)

INSTRUCTION = """You are speaking to one person about their chart. Write as
though you have read it carefully and are telling them what you found.

**You may state the findings below and nothing else.** Every one carries the
exact phrasing its evidence licenses — use that phrasing, and do not upgrade it.
A finding marked "some indications suggest" is not a finding you may report as
established, however natural that would read.

Where a finding has evidence against it, say so in the same breath. Do not
gather the caveats into a paragraph at the end; a reader skips that paragraph,
and you will have technically disclosed something nobody heard.

No preamble about what astrology is. No summary of what you are about to say.
No sign-off — the interface adds one."""


def _claims_block(plan) -> str:
    lines = ["WHAT YOU MAY SAY — these findings and no others"]
    for claim in plan.allowed:
        lines.append(f"  [{claim.claim_id}]")
        lines.append(f"      phrasing licensed: \"{claim.phrasing}\"")
        lines.append(f"      confidence {claim.confidence:.2f}, "
                     f"evidence tier {claim.tier}")
        lines.append(f"      cite: {', '.join(claim.citations) or 'uncited'}")
        if claim.counter:
            lines.append(
                f"      ARGUES AGAINST IT: {', '.join(claim.counter)} — say "
                f"this alongside the finding, not after it"
            )
        if not claim.corroborated:
            lines.append("      NOT CORROBORATED to this domain's standard. "
                         "State it as an indication.")
        if claim.window:
            lines.append(f"      window: {claim.window} — you may name this "
                         f"period, and only this period")
    return "\n".join(lines)


def gate_block(plan) -> str:
    """The plan, rendered for the prompt.

    Two kinds of material reach the narrative voice and they are not the same
    kind of thing, so they are labelled separately:

      * **`AllowedClaim`s** are assertions about *this chart*, licensed by
        rules that fired and cleared the evidence floor. The gate is on these,
        and it is subtractive - a claim that did not clear the floor is not in
        the prompt, so no amount of enthusiasm can put it in the answer.
      * **Retrieved passages** are book text. They may be quoted and explained;
        they may not be turned into new claims about the chart, because
        topical similarity is not evidence that something is true of this
        native. That prohibition is stated below rather than assumed.

    Collapsing the two - gating the passages, or licensing the claims loosely -
    breaks one half or the other. Most questions in this corpus still reach the
    reader through passages alone, because the rule base is thin.
    """
    if plan is None:
        return ""

    blocks = [INSTRUCTION, _claims_block(plan)]
    if plan.must_say:
        blocks.append(
            "YOU MUST SAY THESE\n"
            + "\n".join(f"  {m}" for m in plan.must_say)
            + "\n  These are what the reader is owed. A model left to itself "
              "smooths them over, because they make the answer less satisfying."
        )
    if plan.must_not_say:
        blocks.append(
            "YOU MUST NOT SAY THESE\n"
            + "\n".join(f"  {m}" for m in plan.must_not_say)
        )
    if plan.disagreement:
        blocks.append(f"THE COUNCIL DISAGREED\n  {plan.disagreement}")
    return "\n\n".join(blocks)


def build_narration_prompt(plan, *, state=None) -> str:
    """Everything the narrative voice sees. Deterministic given plan and state.

    Built on `prompts.build_rishi_prompt` rather than replacing it: the persona,
    the conversation history, the retrieved passages and the chart facts all
    still reach the model exactly as they did, and the plan is inserted as the
    gate ahead of them. Writing a second prompt builder here would have quietly
    dropped the page retrieval that most questions still answer from - which it
    did, for one commit, until the integration test caught it.
    """
    from rishivan.council.domains import QueryDomain
    from rishivan.council.prompts import build_rishi_prompt, rule_context

    state = state or {}
    council = "\n\n---\n\n".join(
        b for b in (gate_block(plan), state.get("council_summary", "")) if b
    )
    return build_rishi_prompt(
        rishi_name=state.get("primary_rishi") or "vyom",
        domain=state.get("query_domain") or QueryDomain.GENERAL,
        question=(plan.question if plan else state.get("question", "")),
        context=state.get("context_text", ""),
        chart_facts=state.get("chart_facts"),
        conversation=state.get("conversation"),
        rules=rule_context(state.get("matched_rules") or []),
        life_domain=(state.get("routing") or {}).get("primary"),
        contributors=state.get("contributor_reports") or (),
        council=council,
    )


def render_template(plan) -> str:
    """A grounded answer with no model involved.

    Plain, and deliberately not disguised as generated prose - a reader who
    gets this should be able to tell something degraded, rather than wonder why
    the Rishi suddenly writes in lists.
    """
    if plan.insufficient or not plan.allowed:
        return INSUFFICIENT

    lines = []
    for claim in plan.allowed:
        subject = claim.claim_id.split(".", 1)[-1].replace("_", " ")
        line = f"On {subject}: {claim.phrasing} — {', '.join(claim.citations)}."
        if claim.counter:
            line += f" Against it: {', '.join(claim.counter)}."
        if not claim.corroborated:
            line += " This is an indication rather than a settled finding."
        if claim.window:
            line += f" The period this could act in is {claim.window}."
        lines.append(line)

    for must in plan.must_say:
        lines.append(must)

    return "\n\n".join(lines)


def stream_answer(plan, *, client, state=None) -> Generator[str, None, None]:
    """The answer, chunk by chunk.

    Falls back to the template on any model failure, including one that lands
    **mid-stream** - which is the realistic case and the one a naive try/except
    around the whole loop gets wrong. A reader must not be left with half a
    sentence, so the accumulated partial is discarded and the template replaces
    it whole. Losing three good words is a smaller cost than an answer that
    stops mid-clause.
    """
    if plan is None or plan.insufficient or not plan.allowed:
        # No model call at all. Composing prose over nothing is the failure the
        # grounding discipline exists to prevent, and paying a model to do it
        # is that failure with an invoice attached.
        yield INSUFFICIENT
        return

    from rishivan.council.client import model_name

    prompt = build_narration_prompt(plan, state=state)
    emitted: list[str] = []
    try:
        for chunk in client.models.generate_content_stream(
            model=model_name(MODEL_TIER), contents=prompt
        ):
            if chunk.text:
                emitted.append(chunk.text)
                yield chunk.text
    except Exception:  # noqa: BLE001
        if emitted:
            # Already on the reader's screen and unretractable. Mark the seam
            # rather than pretending the sentence finished.
            yield "\n\n---\n\n"
        yield render_template(plan)


def stream_for(final, *, client):
    """The stream a finished run should hand back, or None.

    `None` on the insufficient path is the contract, not an oversight:
    `streamlit_app` renders its own warning for it, and `council_consult`
    returned None there long before this phase. Streaming a canned refusal
    inside a Rishi answer card, avatar and sign-off included, would be a
    better product decision quite possibly — but it is a product decision, and
    this phase moves narration without changing what it says.

    Lives here rather than as a branch in `council_consult`, because that
    adapter is meant to be branch-free and a test asserts it.
    """
    if final.get("outcome") == "insufficient":
        return None
    return stream_answer(final.get("answer_plan"), client=client, state=final)
