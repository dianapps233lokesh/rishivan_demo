"""Vertex AI client factory.

Vertex only, and not merely by preference: the Qdrant collections were embedded with
`text-embedding-004`, which is Vertex-exclusive. An API-key client cannot produce a
comparable vector, so a second backend could only ever have degraded retrieval.
"""
from __future__ import annotations

from google import genai


def _helicone_http_options(model: str, pipeline: str) -> dict | None:
    """Route Vertex traffic through the Helicone gateway when a key is configured.

        Returns None without a key, so leaving Helicone unconfigured is always safe.

        One gotcha worth keeping: with `vertexai=True` the genai SDK builds paths as
        `/v1beta1/projects/{p}/locations/global/...`, and a regional endpoint returns 404
        for a `locations/global` path — so the target must be the global endpoint.
    """
    from rishivan.config import settings

    if not settings.has_helicone:
        return None
    return {
        "base_url": "https://gateway.helicone.ai",
        "headers": {
            "helicone-auth": f"Bearer {settings.HELICONE_API_KEY}",
            "helicone-target-url": "https://aiplatform.googleapis.com",
            "helicone-property-model": model,
            "helicone-property-pipeline": pipeline,
        },
    }


def get_vertex_client(
    *, helicone_model: str | None = None, helicone_pipeline: str | None = None
) -> genai.Client:
    """Build a Vertex AI client from service-account settings.

    Pass `helicone_pipeline` to tag this client's traffic in the Helicone dashboard --
    the Koonji extractor uses `koonji-extract`, so its spend is separable from the
    demo's chat traffic.
    """
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
    http_options = (
        _helicone_http_options(helicone_model or "unspecified", helicone_pipeline)
        if helicone_pipeline
        else None
    )
    return genai.Client(
        vertexai=True,
        project=settings.GCP_PROJECT_ID,
        location=settings.GCP_LOCATION,
        credentials=credentials,
        http_options=http_options,
    )


MODELS = {
    "flash": "gemini-3.7-flash",
    "pro":   "gemini-3.1-pro-preview",
    "embed": "text-embedding-004",
}
"""Tier -> model.

`pro` and `flash` were the same string until the two-call direct lane needed
them not to be. They now name genuinely different models, and the split is the
lane's entire premise: `council/analyse.py` works out what the chart carries on
`pro`, `council/narrate_verdict.py` says it warmly on `flash`. Point them at one
model again and the second call becomes a round trip that buys nothing.

`embed` must stay `text-embedding-004`: it is what the Qdrant collections were
built with, and a different embedder makes every stored vector incomparable
without re-embedding the corpus."""


def model_name(tier: str = "flash") -> str:
    """The model string for a tier, falling back to flash."""
    return MODELS.get(tier, MODELS["flash"])
