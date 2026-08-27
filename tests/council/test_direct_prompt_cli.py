"""The script that makes the browser comparison mechanical."""

import pytest

from scripts.direct_prompt import main, prompt_for


class TestPromptFor:
    def test_it_builds_a_natal_prompt(self):
        prompt = prompt_for(
            "when will I marry?", dob="1990-01-01", tob="12:00",
            place="New Delhi", lat=28.6139, lon=77.2090, tz_offset=5.5,
            when="2026-08-25",
        )
        assert "READING METHOD" in prompt
        assert "when will I marry?" in prompt

    def test_the_question_routes_the_method(self):
        kw = dict(dob="1990-01-01", tob="12:00", place="New Delhi",
                  lat=28.6139, lon=77.2090, tz_offset=5.5, when="2026-08-25")
        marriage = prompt_for("when will I marry?", **kw)
        career = prompt_for("will I get a promotion?", **kw)
        assert "Love / Marriage / Relationships" in marriage
        assert "Love / Marriage / Relationships" not in career

    def test_without_birth_data_it_casts_a_prashna_chart_and_says_so(self):
        """It used to cast a moment chart and label the rows `natal`, which told
        the model that a planet passing through a sign that afternoon was a birth
        placement. It read it as exactly that, and a travel reading described a
        "debilitated natal Venus" that was really transiting Venus."""
        prompt = prompt_for("can I travel abroad tomorrow?", dob=None, tob=None,
                            place="", lat=None, lon=None, tz_offset=5.5,
                            when="2026-08-25")
        assert "THIS IS A PRASHNA READING" in prompt
        assert "prashna " in prompt          # the FRAME column
        # No ROW may claim to be natal. The word still appears in instructions -
        # the method's "natal promise" step, which the framing block remaps.
        rows = [ln for ln in prompt.splitlines()
                if ln[:1] in (" ", "*") and "Aries" in ln or "Pisces" in ln]
        assert not any(" natal " in ln for ln in rows)
        assert "no nativity" in prompt

    def test_a_prashna_reading_drops_the_facts_that_need_a_birth_moon(self):
        """Tara bala and chandra bala compare the transiting Moon against the
        BIRTH Moon. With a prashna chart both compare the Moon against itself -
        always Janma, always the 1st sign - and a reading built real advice on
        one of them."""
        prompt = prompt_for("can I travel abroad tomorrow?", dob=None, tob=None,
                            place="", lat=None, lon=None, tz_offset=5.5,
                            when="2026-08-25")
        assert "Tara bala" not in prompt
        assert "Chandra bala" not in prompt
        assert "Vimshottari dasha" in prompt  # declared unavailable instead

    def test_it_is_deterministic_for_a_fixed_when(self):
        kw = dict(dob="1990-01-01", tob="12:00", place="New Delhi",
                  lat=28.6139, lon=77.2090, tz_offset=5.5, when="2026-08-25")
        assert prompt_for("when will I marry?", **kw) == prompt_for(
            "when will I marry?", **kw
        )

    def test_a_natal_prompt_carries_the_computed_periods(self):
        """The dasha timeline is the only source of a date the model may write,
        so a prompt without it silently licenses invented ones."""
        prompt = prompt_for(
            "when will I marry?", dob="1990-01-01", tob="12:00",
            place="New Delhi", lat=28.6139, lon=77.2090, tz_offset=5.5,
            when="2026-08-25",
        )
        assert "COMPUTED PERIODS" in prompt
        assert "Mahadasha timeline from birth" in prompt


class TestCli:
    def test_it_prints_the_prompt_and_exits_zero(self, capsys):
        code = main([
            "--question", "when will I marry?",
            "--dob", "1990-01-01", "--tob", "12:00",
            "--place", "New Delhi", "--lat", "28.6139", "--lon", "77.2090",
            "--when", "2026-08-25",
        ])
        assert code == 0
        assert "READING METHOD" in capsys.readouterr().out

    def test_a_question_is_required(self):
        with pytest.raises(SystemExit):
            main([])

    def test_it_makes_no_model_call(self, monkeypatch, capsys):
        """No credentials, no network. This script must run on a laptop with
        nothing configured, which is where the comparison set gets built."""
        import builtins

        real_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.startswith(("google.genai", "qdrant_client")):
                raise AssertionError(f"the CLI imported {name}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", guarded)
        assert main(["--question", "when will I marry?"]) == 0
