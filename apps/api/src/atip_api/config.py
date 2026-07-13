from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 127.0.0.1 (not localhost): IPv6 loopback isn't forwarded to the containers on Windows
    database_url: str = "postgresql+asyncpg://atip:atip@127.0.0.1:5433/atip"
    redis_url: str = "redis://127.0.0.1:6380/0"
    qdrant_url: str = "http://127.0.0.1:6335"
    qdrant_collection: str = "atip_chunks"
    embedding_dim: int = 1536
    embedding_model: str = "text-embedding-3-small"
    # OpenAI-compatible endpoint; embeddings are skipped (with a warning) if no key is set
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    # chat model for verified RAG; generation is disabled entirely without an API key
    llm_model: str = "gpt-4o-mini"
    # deterministic budgets for downstream calls; retries are handled by tenacity
    openai_timeout_seconds: float = 60.0
    qdrant_timeout_seconds: int = 10
    rrf_k: int = 60
    storage_dir: Path = Path("storage/uploads")
    max_upload_mb: int = 50
    max_pdf_pages: int = 2000
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    log_json: bool = True
    # per-client per-minute limits on resource-heavy endpoints
    rate_limit_enabled: bool = True
    rate_limit_ask_per_minute: int = 30
    rate_limit_extract_per_minute: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
