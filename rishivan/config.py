"""Settings for the standalone demo.

Replaces the main application's pydantic-settings config, which pulls in the
database, Redis, Celery and S3 configuration this demo does not need.

Values are read from Streamlit secrets first (that is how Streamlit Community
Cloud injects them), then from the environment, so the same code runs locally
with a .env file and unchanged in the cloud.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import cache, cached_property
from pathlib import Path

_MAIN_REPO_ENV = Path(__file__).resolve().parents[2] / ".env"
"""The main backend's own .env, one directory up from this demo — same
Google Cloud project and Qdrant instance, so its Vertex/Qdrant credentials
are valid here too. Read-only, in-process; never written or echoed."""


@cache
def _main_repo_env_values() -> dict[str, str]:
    if not _MAIN_REPO_ENV.is_file():
        return {}
    values: dict[str, str] = {}
    for line in _MAIN_REPO_ENV.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _secret(name: str, default: str = "") -> str:
    """Streamlit secret, else environment variable, else the main repo's own
    .env (demo-local convenience only), else default."""
    try:  # Streamlit is absent in scripts and tests; fall back quietly.
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 — no secrets file, or not under Streamlit
        pass
    if name in os.environ:
        return os.environ[name]
    return _main_repo_env_values().get(name, default)


@dataclass
class Settings:
    """Only what the Council pipeline actually touches."""

    # ── Vector store ─────────────────────────────────────────────────────────
    # Qdrant only: Chroma needs local files, which a cloud container loses on
    # every restart.
    VECTOR_BACKEND: str = "qdrant"
    CHROMA_PATH: str = ".chroma"          # unused in the cloud, kept for the
    #                                       shared VectorStore interface

    @cached_property
    def QDRANT_URL(self) -> str:
        return _secret("QDRANT_URL")

    @cached_property
    def QDRANT_API_KEY(self) -> str:
        return _secret("QDRANT_API_KEY")

    @cached_property
    def VECTOR_COLLECTION(self) -> str:
        return _secret("VECTOR_COLLECTION", "rishivan_docs")

    # ── Google AI ────────────────────────────────────────────────────────────
    @cached_property
    def GEMINI_API_KEY(self) -> str:
        return _secret("GEMINI_API_KEY")

    @cached_property
    def GCP_PROJECT_ID(self) -> str:
        return _secret("GCP_PROJECT_ID")

    @cached_property
    def GCP_LOCATION(self) -> str:
        return _secret("GCP_LOCATION", "global")

    @cached_property
    def GCP_SERVICE_ACCOUNT_EMAIL(self) -> str:
        return _secret("GCP_SERVICE_ACCOUNT_EMAIL")

    @cached_property
    def GCP_PRIVATE_KEY_ID(self) -> str:
        return _secret("GCP_PRIVATE_KEY_ID")

    @cached_property
    def GCP_PRIVATE_KEY(self) -> str:
        # TOML and .env both escape newlines; the PEM parser needs them real.
        return _secret("GCP_PRIVATE_KEY").replace("\\n", "\n")

    # ── Observability ────────────────────────────────────────────────────────
    @cached_property
    def HELICONE_API_KEY(self) -> str:
        """Optional. When set, Vertex traffic routes through the Helicone gateway."""
        return _secret("HELICONE_API_KEY")

    # ── Derived ──────────────────────────────────────────────────────────────
    @cached_property
    def has_vertex(self) -> bool:
        return bool(self.GCP_PROJECT_ID and self.GCP_PRIVATE_KEY)

    @cached_property
    def has_gemini_key(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @cached_property
    def has_helicone(self) -> bool:
        return bool(self.HELICONE_API_KEY)

    @cached_property
    def default_backend(self) -> str:
        """Prefer a Gemini API key when present — no service account needed."""
        return "gemini" if self.has_gemini_key else "vertex"

    def missing(self) -> list[str]:
        """Config the app cannot start without, for a clear error on screen."""
        gaps: list[str] = []
        if not self.QDRANT_URL:
            gaps.append("QDRANT_URL")
        if not (self.has_gemini_key or self.has_vertex):
            gaps.append("GEMINI_API_KEY (or the five GCP_* Vertex values)")
        return gaps


settings = Settings()
