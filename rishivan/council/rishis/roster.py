"""Which Rishis are invited, and the gate that keeps the rest out.

**The existing eight personas keep their names.** `agam`, `vyom`, `ritam` and
the rest are annotated across the whole corpus as `rishi_affinity`, and renaming
them would silently change what every one of those annotations means. What this
file adds is a *role* per persona: an analytical remit, the state it is given,
and the condition under which it is invited at all.

**Sakshi is a role with no persona**, because it never speaks in a voice - it
audits. Adding a ninth persona would break `ALL_RISHI_NAMES` and the no-orphan
coverage test for nothing gained.

**The router proposes; the evidence disposes.** A Rishi is invited only when
rules in the domains it may argue from actually fired. Inviting one whose
subgraph is empty spends tokens to produce nothing, and worse, produces
confident-sounding filler - a model asked for an opinion supplies one, and the
filler reads exactly like an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.types import Send

from rishivan.council.hierarchy import koonji_domains_for_rishi

RISHI_NODE = "rishi"
"""One node function, many `Send`s. Eight near-identical node functions would be
eight places to apply a prompt fix seven times, and the seventh gets missed."""

AUDITOR = "sakshi"

ALWAYS: tuple[str, ...] = ("vyom",)
"""The primary classical synthesis, invited whatever the question.

`vyom` rates every life domain uniformly and is already the classifier's
fallback voice, which makes it the one Rishi that can speak to a reading nobody
else has coverage of. Without it, a question routed to a domain no persona
specialises in would convene an empty council.
"""

MAX_RISHIS = 5
"""Four specialists plus the classical voice.

§12's "invoke the minimum set" is a cost statement and a quality one. The fifth
marginal Rishi on a wealth question is agreeing with the fourth, and agreement
between two restatements of the same evidence is exactly what the evidence graph
already discounts - paying a model to generate it does not make it independent.
"""

TIMING_RISHI = "ritam"


@dataclass(frozen=True, slots=True)
class RishiRole:
    persona: str
    remit: str
    """One sentence, and it goes into the prompt verbatim. A role a reviewer
    cannot read is a role nobody can tell is being played wrong."""

    reads: tuple[str, ...]
    """The state keys this role is handed, and this is load-bearing rather than
    documentation.

    **`Send(node, arg)` REPLACES the node's state with `arg`.** It does not
    merge. A `Send("rishi", {"rishi": "medhan"})` gives that node a state
    containing one key, and every `state.get("reading")` in it returns None -
    silently, producing a report about a chart the Rishi never saw. Measured,
    not assumed: a two-node scratch graph confirms the outer state does not
    reach a fanned-out node.

    So `route_rishis` copies these keys into the payload, and
    `test_the_payload_carries_what_the_role_reads` pins it.
    """

    always: bool = False
    timing_only: bool = False


_CHART = ("chart_state", "reading", "hierarchy")
_TIMED = _CHART + ("timing",)

ROLES: dict[str, RishiRole] = {
    "vyom": RishiRole(
        persona="vyom",
        remit="the classical Parashari reading - houses, lordships, "
              "dignities and the divisional charts that confirm or "
              "contradict them",
        reads=_TIMED + ("vargas",),
        always=True,
    ),
    "ritam": RishiRole(
        persona="ritam",
        remit="when, and on what basis - the dasha periods that activate "
              "what the chart promises, and the honest admission when a "
              "promise has no period to land in",
        reads=_TIMED,
        timing_only=True,
    ),
    "dhruvan": RishiRole(
        persona="dhruvan",
        remit="the material domains - wealth, career, property and the "
              "journeys taken for them",
        reads=_CHART,
    ),
    "medhan": RishiRole(
        persona="medhan",
        remit="the relational and bodily domains - marriage, family, "
              "children and health",
        reads=_CHART,
    ),
    "tattvan": RishiRole(
        persona="tattvan",
        remit="the chart's own shape - temperament, strengths, the "
              "patterns a domain reading would step over",
        reads=_CHART,
    ),
    "agam": RishiRole(
        persona="agam",
        remit="soul purpose and the karmic reading - what this chart is "
              "for, rather than what it will get",
        reads=_CHART,
    ),
    "pragnav": RishiRole(
        persona="pragnav",
        remit="the spiritual reading - dharma, renunciation, the 9th and "
              "12th and what they ask of this native",
        reads=_CHART,
    ),
    "tejan": RishiRole(
        persona="tejan",
        remit="remedies - and only where a fired rule prescribes one, "
              "never as consolation for an unwelcome reading",
        reads=_CHART,
    ),
    AUDITOR: RishiRole(
        persona="",
        remit="the adversarial audit - what the council missed, asserted "
              "without evidence, or agreed on too easily",
        reads=_TIMED + ("reports",),
    ),
}


def _is_timing_question(state) -> bool:
    """A question with a time component, from the parse rather than keywords.

    `TIMING_ONLY` mode, or any payload carrying a resolved `time_scope` - which
    is what `koonji/router.py` sets when it finds "next year", "in 2027", "when
    will I". Re-deriving it here with a second regex would be a second thing to
    disagree with the router about.
    """
    from rishivan.koonji.question import Mode

    spec = state.get("spec")
    if spec is None:
        return False
    if spec.mode is Mode.TIMING_ONLY:
        return True
    return getattr(spec.payload, "time_scope", None) is not None


def _domains_that_fired(state) -> frozenset[str]:
    reading = state.get("reading")
    if reading is None:
        return frozenset()
    return frozenset(
        d for d in reading.rule_domains_seen() if reading.promises(d)
    )


def route_rishis(state) -> list[Send]:
    """The fan-out. Returns one `Send` per invited Rishi, ordered.

    Order is not cosmetic: the classical voice comes first because synthesis
    reads it as the reading the specialists are compared against.
    """
    fired = _domains_that_fired(state)
    timing = _is_timing_question(state)

    invited: list[str] = list(ALWAYS)
    for name, role in ROLES.items():
        if name == AUDITOR or name in invited:
            continue
        if role.timing_only and not timing:
            continue
        if not (koonji_domains_for_rishi(name) & fired):
            # No evidence in any domain this Rishi may argue from. Inviting it
            # anyway is how a council produces eight confident opinions about a
            # chart that fired three rules.
            continue
        invited.append(name)

    return [_send(state, name) for name in invited[:MAX_RISHIS]]


#: Carried into every payload whatever the role, because every prompt needs
#: them: what was asked, who is answering, and about which domain.
_UNIVERSAL = ("question", "koonji_domain", "reading_is_unreviewed", "findings_for")


def _send(state, rishi: str) -> Send:
    """One Rishi's whole input state.

    Built by copying rather than by reference to the outer state, because the
    outer state is not available inside a fanned-out node - see `RishiRole.reads`.
    """
    role = ROLES[rishi]
    payload: dict = {"rishi": rishi}
    for key in _UNIVERSAL + role.reads:
        if key in state:
            payload[key] = state[key]
    return Send(RISHI_NODE, payload)
