"""A real `ModelClient` for the extractor. The only networked thing in koonji.

`extract.py` takes its client by injection and has only ever been given a
scripted one in tests. This is the other implementation: Vertex, through the
same service-account credentials the rest of the app uses, tagged so that
extraction spend is separable from chat spend in the Helicone dashboard.

It lives behind an import that the engine never touches. `koonji.engine` does
not import this module, `koonji.extract` does not import it either - the
extractor is handed an instance. So a serving pod that never extracts never
imports `google.genai`, and the rule that nothing in the serving path calls a
model stays structural rather than a convention people remember.

Retries are here rather than in `extract.py` for the same reason the client is
injected: a 429 is a property of the transport, and the pipeline should not have
to know what a 429 is.
"""

from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

PIPELINE_TAG = "koonji-extract"
"""Helicone property. Matches the tag `council/client.py` already documents."""

RETRYABLE = ("429", "500", "502", "503", "504", "resource_exhausted",
             "unavailable", "deadline", "timeout", "internal error")


class ExtractionUnavailable(RuntimeError):
    """The provider could not be reached after retries.

    Distinct from a bad response: a bad response is data the validator will
    catch, and this is nothing at all. Conflating them means a rate limit gets
    recorded as an extraction failure and the passage is never retried.
    """


class Truncated(ExtractionUnavailable):
    """The response ran into the output ceiling.

    A subclass, so a caller that only knows about `ExtractionUnavailable` still
    handles it - but distinguishable, because the fix is different. An
    unavailable provider wants a retry; a truncated response wants a bigger
    ceiling, and retrying it just spends the same money to hit the same wall.
    """


def _truncated(response: Any) -> bool:
    for candidate in getattr(response, "candidates", None) or ():
        reason = str(getattr(candidate, "finish_reason", "") or "")
        if "MAX_TOKENS" in reason.upper():
            return True
    return False


@dataclass(slots=True)
class Budget:
    """A hard stop on spend, enforced in this process.

    A proving run that quietly turns into a full corpus run is the expensive
    mistake here, and it is easy to make - one forgotten `--limit`. So the
    ceiling is a property of the client, and exceeding it raises rather than
    warns.
    """

    max_calls: int = 0
    """0 means no ceiling. Set it on anything that is not a proving run."""

    calls: int = 0
    prompt_chars: int = 0
    response_chars: int = 0

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    """`calls += 1` is a read-modify-write, and the whole point of this class is
    to be a hard ceiling. Under concurrent extraction an unlocked counter
    undercounts, which means the one guarantee it offers - that a forgotten
    `--limit` cannot turn into a full corpus run - quietly stops holding."""

    def spend(self, prompt: str, response: str) -> None:
        with self._lock:
            self.calls += 1
            self.prompt_chars += len(prompt)
            self.response_chars += len(response)

    def check(self) -> None:
        with self._lock:
            reached = bool(self.max_calls) and self.calls >= self.max_calls
        if reached:
            raise ExtractionUnavailable(
                f"call budget of {self.max_calls} reached - raise `max_calls` or "
                f"narrow the run"
            )

    def __str__(self) -> str:
        return (f"{self.calls} calls · {self.prompt_chars / 1000:.0f}k prompt chars "
                f"· {self.response_chars / 1000:.0f}k response chars")


@dataclass
class VertexClient:
    """`ModelClient` over Vertex AI.

    Structural typing - it satisfies `extract.ModelClient` without importing it,
    so this module has no dependency on the extractor and the extractor has none
    on Vertex.
    """

    budget: Budget = field(default_factory=Budget)
    max_attempts: int = 4
    base_delay: float = 2.0
    default_model: str = "gemini-2.5-flash"
    max_output_tokens: int = 32768
    """Generous, because the extraction stage is the long one.

    At 8192 a passage yielding four rules truncates mid-quote, and the caller
    sees `JSONDecodeError: Unterminated string` - which reads as a malformed
    model and sends you looking at the prompt. It is not a malformed model, it
    is a ceiling, and `Truncated` below says so.
    """

    _client: Any = field(default=None, repr=False)
    _client_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _vertex(self):
        """Built once, under a lock, because the unlocked version breaks under
        concurrency in a way that reads like a provider outage.

        Two threads both find `_client is None`, both build one, and the second
        assignment wins. The first client now has no reference from `self`, is
        garbage-collected, and closes its transport -- while the thread that
        received it is still mid-request. The symptom is
        `Cannot send a request, as the client has been closed`, raised against
        a perfectly good passage, four retries deep, seven times in sixteen.
        """
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from rishivan.council.client import get_vertex_client

                    self._client = get_vertex_client(
                        helicone_model=self.default_model,
                        helicone_pipeline=PIPELINE_TAG,
                    )
        return self._client

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.0,
        json_schema: Optional[dict] = None,
        model: str = "",
    ) -> str:
        from google.genai import types

        self.budget.check()
        model = model or self.default_model

        config: dict[str, Any] = {
            "system_instruction": system,
            "temperature": temperature,
            # The extractor's whole discipline rests on the model saying "I
            # cannot express this" rather than approximating. A truncated
            # response looks like a malformed one, so the ceiling is generous.
            "max_output_tokens": self.max_output_tokens,
        }
        if json_schema is not None:
            # An empty dict means "JSON, shape unconstrained". The extractor's
            # rule documents are open by design - a rule can carry any of seven
            # consequent blocks - so pinning a response_schema over them would
            # reject valid extractions. Forcing the mime type alone is what
            # actually matters: it is the difference between the provider
            # guaranteeing parseable JSON and the prompt politely asking for it.
            config["response_mime_type"] = "application/json"
            if json_schema:
                config["response_schema"] = json_schema

        last: Optional[Exception] = None
        for attempt in range(self.max_attempts):
            try:
                response = self._vertex().models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config),
                )
                text = (response.text or "").strip()
                self.budget.spend(prompt, text)
                if _truncated(response):
                    # Raised rather than returned, because half a JSON document
                    # is not a smaller answer - it is a different one, and
                    # parsing it produces a rule missing whichever condition
                    # happened to fall past the ceiling.
                    raise Truncated(
                        f"{model} hit the {self.max_output_tokens}-token output "
                        f"ceiling. Raise `max_output_tokens` or narrow the passage."
                    )
                if not text:
                    raise ExtractionUnavailable("empty response")
                return text
            except Truncated:
                raise
            except Exception as exc:  # noqa: BLE001 - classified below
                last = exc
                if not _retryable(exc) or attempt == self.max_attempts - 1:
                    break
                # Jittered, because a batch that retries in lockstep re-creates
                # the burst that caused the rate limit.
                delay = self.base_delay * (2 ** attempt)
                time.sleep(delay + random.uniform(0, delay / 2))

        raise ExtractionUnavailable(
            f"{model} failed after {self.max_attempts} attempts: {last}"
        ) from last


def _retryable(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in RETRYABLE)


@dataclass
class RecordingClient:
    """Wraps a client and writes every exchange to a JSONL file.

    Worth having for a proving run. The roadmap's instruction for the first
    twenty passages is "read every single output yourself", and reading them
    from a file beats scraping them out of a terminal - especially when the
    interesting ones are the disagreements between the two temperatures.
    """

    inner: Any
    path: Any

    def complete(self, **kw: Any) -> str:
        out = self.inner.complete(**kw)
        from pathlib import Path

        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "model": kw.get("model", ""),
                "temperature": kw.get("temperature", 0.0),
                "system": kw.get("system", "")[:400],
                "prompt": kw.get("prompt", ""),
                "response": out,
            }, ensure_ascii=False) + "\n")
        return out
