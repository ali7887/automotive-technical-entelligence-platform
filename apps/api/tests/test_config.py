"""Release configuration: fail-fast validation and secret hygiene.

Settings are built without an env file and with explicit kwargs so assertions
do not depend on the developer's local .env (conftest env vars are overridden
by constructor kwargs, which have the highest pydantic-settings priority).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from atip_api.ai.embeddings import get_embedding_client
from atip_api.ai.llm import get_llm_client
from atip_api.config import Settings, get_app_version, get_settings
from atip_api.main import create_app


class _EnvFileFreeSettings(Settings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

_PROD_KWARGS = {
    "environment": "production",
    "database_url": "postgresql+asyncpg://svc:s3cret@db.internal:5432/atip",
    "storage_dir": Path("C:/data/uploads") if Path("C:/").exists() else Path("/data/uploads"),
}


def _settings(**overrides) -> Settings:
    return _EnvFileFreeSettings(**overrides)


def test_production_rejects_dev_database_credentials():
    settings = _settings(
        **{**_PROD_KWARGS, "database_url": "postgresql+asyncpg://atip:atip@db:5432/atip"}
    )
    with pytest.raises(RuntimeError, match="dev-default credentials"):
        settings.validate_for_release()


def test_production_rejects_relative_storage_dir():
    settings = _settings(**{**_PROD_KWARGS, "storage_dir": Path("storage/uploads")})
    with pytest.raises(RuntimeError, match="STORAGE_DIR"):
        settings.validate_for_release()


def test_production_accepts_explicit_configuration():
    _settings(**_PROD_KWARGS).validate_for_release()


def test_development_defaults_pass_validation():
    _settings().validate_for_release()


def test_invalid_environment_rejected():
    with pytest.raises(ValidationError):
        _settings(environment="staging")


@pytest.mark.parametrize(
    "field",
    ["rate_limit_ask_per_minute", "rate_limit_extract_per_minute", "max_upload_mb",
     "max_pdf_pages", "qdrant_timeout_seconds", "embedding_dim", "rrf_k"],
)
def test_non_positive_limits_rejected(field):
    with pytest.raises(ValidationError):
        _settings(**{field: 0})


def test_api_key_never_appears_in_repr_or_str():
    settings = _settings(openai_api_key="sk-super-secret-value")
    assert "sk-super-secret-value" not in repr(settings)
    assert "sk-super-secret-value" not in str(settings)
    assert settings.openai_api_key_value == "sk-super-secret-value"


def test_blank_api_key_disables_ai_clients():
    settings = _settings(openai_api_key="")
    assert settings.openai_api_key_value is None
    assert get_llm_client(settings) is None
    assert get_embedding_client(settings) is None


def test_create_app_fails_fast_on_unsafe_production_config(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(
        settings, "database_url", "postgresql+asyncpg://atip:atip@db:5432/atip"
    )
    with pytest.raises(RuntimeError, match="production configuration"):
        create_app()


def test_app_version_is_available():
    version = get_app_version()
    assert isinstance(version, str)
    assert version
