"""Settings, resolved from Streamlit secrets, then the environment.

Streamlit Community Cloud injects secrets; local runs and scripts use `.env`.
The same code path serves both.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import cache, cached_property
from pathlib import Path

from sqlalchemy import URL

_PARENT_ENV = Path(__file__).resolve().parents[2] / ".env"
"""The sibling backend's `.env` — same GCP project and Qdrant instance, so its
credentials are valid here. Read-only, never written or echoed."""


@cache
def _parent_env_values() -> dict[str, str]:
    if not _PARENT_ENV.is_file():
        return {}
    values: dict[str, str] = {}
    for line in _PARENT_ENV.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _secret(name: str, default: str = "") -> str:
    """Streamlit secret, else environment, else the sibling `.env`, else default."""
    try:  # Streamlit is absent in scripts and tests; fall back quietly.
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # noqa: BLE001 — no secrets file, or not under Streamlit
        pass
    if name in os.environ:
        return os.environ[name]
    return _parent_env_values().get(name, default)


@dataclass
class Settings:
    """Only what this repo actually reads."""

    DEBUG: bool = False

    # ── Vector store ────────────────────────────────────────────────────────
    @cached_property
    def QDRANT_URL(self) -> str:
        return _secret("QDRANT_URL")

    @cached_property
    def QDRANT_API_KEY(self) -> str:
        return _secret("QDRANT_API_KEY")

    @cached_property
    def VECTOR_COLLECTION(self) -> str:
        return _secret("VECTOR_COLLECTION", "rishivan_docs")

    # ── Google AI ───────────────────────────────────────────────────────────
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

    @cached_property
    def HELICONE_API_KEY(self) -> str:
        """Optional. When set, Vertex traffic routes via the Helicone gateway."""
        return _secret("HELICONE_API_KEY")

    # ── Postgres (the rule base; the answering path does not use it) ─────────
    @cached_property
    def database_url(self) -> str:
        """Async SQLAlchemy URL. `URL.create` percent-encodes the password."""
        return URL.create(
            "postgresql+asyncpg",
            username=_secret("DATABASE_USER", "postgres"),
            password=_secret("DATABASE_PASSWORD", "abc@123"),
            host=_secret("DATABASE_HOST", "localhost"),
            port=int(_secret("DATABASE_PORT", "5432")),
            database=_secret("DATABASE_NAME", "rishivan_dev_local"),
        ).render_as_string(hide_password=False)

    # ── Derived ─────────────────────────────────────────────────────────────
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
