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


_MONGO_URI = re.compile(r"^(mongodb(?:\+srv)?://)([^:@/]+):([^@]*)@(.+)$")


def _encode_mongo_userinfo(uri: str) -> str:
    """Percent-encode the username and password inside a Mongo URI.

    Idempotent: a URI whose credentials are already encoded is returned
    unchanged, because encoding an encoded string doubles the escapes and
    produces a password that authenticates against nothing.
    """
    from urllib.parse import quote_plus, unquote_plus

    match = _MONGO_URI.match(uri.strip())
    if not match:
        # No inline credentials, or a shape we do not recognise. Hand it to
        # the driver as given rather than mangling it.
        return uri.strip()
    scheme, user, password, rest = match.groups()
    return (
        f"{scheme}{quote_plus(unquote_plus(user))}:"
        f"{quote_plus(unquote_plus(password))}@{rest}"
    )


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

    # ── MongoDB (telemetry: traces and the prediction ledger) ───────────────
    @cached_property
    def MONGODB_URI(self) -> str:
        """The connection string, with its credentials percent-encoded.

        Atlas hands you a URI with the password inline, and pymongo refuses it
        outright if the password contains a reserved character - the real one
        here holds a `%` and raised `InvalidURI: Username and password must be
        escaped according to RFC 3986`. Encoding it here rather than asking
        whoever pastes the secret to remember: the same reasoning as
        `database_url`, which uses `URL.create` for exactly this.

        An already-encoded URI passes through unchanged, because `quote_plus`
        of an encoded string would double-encode it - so the check is whether
        decoding changes anything.
        """
        raw = _secret("MONGODB_URI")
        if not raw:
            return ""
        return _encode_mongo_userinfo(raw)

    @cached_property
    def MONGODB_DB_NAME(self) -> str:
        return _secret("MONGODB_DB_NAME", "rishivan_telemetry")

    @cached_property
    def MONGODB_COLLECTION_NAME(self) -> str:
        """The turn-level telemetry collection - one document per answer."""
        return _secret("MONGODB_COLLECTION_NAME", "client_testing")

    @cached_property
    def MONGODB_PREDICTIONS_COLLECTION(self) -> str:
        """The prediction ledger.

        Derived from the turn collection rather than configured separately, so
        a second test round only needs the one name changed and its ledger
        follows it. Override explicitly if the two must diverge.
        """
        return _secret(
            "MONGODB_PREDICTIONS_COLLECTION",
            f"{self.MONGODB_COLLECTION_NAME}_predictions",
        )

    @cached_property
    def MONGODB_REQUIREMENTS_COLLECTION(self) -> str:
        """What each question kind requires.

        NOT derived from `MONGODB_COLLECTION_NAME` the way the prediction ledger
        is, and the difference is deliberate: a second client-test round wants a
        fresh telemetry collection and the SAME requirements. Deriving it would
        silently empty the table every time somebody renamed the test round, and
        an empty requirements table is a reading built from nothing.
        """
        return _secret("MONGODB_REQUIREMENTS_COLLECTION", "question_requirements")

    @cached_property
    def MONGODB_RETENTION_DAYS(self) -> int:
        """TTL on telemetry documents. Zero disables expiry.

        The Atlas free tier is 512 MB and there is no alarm before it fills -
        writes simply start failing. A TTL index means the cap is reached by
        age rather than by surprise.
        """
        return int(_secret("MONGODB_RETENTION_DAYS", "90"))

    # ── Derived ─────────────────────────────────────────────────────────────
    @cached_property
    def has_vertex(self) -> bool:
        return bool(self.GCP_PROJECT_ID and self.GCP_PRIVATE_KEY)

    @cached_property
    def has_helicone(self) -> bool:
        return bool(self.HELICONE_API_KEY)

    @cached_property
    def has_mongo(self) -> bool:
        return bool(self.MONGODB_URI)

    def missing(self) -> list[str]:
        """Config the app cannot start without, for a clear error on screen."""
        gaps: list[str] = []
        if not self.QDRANT_URL:
            gaps.append("QDRANT_URL")
        if not self.has_vertex:
            gaps.append("the five GCP_* Vertex values")
        return gaps


settings = Settings()
