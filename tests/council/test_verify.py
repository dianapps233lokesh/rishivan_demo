"""Did the prose stay inside the plan?

**A measurement, not a guardrail.** Once a chunk has been yielded it is on the
reader's screen, and nothing here can retract it. The gate is on the prompt —
this runs afterwards, records what leaked into the trace, and fails the eval
harness loudly, which is where it earns its keep.

The two tests that matter most are the ones that keep it quiet:
`test_a_faithful_answer_produces_no_violations` and
`test_the_template_never_violates_its_own_plan`. A verifier that fires on
everything gets switched off, and then it protects nothing.
"""

import inspect

import pytest

from rishivan.council import verify as verify_module
from rishivan.council.answer_plan import AllowedClaim, AnswerPlan
from rishivan.council.narrate import render_template
from rishivan.council.verify import verify_answer

STRONG = AllowedClaim(
    claim_id="wealth.accumulation", band="strongly_indicated",
    phrasing="strongly indicated", confidence=0.78,
    citations=("bphs ch34.v12",), rule_ids=("R1",), tier="house",
    counter=("saravali ch5.v3",), corroborated=True,
)

WEAK = AllowedClaim(
    claim_id="wealth.loss", band="some_indications",
    phrasing="some indications suggest", confidence=0.42,
    citations=("phaladeepika ch2.v9",), rule_ids=("R2",), tier="varga",
    corroborated=False,
)

DATED = AllowedClaim(
    claim_id="career.rise", band="strongly_indicated",
    phrasing="strongly indicated", confidence=0.8,
    citations=("bphs ch10.v1",), rule_ids=("R3",), tier="house",
    corroborated=True, window="Aug 2026 – Aug 2036",
)


def _plan(allowed=(STRONG,), **kw):
    base = dict(question="q", domain="domain.wealth", allowed=tuple(allowed),
                must_say=(), must_not_say=(), disagreement="",
                insufficient=False, unreviewed=False)
    base.update(kw)
    return AnswerPlan(**base)


# ==========================================================================
# Dates
# ==========================================================================


def test_a_date_with_no_window_behind_it_is_a_violation():
    violations = verify_answer("You will marry in 2028.", _plan())
    assert any(v.kind == "uncited_date" for v in violations)


def test_a_date_with_a_window_is_not_a_violation():
    text = "The period this could act in is Aug 2026 – Aug 2036."
    assert not [v for v in verify_answer(text, _plan([DATED]))
                if v.kind == "uncited_date"]


def test_a_month_and_year_counts_as_a_date():
    assert any(v.kind == "uncited_date"
               for v in verify_answer("Expect it around March 2029.", _plan()))


def test_a_vague_period_is_not_a_date():
    """"in the coming years" is not a prediction anyone can score, and
    flagging it makes the verifier noise."""
    assert not verify_answer(
        "In the coming years this is strongly indicated — bphs ch34.v12. "
        "Against it: saravali ch5.v3.", _plan())


# ==========================================================================
# Bands
# ==========================================================================


@pytest.mark.parametrize("word", [
    "will definitely", "guaranteed", "certainly", "without doubt", "for sure",
])
def test_certainty_language_over_a_weak_band_is_a_violation(word):
    text = f"This {word} happens — phaladeepika ch2.v9."
    assert any(v.kind == "overclaimed_band"
               for v in verify_answer(text, _plan([WEAK])))


def test_certainty_language_is_still_wrong_over_a_strong_band():
    """`consistently_supported` is the top band this system has and it is not
    certainty. Nothing licenses "guaranteed"."""
    assert any(v.kind == "overclaimed_band"
               for v in verify_answer(
                   "This is guaranteed — bphs ch34.v12. "
                   "Against it: saravali ch5.v3.", _plan()))


# ==========================================================================
# Counter-evidence
# ==========================================================================


def test_stating_a_claim_and_suppressing_its_counter_is_a_violation():
    """The half every product drops. If it survives the plan and dies in the
    prose, it has been dropped — just at the last possible moment."""
    text = "Wealth accumulation is strongly indicated — bphs ch34.v12."
    assert any(v.kind == "suppressed_counter"
               for v in verify_answer(text, _plan()))


def test_stating_the_counter_clears_it():
    text = ("Wealth accumulation is strongly indicated — bphs ch34.v12. "
            "Against it, saravali ch5.v3 says otherwise.")
    assert not [v for v in verify_answer(text, _plan())
                if v.kind == "suppressed_counter"]


def test_a_claim_with_no_counter_evidence_cannot_suppress_any():
    assert not [v for v in verify_answer("Some indications suggest a loss.",
                                         _plan([WEAK]))
                if v.kind == "suppressed_counter"]


# ==========================================================================
# Staying quiet
# ==========================================================================


def test_a_faithful_answer_produces_no_violations():
    """The check that stops the verifier becoming noise."""
    text = ("Wealth accumulation is strongly indicated — bphs ch34.v12. "
            "Against it: saravali ch5.v3.")
    assert verify_answer(text, _plan()) == []


def test_the_template_never_violates_its_own_plan():
    """The strongest test in the phase. The template is generated FROM the
    plan; if it can violate the plan, the plan is not what it is generated
    from — and the fallback would be shipping the failure it exists to
    prevent."""
    for plan in (_plan(), _plan([WEAK]), _plan([DATED]),
                 _plan([STRONG, WEAK, DATED]),
                 _plan([STRONG], must_say=("D60 was withheld.",)),
                 _plan((), insufficient=True)):
        assert verify_answer(render_template(plan), plan) == [], plan.claim_ids()


def test_an_empty_answer_is_not_a_violation():
    """It is a different problem, and reporting it here would put the
    verifier in the business of judging length."""
    assert verify_answer("", _plan()) == []


def test_a_declining_answer_is_not_a_violation():
    from rishivan.council.narrate import INSUFFICIENT

    assert verify_answer(INSUFFICIENT, _plan((), insufficient=True)) == []


# ==========================================================================
# Shape
# ==========================================================================


def test_a_violation_says_what_and_where():
    violation = verify_answer("You will marry in 2028.", _plan())[0]
    assert violation.kind and violation.detail
    assert "2028" in violation.detail


def test_the_verifier_calls_no_model_and_reads_no_clock():
    source = inspect.getsource(verify_module)
    assert "generate_content" not in source
    assert "datetime.now" not in source


def test_it_is_deterministic():
    text = "You will marry in 2028."
    assert verify_answer(text, _plan()) == verify_answer(text, _plan())
