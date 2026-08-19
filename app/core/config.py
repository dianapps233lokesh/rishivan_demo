"""Application settings loaded from the environment (12-factor)."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Runtime
    ENVIRONMENT: Literal["dev", "stage", "prod"] = "dev"
    DEBUG: bool = False

    # API
    PROJECT_NAME: str = "Rishivan API"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "abc@123"
    DATABASE_NAME: str = "rishivan_dev_local"

    # Redis (cache + Celery broker/backend use separate DB numbers)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    CELERY_BROKER_DB: int = 1
    CELERY_RESULT_DB: int = 2

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # OTP
    OTP_LENGTH: int = 6
    OTP_EXPIRE_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 3
    OTP_RESEND_COOLDOWN_SECONDS: int = 30
    OTP_DEV_BYPASS_CODE: str = "123456"

    # Secret Key (single secret key for all signing/crypto operations)
    SECRET_KEY: SecretStr = SecretStr("change_me_in_production_secret_key")

    # JWT
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Admin Panel
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin"

    # Object storage
    S3_BUCKET: str | None = None
    S3_REGION: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    # Gemini / Vertex AI
    GEMINI_API_KEY: str = ""  # leave blank when using Vertex AI
    GEMINI_FLASH_MODEL: str = "gemini-3.6-flash"
    GEMINI_PRO_MODEL: str = "gemini-3.1-pro-preview"
    # Confirmed against this project's live model list (client.models.list()):
    # "gemini-3.6-pro" was never a real model -- the Pro line stalls at
    # 3.1-pro-preview/2.5-pro while Flash continued to 3.6/3.7. gemini-2.5-pro
    # was also tried and rejected our thinking_budget=0 outright ("model does
    # not support setting thinking_budget to 0"), so it is not a drop-in
    # substitute for this codebase's adapter either -- 3.1-pro-preview is the
    # one confirmed to actually answer with thinking disabled.

    # GCP service-account credentials (sourced from env — no JSON file on server)
    GCP_PROJECT_ID: str = ""
    GCP_LOCATION: str = "us-central1"
    GCP_SERVICE_ACCOUNT_EMAIL: str = ""
    GCP_PRIVATE_KEY: str = ""  # full PEM block with literal \n
    GCP_PRIVATE_KEY_ID: str = ""

    # Document AI — the OCR prior for the knowledge pipeline.
    # Full resource name: projects/{p}/locations/{l}/processors/{id}
    DOCAI_PROCESSOR_NAME: str = ""

    # S3 (S3_BUCKET / S3_REGION / AWS_* already defined above)
    S3_PREFIX: str = "rishivan"
    S3_ENDPOINT_URL: str | None = None

    # Ingestion
    RENDER_DPI: int = 200
    INGEST_CONCURRENCY: int = 4

    # Vector store (RAG). Backend switches the storage/query layer only —
    # embeddings are computed by Vertex regardless of backend.
    VECTOR_BACKEND: Literal["chroma", "qdrant"] = "qdrant"
    VECTOR_COLLECTION: str = "rishivan_docs"
    CHROMA_PATH: str = ".chroma_db"
    QDRANT_URL: str = ""  # e.g. https://<id>.<region>.cloud.qdrant.io:6333
    QDRANT_API_KEY: str = ""

    # Retrieval (P3) — the knowledge-pipeline passage collection, distinct from
    # the legacy VECTOR_COLLECTION above.
    QDRANT_COLLECTION: str = "rishivan_passages"
    RETRIEVAL_TOP_K: int = 12
    RRF_PREFETCH_LIMIT: int = 60

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL (URL.create percent-encodes credentials)."""
        return URL.create(
            "postgresql+asyncpg",
            username=self.DATABASE_USER,
            password=self.DATABASE_PASSWORD,
            host=self.DATABASE_HOST,
            port=self.DATABASE_PORT,
            database=self.DATABASE_NAME,
        ).render_as_string(hide_password=False)

    def _redis_url(self, db: int) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{db}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        """Redis URL for the shared application cache."""
        return self._redis_url(self.REDIS_DB)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_broker_url(self) -> str:
        """Redis URL used as the Celery message broker."""
        return self._redis_url(self.CELERY_BROKER_DB)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_result_backend(self) -> str:
        """Redis URL used to store Celery task results."""
        return self._redis_url(self.CELERY_RESULT_DB)


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so the environment is parsed only once."""
    return Settings()


settings = get_settings()
