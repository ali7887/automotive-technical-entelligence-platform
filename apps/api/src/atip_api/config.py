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
    storage_dir: Path = Path("storage/uploads")
    max_upload_mb: int = 50
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
