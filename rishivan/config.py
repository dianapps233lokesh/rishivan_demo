"""Settings for the standalone demo.

Replaces the main application's pydantic-settings config, which pulls in the
database, Redis, Celery and S3 configuration this demo does not need.

Values are read from Streamlit secrets first (that is how Streamlit Community
Cloud injects them), then from the environment, so the same code runs locally
with a .env file and unchanged in the cloud.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import cached_property


def _secret(name: str, default: str = "") -> str:
    """Streamlit secret, else environment variable, else default."""
    try:  # Streamlit is absent in scripts and tests; fall back quietly.
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 — no secrets file, or not under Streamlit
        pass
    return os.environ.get(name, default)


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

    # ── Derived ──────────────────────────────────────────────────────────────
    @cached_property
    def has_vertex(self) -> bool:
        return bool(self.GCP_PROJECT_ID and self.GCP_PRIVATE_KEY)

    @cached_property
    def has_gemini_key(self) -> bool:
        return bool(self.GEMINI_API_KEY)

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
