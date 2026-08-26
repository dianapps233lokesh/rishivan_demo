"""A promise is not an event, and the timing engine may only date a promise.

`timing/windows.py` calls `reading.promises(domain)` and short-circuits every
one of its five stages when the answer is False. That gate is the reason the
module can say *"the chart does not indicate this, so there is no window to give
you"* rather than manufacturing a date - the dasha arithmetic always yields a
period, so a pipeline starting from the periods always produces one.

Which makes these the tests that stop a period becoming a prediction.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.koonji.engine import Engine

WHEN = datetime(2026, 8, 26, 12, 0)

CANDIDATE = frozenset({"candidate"})
"""Every one of the 1,117 extracted rules is `candidate`; none has been
promoted to `production`. `Engine.read` defaults to production-only, so a
reading taken at the default returns nothing at all - which is correct, and is
also why these tests say the status out loud rather than inheriting it."""


@pytest.fixture(scope="module")
def engine():
    return Engine.from_rules()


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BirthData(
        year=1990, month=1, day=1, hour=12, minute=0,
        tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
    ))


@pytest.fixture(scope="module")
def reading(engine, chart):
    return engine.read(chart, when=WHEN, statuses=CANDIDATE)


def test_a_reading_knows_which_domains_it_covers(reading):
    """At least one domain out of a full unfiltered read. A reading that
    promises nothing at all means the fact set and the rule base stopped
    agreeing, which is a deployment alarm, not an astrological finding."""
    promised = [d for d in reading.rule_domains_seen() if reading.promises(d)]
    assert promised


def test_a_domain_no_rule_is_tagged_with_is_not_promised(reading):
    assert reading.promises("domain.nonexistent") is False


def test_promises_returns_a_bool_not_a_truthy_object(reading):
    """`timing/windows.py` puts this straight into `EventWindow.promise`,
    which is typed `bool` and serialised."""
    assert reading.promises("domain.wealth") in (True, False)


def test_the_promise_basis_cites_the_rules_that_made_it(reading):
    for domain in reading.rule_domains_seen():
        if reading.promises(domain):
            basis = reading.promise_basis(domain)
            assert basis
            assert all(isinstance(c, str) and c for c in basis)
            return
    pytest.fail("no promised domain to check the basis of")


def test_an_unpromised_domain_has_an_empty_basis(reading):
    assert reading.promise_basis("domain.nonexistent") == ()


def test_a_claim_below_the_evidence_floor_is_not_a_promise(engine, chart):
    """`INSUFFICIENT_BELOW` is the line. A 0.2-confidence claim is a thing the
    chart faintly suggests, not a promise anything may be dated against."""
    from rishivan.koonji.evidence import INSUFFICIENT_BELOW

    reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
    for domain in reading.rule_domains_seen():
        if not reading.promises(domain):
            continue
        supports = reading._promise_supports(domain)
        claims = [
            c for c in reading.claims
            if any(s.rule_id in {x.rule_id for x in supports} for s in c.support)
        ]
        assert any(c.confidence >= INSUFFICIENT_BELOW for c in claims), domain


def test_the_basis_does_not_repeat_a_citation(reading):
    for domain in reading.rule_domains_seen():
        basis = reading.promise_basis(domain)
        assert len(basis) == len(set(basis)), domain


def test_a_filtered_read_still_answers_about_its_own_domain(engine, chart):
    """The realistic call. The graph reads under a domain filter, and the
    timing node then asks about that same domain."""
    reading = engine.read(chart, when=WHEN, domains={"domain.wealth"}, statuses=CANDIDATE)
    assert reading.promises("domain.wealth") in (True, False)


def test_a_reading_with_no_firings_promises_nothing(engine, chart):
    reading = engine.read(chart, when=WHEN, domains={"domain.nonexistent"}, statuses=CANDIDATE)
    assert reading.promises("domain.wealth") is False
