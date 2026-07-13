import importlib.metadata
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_app_version() -> str:
    try:
        return importlib.metadata.version("atip-api")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # deployment stage; "production" turns on fail-fast configuration checks
    environment: Literal["development", "test", "production"] = "development"
    # release identifier stamped into /health/live (set by the deploy pipeline)
    build_sha: str | None = None

    # 127.0.0.1 (not localhost): IPv6 loopback isn't forwarded to the containers on Windows
    database_url: str = "postgresql+asyncpg://atip:atip@127.0.0.1:5433/atip"
    redis_url: str = "redis://127.0.0.1:6380/0"
    qdrant_url: str = "http://127.0.0.1:6335"
    qdrant_collection: str = "atip_chunks"
    embedding_dim: int = Field(default=1536, ge=1)
    embedding_model: str = "text-embedding-3-small"
    # OpenAI-compatible endpoint; embeddings are skipped (with a warning) if no key is set
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    # chat model for verified RAG; generation is disabled entirely without an API key
    llm_model: str = "gpt-4o-mini"
    # deterministic budgets for downstream calls; retries are handled by tenacity
    openai_timeout_seconds: float = Field(default=60.0, gt=0)
    qdrant_timeout_seconds: int = Field(default=10, ge=1)
    rrf_k: int = Field(default=60, ge=1)
    # optional cross-encoder reranking of fused candidates (Cohere/Jina/TEI-style
    # HTTP API); any failure falls back to plain RRF ordering, never an error
    rerank_enabled: bool = False
    rerank_url: str | None = None
    rerank_model: str | None = None
    rerank_api_key: SecretStr | None = None
    rerank_timeout_seconds: float = Field(default=10.0, gt=0)
    rerank_candidates: int = Field(default=30, ge=1, le=100)
    storage_dir: Path = Path("storage/uploads")
    max_upload_mb: int = Field(default=50, ge=1)
    max_pdf_pages: int = Field(default=2000, ge=1)
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    log_json: bool = True
    # per-client per-minute limits on resource-heavy endpoints
    rate_limit_enabled: bool = True
    rate_limit_ask_per_minute: int = Field(default=30, ge=1)
    rate_limit_extract_per_minute: int = Field(default=10, ge=1)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def openai_api_key_value(self) -> str | None:
        """The API key as a plain string, or None when unset or blank."""
        if self.openai_api_key is None:
            return None
        return self.openai_api_key.get_secret_value() or None

    @property
    def rerank_api_key_value(self) -> str | None:
        if self.rerank_api_key is None:
            return None
        return self.rerank_api_key.get_secret_value() or None

    def validate_for_release(self) -> None:
        """Fail fast on configuration that is unambiguously wrong in production.

        Only checks with zero false positives belong here — anything softer is a
        startup log warning in create_app(), not a boot failure.
        """
        if self.environment != "production":
            return
        problems: list[str] = []
        if "atip:atip@" in self.database_url:
            problems.append("DATABASE_URL still uses the dev-default credentials")
        if not self.storage_dir.is_absolute():
            problems.append(
                "STORAGE_DIR must be an absolute path in production "
                "(a relative path depends on the process working directory)"
            )
        if problems:
            raise RuntimeError(
                "Refusing to start with unsafe production configuration: "
                + "; ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
