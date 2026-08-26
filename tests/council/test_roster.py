"""Which Rishis are invited, and the gate that stops the rest.

**The router proposes; the evidence disposes.** Inviting a Rishi whose evidence
subgraph is empty spends tokens to produce nothing — and worse, produces
confident-sounding filler, because a model asked for an opinion supplies one.
That is the failure mode this file exists to prevent, and it is invisible in the
output: the filler reads exactly like an opinion.
"""

from datetime import datetime

import pytest

from rishivan.council.rishis.roster import (
    ALWAYS,
    AUDITOR,
    MAX_RISHIS,
    ROLES,
    route_rishis,
)
from rishivan.graph.state import initial_state


class _FakeReading:
    def __init__(self, domains):
        self._domains = set(domains)

    def rule_domains_seen(self):
        return sorted(self._domains)

    def promises(self, domain):
        return domain in self._domains


def _state(question="will I become wealthy?", *, domain="domain.wealth",
           domains_fired=("domain.wealth",), spec=None):
    from rishivan.council.hierarchy import hierarchy_for

    s = initial_state(question, query_time=datetime(2026, 8, 26, 12, 0))
    s["koonji_domain"] = domain
    s["hierarchy"] = hierarchy_for(domain)
    s["reading"] = _FakeReading(domains_fired) if domains_fired else None
    if spec is not None:
        s["spec"] = spec
    return s


def _targets(sends):
    return [s.arg["rishi"] for s in sends]


# ==========================================================================
# The roster
# ==========================================================================


def test_every_persona_has_a_role():
    from rishivan.council.personas import ALL_RISHI_NAMES

    assert set(ALL_RISHI_NAMES) <= set(ROLES)


def test_sakshi_is_a_role_without_a_persona():
    """It audits; it never speaks in a voice. Adding a ninth persona would
    break `ALL_RISHI_NAMES` and the no-orphan-domain test for no gain."""
    from rishivan.council.personas import ALL_RISHI_NAMES

    assert AUDITOR in ROLES
    assert AUDITOR not in ALL_RISHI_NAMES


def test_every_role_states_its_remit():
    """A role a reviewer cannot read is a role nobody can tell is being played
    wrong. The remit goes in the prompt."""
    for name, role in ROLES.items():
        assert role.remit.strip(), name


def test_the_always_rishi_is_a_real_role():
    for name in ALWAYS:
        assert name in ROLES


# ==========================================================================
# Routing
# ==========================================================================


def test_the_classical_voice_always_runs():
    assert "vyom" in _targets(route_rishis(_state()))


def test_the_domain_rishi_for_marriage_is_invited():
    sends = route_rishis(_state(
        "when will I get married?", domain="domain.relationship",
        domains_fired=("domain.relationship",)))
    assert "medhan" in _targets(sends)


def test_the_domain_rishi_for_wealth_is_invited():
    assert "dhruvan" in _targets(route_rishis(_state()))


def test_a_rishi_with_no_fired_rules_is_not_invited():
    """The gate. A wealth reading must not summon the marriage Rishi merely
    because the roster lists one."""
    targets = _targets(route_rishis(_state(domains_fired=("domain.wealth",))))
    assert "medhan" not in targets


def test_no_reading_means_the_classical_voice_alone():
    """Nothing fired, so nothing but the general synthesis has evidence to
    speak from."""
    assert _targets(route_rishis(_state(domains_fired=()))) == list(ALWAYS)


def test_a_reading_that_fired_nothing_invites_no_domain_rishi():
    assert _targets(route_rishis(_state(domains_fired=()))) == list(ALWAYS)


def test_the_auditor_is_not_in_the_fanout():
    """It runs after, on the reports. Fanning it out with its own subjects
    means auditing an empty list."""
    assert AUDITOR not in _targets(route_rishis(_state()))


def test_the_fanout_is_capped():
    """§12's "invoke the minimum set". The fifth marginal Rishi on a wealth
    question is agreeing with the fourth, and agreement between restatements
    is what the evidence graph already discounts."""
    sends = route_rishis(_state(
        domains_fired=tuple(
            d for d in __import__(
                "rishivan.council.hierarchy", fromlist=["HIERARCHIES"]
            ).HIERARCHIES
        )))
    assert len(sends) <= MAX_RISHIS


def test_nobody_is_invited_twice():
    sends = route_rishis(_state(
        domains_fired=("domain.wealth", "domain.career", "domain.property")))
    targets = _targets(sends)
    assert len(targets) == len(set(targets))


def test_the_always_rishi_comes_first():
    """Order is not cosmetic — it is what the synthesis reads as the primary
    classical reading against which the specialists are compared."""
    assert _targets(route_rishis(_state()))[0] == ALWAYS[0]


def test_each_send_carries_the_persona_it_is_for():
    for send in route_rishis(_state()):
        assert send.arg["rishi"] in ROLES


def test_each_send_targets_the_one_rishi_node():
    """One node function, many Sends. Eight near-identical node functions
    would be eight places to apply a prompt fix seven times."""
    for send in route_rishis(_state()):
        assert send.node == "rishi"


def test_routing_is_deterministic():
    a = _targets(route_rishis(_state()))
    b = _targets(route_rishis(_state()))
    assert a == b


def test_the_timing_rishi_is_invited_only_for_a_timing_question():
    from rishivan.koonji.router import parse

    plain = _state("what is my wealth like?",
                   spec=parse("what is my wealth like?"))
    assert "ritam" not in _targets(route_rishis(plain))

    timed = _state("when will I become wealthy?",
                   spec=parse("when will I become wealthy?"))
    assert "ritam" in _targets(route_rishis(timed))
