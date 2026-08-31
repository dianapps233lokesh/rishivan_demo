"""The reasoning call: its config, its retry, and what it refuses to repair."""

import json

import pytest

from rishivan.council.analyse import RETRY_PREFACE, analyse
from rishivan.council.verdict import VerdictError

GOOD = {
    "promise": "carried",
    "headline": "The promotion lands in late 2026.",
    "factors": [{"fact": "Mars, house 10", "consequence": "recognition",
                 "weight": "strong"}],
}


class _Response:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _Response(nxt)


class FakeClient:
    def __init__(self, *responses):
        self.models = FakeModels(responses)


class TestAnalyse:
    def test_it_returns_a_parsed_verdict(self):
        client = FakeClient(json.dumps(GOOD))
        verdict = analyse("PROMPT", client=client, echo=False)
        assert verdict.promise == "carried"
        assert verdict.factors[0].fact == "Mars, house 10"

    def test_it_uses_the_pro_tier(self):
        """The whole point of the split. If this silently ran on flash, the
        two-call lane would be an extra call that bought nothing."""
        from rishivan.council.client import model_name

        client = FakeClient(json.dumps(GOOD))
        analyse("PROMPT", client=client, echo=False)
        assert client.models.calls[0]["model"] == model_name("pro")
        assert model_name("pro") != model_name("flash")

    def test_temperature_is_zero(self):
        client = FakeClient(json.dumps(GOOD))
        analyse("PROMPT", client=client, echo=False)
        assert client.models.calls[0]["config"].temperature == 0.0

    def test_it_asks_for_the_schema(self):
        from rishivan.council.verdict import VERDICT_SCHEMA

        client = FakeClient(json.dumps(GOOD))
        analyse("PROMPT", client=client, echo=False)
        config = client.models.calls[0]["config"]
        assert config.response_mime_type == "application/json"
        assert config.response_schema == VERDICT_SCHEMA

    def test_it_sends_the_prompt_verbatim(self):
        client = FakeClient(json.dumps(GOOD))
        analyse("PROMPT", client=client, echo=False)
        assert client.models.calls[0]["contents"] == "PROMPT"


class TestRetry:
    def test_a_bad_first_response_is_retried_once(self):
        client = FakeClient("not json", json.dumps(GOOD))
        assert analyse("PROMPT", client=client, echo=False).promise == "carried"
        assert len(client.models.calls) == 2

    def test_the_retry_tells_the_model_what_broke(self):
        """A blind retry at temperature 0 sends the identical prompt and gets
        the identical failure. The error has to travel back."""
        client = FakeClient("not json", json.dumps(GOOD))
        analyse("PROMPT", client=client, echo=False)
        second = client.models.calls[1]["contents"]
        assert second.startswith("PROMPT")
        assert RETRY_PREFACE in second

    def test_two_failures_raise(self):
        client = FakeClient("not json", "still not json")
        with pytest.raises(VerdictError):
            analyse("PROMPT", client=client, echo=False)
        assert len(client.models.calls) == 2

    def test_a_transport_failure_raises_as_a_verdict_error(self):
        """The caller has one thing to catch, whether the model was unreachable
        or merely incoherent."""
        client = FakeClient(RuntimeError("vertex is down"),
                            RuntimeError("vertex is still down"))
        with pytest.raises(VerdictError):
            analyse("PROMPT", client=client, echo=False)
