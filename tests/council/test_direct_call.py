"""The one call, its config, and the dump that makes the comparison possible."""

from rishivan.council.direct import stream_direct


class _Chunk:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, chunks=("Marriage ", "is close."), explode_after=None):
        self.chunks, self.explode_after = chunks, explode_after
        self.calls = []

    def generate_content_stream(self, **kwargs):
        self.calls.append(kwargs)
        for index, text in enumerate(self.chunks):
            if self.explode_after is not None and index == self.explode_after:
                raise RuntimeError("the model fell over")
            yield _Chunk(text)


class FakeClient:
    def __init__(self, **kw):
        self.models = FakeModels(**kw)


class TestStreamDirect:
    def test_it_streams_the_chunks(self):
        client = FakeClient()
        assert "".join(stream_direct("PROMPT", client=client)) == "Marriage is close."

    def test_it_sends_the_prompt_verbatim(self):
        client = FakeClient()
        list(stream_direct("PROMPT", client=client))
        assert client.models.calls[0]["contents"] == "PROMPT"

    def test_temperature_is_zero(self):
        """Reproducibility is the point: the same prompt must give the same
        reading twice, or a comparison against three other platforms is
        measuring sampling noise."""
        client = FakeClient()
        list(stream_direct("PROMPT", client=client))
        config = client.models.calls[0]["config"]
        assert config.temperature == 0.0

    def test_thinking_is_on(self):
        client = FakeClient()
        list(stream_direct("PROMPT", client=client))
        config = client.models.calls[0]["config"]
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_budget != 0

    def test_it_uses_the_flash_tier(self):
        from rishivan.council.client import model_name
        client = FakeClient()
        list(stream_direct("PROMPT", client=client))
        assert client.models.calls[0]["model"] == model_name("flash")

    def test_a_midstream_failure_discards_the_partial(self):
        """Half a sentence on a reader's screen is worse than a stated failure.
        Same decision narrate.stream_answer makes, minus the template - there is
        no AnswerPlan in this lane to render one from."""
        client = FakeClient(chunks=("Marriage ", "is close."), explode_after=1)
        out = "".join(stream_direct("PROMPT", client=client))
        assert "is close." not in out
        assert "could not" in out.lower()

    def test_a_failure_before_the_first_chunk_says_so(self):
        client = FakeClient(explode_after=0)
        out = "".join(stream_direct("PROMPT", client=client))
        assert out.strip()
        assert "could not" in out.lower()


class TestTheConsoleDump:
    def test_the_whole_prompt_is_printed(self, capsys):
        list(stream_direct("THE ENTIRE PROMPT", client=FakeClient()))
        assert "THE ENTIRE PROMPT" in capsys.readouterr().out

    def test_it_is_delimited_so_it_can_be_copied(self, capsys):
        list(stream_direct("PROMPT", client=FakeClient()))
        out = capsys.readouterr().out
        assert "DIRECT PROMPT" in out
        assert "END DIRECT PROMPT" in out

    def test_it_prints_before_the_call_not_after(self, capsys):
        """So a prompt that makes the model fail is still on screen."""
        list(stream_direct("PROMPT", client=FakeClient(explode_after=0)))
        assert "PROMPT" in capsys.readouterr().out

    def test_it_reports_the_size(self, capsys):
        list(stream_direct("PROMPT", client=FakeClient()))
        assert "chars" in capsys.readouterr().out

    def test_echo_can_be_turned_off(self, capsys):
        list(stream_direct("PROMPT", client=FakeClient(), echo=False))
        assert "DIRECT PROMPT" not in capsys.readouterr().out
