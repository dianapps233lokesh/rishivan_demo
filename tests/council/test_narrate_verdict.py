"""The narration half: what flash is shown, and what it is structurally unable
to say because it was never shown it."""

import pytest

from rishivan.council.narrate_verdict import (
    build_narration_prompt, month_span, render_template, stream_verdict,
)
from rishivan.council.verdict import ExactTime, Factor, Verdict, Window

VERDICT = Verdict(
    promise="carried",
    headline="The promotion lands between late 2026 and late 2027.",
    not_happening="Nothing arrives in the next three months.",
    factors=(
        Factor("Mars, house 10 (D10)", "recognition through delivery", "strong"),
        Factor("Saturn, house 6", "a senior person keeps slowing your file", "weak"),
    ),
    windows=(
        Window("2026-11-14", "2027-09-02", "Sun/Rahu antardasha", "future"),
    ),
    exact_times=(ExactTime("Rahu Kaal", "13:42 to 15:16"),),
    disagreements=("The D10 argues earlier than the transit does",),
    unsupported=("D10 was not computed",),
    falsifier="No change of reporting line by September 2027.",
)


class TestMonthSpan:
    def test_it_rounds_a_span_to_months(self):
        assert month_span("2026-11-14", "2027-09-02") == "November 2026 to September 2027"

    def test_a_span_inside_one_month_still_reads(self):
        assert month_span("2026-11-02", "2026-11-27") == "November 2026"

    def test_an_unparseable_date_survives_rather_than_vanishing(self):
        assert "?" not in month_span("later", "2027-09-02")


class TestPrompt:
    @pytest.fixture
    def prompt(self):
        return build_narration_prompt(VERDICT, question="Will I be promoted?")

    def test_no_iso_date_reaches_the_narrator(self, prompt):
        """The strongest guarantee this split buys. Flash is told to write
        months rather than days, and separately it is never shown a day - so a
        day-exact forecast is not a rule it can break, it is a string it does
        not have."""
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", prompt) is None

    def test_the_window_arrives_already_in_months(self, prompt):
        assert "November 2026 to September 2027" in prompt
        assert "Sun/Rahu antardasha" in prompt

    def test_the_headline_and_the_negative_are_both_there(self, prompt):
        assert VERDICT.headline in prompt
        assert VERDICT.not_happening in prompt

    def test_every_factor_crosses_with_its_consequence(self, prompt):
        for factor in VERDICT.factors:
            assert factor.fact in prompt
            assert factor.consequence in prompt

    def test_exact_times_cross_verbatim(self, prompt):
        """The one class of value the reader gets to the minute. Rounding these
        destroys the answer rather than protecting it."""
        assert "13:42 to 15:16" in prompt

    def test_disagreement_and_unsupported_and_falsifier_all_cross(self, prompt):
        assert VERDICT.disagreements[0] in prompt
        assert VERDICT.unsupported[0] in prompt
        assert VERDICT.falsifier in prompt

    def test_the_question_is_there(self, prompt):
        assert "Will I be promoted?" in prompt

    def test_the_gate_audit_never_reaches_the_narrator(self):
        """`dropped` is for a trace. Telling flash what pro was not allowed to
        say hands it the material back."""
        verdict = Verdict(
            promise="carried", headline="Yes.",
            dropped=("window 2029-03-01..2030-01-01: not printed in the prompt",),
        )
        assert "2029" not in build_narration_prompt(verdict, question="q")

    def test_an_absent_promise_is_told_not_to_name_a_period(self):
        verdict = Verdict(promise="absent",
                          headline="The chart does not carry this.")
        prompt = build_narration_prompt(verdict, question="q")
        assert "does not carry" in prompt
        assert "PERIODS" not in prompt


class TestTemplate:
    def test_it_writes_a_real_answer_with_no_model(self):
        """The argument for the architecture, and something the single-call lane
        could never have: the verdict is structured, so when flash falls over
        there is still an answer and it is still the one pro reached."""
        text = render_template(VERDICT)
        assert VERDICT.headline in text
        assert "recognition through delivery" in text
        assert "November 2026 to September 2027" in text
        assert "13:42 to 15:16" in text

    def test_it_writes_no_day_exact_date_either(self):
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", render_template(VERDICT)) is None


class _Chunk:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, chunks, explode_after=None):
        self.chunks, self.explode_after = chunks, explode_after
        self.calls = []

    def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)
        for index, text in enumerate(self.chunks):
            if self.explode_after is not None and index == self.explode_after:
                raise RuntimeError("the model fell over")
            yield _Chunk(text)


class FakeClient:
    def __init__(self, chunks=("The promotion ", "is close."), explode_after=None):
        self.models = FakeModels(chunks, explode_after)


class TestStream:
    def test_it_streams(self):
        client = FakeClient()
        out = "".join(stream_verdict(VERDICT, client=client, question="q"))
        assert out == "The promotion is close."

    def test_it_narrates_on_flash(self):
        """Cheap model, and deliberately. Saying it well is not the job worth a
        frontier model; working it out was, and that already happened."""
        from rishivan.council.client import model_name

        client = FakeClient()
        list(stream_verdict(VERDICT, client=client, question="q"))
        assert client.models.calls[0]["model"] == model_name("flash")

    def test_a_mid_stream_failure_falls_back_to_the_template_whole(self):
        client = FakeClient(chunks=("The promo", "tion"), explode_after=1)
        out = "".join(stream_verdict(VERDICT, client=client, question="q"))
        assert VERDICT.headline in out
