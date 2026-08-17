"""POC AI client factory — supports both Vertex AI and Gemini API key.

Key differences:
  - Vertex AI    : aiplatform.googleapis.com — uses text-embedding-004 for embeds
  - Gemini API   : generativelanguage.googleapis.com
                   Generation → v1 (gemini-2.0-flash)
                   Embedding  → v1beta (gemini-embedding-exp-03-07, dim=768)
                   text-embedding-004 is ONLY available on Vertex AI.
"""
from __future__ import annotations

from google import genai
from google.genai import types as genai_types


def get_gemini_api_client(api_key: str | None = None) -> genai.Client:
    """Build a Gemini API client (api_version=v1beta covers both gen + embed)."""
    from rishivan.config import settings

    key = api_key or settings.GEMINI_API_KEY
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to "
            ".streamlit/secrets.toml (or the environment)."
        )
    # v1beta exposes both gemini-2.0-flash and gemini-embedding-exp-03-07
    return genai.Client(
        api_key=key,
        http_options=genai_types.HttpOptions(api_version="v1beta"),
    )


def get_vertex_client() -> genai.Client:
    """Build a Vertex AI client from service-account settings."""
    from google.oauth2 import service_account
    from rishivan.config import settings

    credentials = service_account.Credentials.from_service_account_info(
        {
            "type": "service_account",
            "project_id": settings.GCP_PROJECT_ID,
            "private_key_id": settings.GCP_PRIVATE_KEY_ID,
            "private_key": settings.GCP_PRIVATE_KEY,
            "client_email": settings.GCP_SERVICE_ACCOUNT_EMAIL,
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return genai.Client(
        vertexai=True,
        project=settings.GCP_PROJECT_ID,
        location=settings.GCP_LOCATION,
        credentials=credentials,
    )


# ── Model registry ────────────────────────────────────────────────────────────
# NOTE: text-embedding-004 is Vertex-only.
# Gemini API uses gemini-embedding-exp-03-07 with output_dimensionality=768
# to match the existing Qdrant collection (built from Vertex text-embedding-004).

GEMINI_MODELS = {
    "flash": "gemini-2.0-flash",
    "pro":   "gemini-2.0-flash",
    "embed": "gemini-embedding-exp-03-07",   # only model available via API key
}

VERTEX_MODELS = {
    "flash": "gemini-3.7-flash",
    "pro":   "gemini-3.7-flash",
    "embed": "text-embedding-004",           # Vertex AI embedding model
}

# Qdrant collection was built with text-embedding-004 → 768 dimensions.
# Force same output dimension when using Gemini API embed model.
GEMINI_EMBED_DIM = 768


def model_name(backend: str, tier: str = "flash") -> str:
    """Return the correct model string for the given backend and tier."""
    if backend == "gemini":
        return GEMINI_MODELS.get(tier, GEMINI_MODELS["flash"])
    return VERTEX_MODELS.get(tier, VERTEX_MODELS["flash"])
