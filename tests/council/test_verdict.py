"""The contract between the two calls, and the gate that enforces it.

Every test here runs without a client, a network or a database. That is the
point: what pro is allowed to hand flash is a pure-data question, and it should
be answerable — and wrong-answerable — without spending a token.
"""

import pytest

from rishivan.council.verdict import (
    VERDICT_SCHEMA, Verdict, VerdictError, apply_gate, parse_verdict,
)

PROMPT = """
THE CHART
 natal    Saturn   Pisces    6    debilitated
 natal    Mars     Capricorn 10   exalted

COMPUTED PERIODS
  - Sun mahadasha, 2021-08-14 to 2027-08-14 [RUNNING NOW]
  - Sun/Rahu antardasha, 2026-11-14 to 2027-09-02 [future]
  - Sun/Moon antardasha, 2022-01-02 to 2022-07-01 [past]

RAHU KAAL today: 13:42 to 15:16
"""

RAW = {
    "promise": "carried",
    "headline": "The promotion lands between late 2026 and late 2027.",
    "not_happening": "Nothing arrives in the next three months.",
    "factors": [
        {"fact": "Mars, house 10", "consequence": "recognition through delivery",
         "weight": "strong"},
        {"fact": "Saturn, house 6", "consequence": "a senior person blocks you",
         "weight": "moderate"},
    ],
    "windows": [
        {"start": "2026-11-14", "end": "2027-09-02",
         "label": "Sun/Rahu antardasha", "status": "future"},
    ],
    "exact_times": [{"label": "Rahu Kaal", "value": "13:42 to 15:16"}],
    "disagreements": ["The D10 argues earlier than the transit does"],
    "unsupported": ["D10 was not computed"],
    "falsifier": "No change of reporting line by September 2027.",
}


def _raw(**overrides):
    return {**RAW, **overrides}


class TestParse:
    def test_it_reads_the_whole_object(self):
        verdict = parse_verdict(RAW)
        assert verdict.promise == "carried"
        assert verdict.headline.startswith("The promotion")
        assert len(verdict.factors) == 2
        assert verdict.factors[0].fact == "Mars, house 10"
        assert verdict.windows[0].label == "Sun/Rahu antardasha"
        assert verdict.exact_times[0].value == "13:42 to 15:16"
        assert verdict.disagreements == ("The D10 argues earlier than the transit does",)
        assert verdict.unsupported == ("D10 was not computed",)

    def test_it_reads_a_json_string(self):
        import json
        assert parse_verdict(json.dumps(RAW)).promise == "carried"

    def test_it_strips_a_fenced_block(self):
        """Models fence JSON even when told not to, and a fence is not a reason
        to fail a turn the model otherwise got right."""
        import json
        fenced = f"```json\n{json.dumps(RAW)}\n```"
        assert parse_verdict(fenced).headline == RAW["headline"]

    def test_unparseable_json_raises(self):
        with pytest.raises(VerdictError):
            parse_verdict("not json at all")

    def test_an_unknown_promise_raises(self):
        with pytest.raises(VerdictError):
            parse_verdict(_raw(promise="probably"))

    def test_a_missing_headline_raises(self):
        """The headline IS the answer. A verdict without one has nothing for the
        narrator to lead with, and leading is the one thing the output block
        insists on."""
        with pytest.raises(VerdictError):
            parse_verdict(_raw(headline="   "))

    def test_an_unknown_window_status_raises(self):
        with pytest.raises(VerdictError):
            parse_verdict(_raw(windows=[
                {"start": "2026-11-14", "end": "2027-09-02",
                 "label": "x", "status": "soon"},
            ]))

    def test_a_factor_without_a_consequence_is_dropped(self):
        """A bare placement is exactly what the prose rules forbid. Dropping it
        here is cheaper than asking flash to translate it and hoping."""
        verdict = parse_verdict(_raw(factors=[
            {"fact": "Saturn, house 6", "consequence": "", "weight": "strong"},
            RAW["factors"][0],
        ]))
        assert [f.fact for f in verdict.factors] == ["Mars, house 10"]

    def test_an_unknown_weight_becomes_moderate(self):
        verdict = parse_verdict(_raw(factors=[
            {"fact": "Mars, house 10", "consequence": "x", "weight": "enormous"},
        ]))
        assert verdict.factors[0].weight == "moderate"


class TestGate:
    def test_a_clean_verdict_survives_intact(self):
        gated = apply_gate(parse_verdict(RAW), PROMPT)
        assert len(gated.windows) == 1
        assert len(gated.factors) == 2
        assert gated.dropped == ()

    def test_a_window_whose_dates_are_not_in_the_prompt_is_dropped(self):
        """The one invention this lane has to make impossible. Swiss Ephemeris
        owns every date; a boundary the prompt never printed was derived by the
        model, whatever it says."""
        gated = apply_gate(parse_verdict(_raw(windows=[
            {"start": "2029-03-01", "end": "2030-01-01",
             "label": "invented", "status": "future"},
        ])), PROMPT)
        assert gated.windows == ()
        assert any("2029-03-01" in reason for reason in gated.dropped)

    def test_a_past_window_is_dropped(self):
        gated = apply_gate(parse_verdict(_raw(windows=[
            {"start": "2022-01-02", "end": "2022-07-01",
             "label": "Sun/Moon antardasha", "status": "past"},
        ])), PROMPT)
        assert gated.windows == ()

    def test_an_absent_promise_clears_every_window(self):
        """Nothing to time. Handing the narrator a window under an absent
        promise is how a 'the chart does not carry this' answer grows a date."""
        gated = apply_gate(parse_verdict(_raw(promise="absent")), PROMPT)
        assert gated.windows == ()
        assert gated.promise == "absent"

    def test_a_factor_naming_a_graha_the_prompt_never_printed_is_dropped(self):
        gated = apply_gate(parse_verdict(_raw(factors=[
            {"fact": "Venus, house 7", "consequence": "a marriage",
             "weight": "strong"},
            RAW["factors"][0],
        ])), PROMPT)
        assert [f.fact for f in gated.factors] == ["Mars, house 10"]
        assert any("Venus" in reason for reason in gated.dropped)

    def test_a_factor_carrying_a_date_the_prompt_never_printed_is_dropped(self):
        gated = apply_gate(parse_verdict(_raw(factors=[
            {"fact": "Sun/Ketu antardasha, 2031-04-04 to 2032-01-01",
             "consequence": "a move", "weight": "weak"},
        ])), PROMPT)
        assert gated.factors == ()

    def test_an_exact_time_not_in_the_prompt_is_dropped(self):
        """These are copied character for character or they are wrong. A time
        the prompt did not print was not copied."""
        gated = apply_gate(parse_verdict(_raw(exact_times=[
            {"label": "Rahu Kaal", "value": "09:00 to 10:30"},
        ])), PROMPT)
        assert gated.exact_times == ()

    def test_the_gate_never_invents(self):
        """Whatever survives was present before. Restated as a property because
        a gate that adds is a gate nobody can reason about."""
        gated = apply_gate(parse_verdict(RAW), PROMPT)
        assert set(f.fact for f in gated.factors) <= set(
            f["fact"] for f in RAW["factors"]
        )


class TestSchema:
    def test_every_field_the_parser_reads_is_declared(self):
        """A field pro is never asked for is a field pro will never send."""
        declared = set(VERDICT_SCHEMA["properties"])
        assert declared == set(RAW)

    def test_the_required_fields_are_the_ones_the_parser_insists_on(self):
        assert set(VERDICT_SCHEMA["required"]) == {"promise", "headline", "factors"}
