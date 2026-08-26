"""One Rishi's turn. One node function, many `Send`s.

Eight near-identical node functions would be eight places to apply a prompt fix
seven times, and the seventh is the one that gets missed. The persona arrives in
the `Send` payload as `state["rishi"]`.

**This node writes exactly one key, and that is not a style choice.** `reports`
is the only channel in `RishivanState` with a reducer. A fanned-out node writing
any other key raises `InvalidUpdateError` at runtime, on a concurrent branch no
node-level test can reach - so the constraint is pinned by a test here instead.

**Failure is an abstention, never an exception.** A Rishi that times out,
returns prose, or writes a report that breaks the contract costs one opinion.
Synthesis proceeds with fewer voices and says how many. The alternative is one
model hiccup taking down a reading that seven other Rishis had already grounded.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState

MODEL_TIER = "flash"


def rishi_node(state: RishivanState, *, client) -> dict:
    """Reason over the evidence, and file a report about it.

    Note the parameter name is `client`, not `store`/`config`/`writer`/
    `runtime` - LangGraph injects those four *by name* and would override
    whatever `functools.partial` bound.
    """
    from rishivan.council.client import model_name
    from rishivan.council.rishis.contract import REPORT_SCHEMA, parse_report
    from rishivan.council.rishis.prompt import build_rishi_report_prompt

    rishi = state.get("rishi") or "vyom"
    domain = state.get("koonji_domain") or ""

    prompt = build_rishi_report_prompt(
        rishi=rishi,
        question=state["question"],
        hierarchy=state.get("hierarchy"),
        chart_state=state.get("chart_state"),
        reading=state.get("reading"),
        vargas=state.get("vargas"),
        timing=state.get("timing"),
        unreviewed=bool(state.get("reading_is_unreviewed")),
        findings=tuple((state.get("findings_for") or {}).get(rishi, ())),
    )

    try:
        response = client.models.generate_content(
            model=model_name(MODEL_TIER),
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": REPORT_SCHEMA,
                "temperature": 0.2,
            },
        )
        report = parse_report(response.text, rishi=rishi, domain=domain)
    except Exception as exc:  # noqa: BLE001
        report = parse_report(
            "", rishi=rishi, domain=domain,
            on_error=f"could not reach the model: {type(exc).__name__}",
        )

    return {"reports": [report]}
