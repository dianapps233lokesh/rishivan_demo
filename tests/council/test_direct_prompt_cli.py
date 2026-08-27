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

    def test_it_works_without_birth_data(self):
        prompt = prompt_for("what is a nakshatra?", dob=None, tob=None,
                            place="", lat=None, lon=None, tz_offset=5.5,
                            when="2026-08-25")
        assert "No chart was computed" in prompt

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
