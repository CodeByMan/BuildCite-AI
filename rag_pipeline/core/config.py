from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from rag_pipeline.core.errors import ConfigError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_mode: Literal["local", "hosted"] = Field(default="local", alias="APP_MODE")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )

    host: str = Field(default="127.0.0.1", alias="HOST", min_length=1)
    port: int = Field(default=8000, alias="PORT", ge=1, le=65535)
    cors_origins: str = Field(
        default="http://localhost:8501,http://127.0.0.1:8501", alias="CORS_ORIGINS"
    )
    allowed_hosts: str = Field(
        default="localhost,127.0.0.1,testserver,api", alias="ALLOWED_HOSTS"
    )

    storage_dir: Path = Field(default=Path("./data"), alias="STORAGE_DIR")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/app.db", alias="DATABASE_URL", min_length=1
    )

    max_upload_bytes: int = Field(default=25 * 1024 * 1024, alias="MAX_UPLOAD_BYTES", ge=1024)
    upload_chunk_bytes: int = Field(default=1024 * 1024, alias="UPLOAD_CHUNK_BYTES", ge=1024)
    max_pdf_pages: int = Field(default=500, alias="MAX_PDF_PAGES", ge=1, le=10_000)

    ocr_mode: Literal["auto", "text_only", "google_vision"] = Field(
        default="auto", alias="OCR_MODE"
    )
    google_application_credentials: Path | None = Field(
        default=None, alias="GOOGLE_APPLICATION_CREDENTIALS"
    )

    embedding_model: str = Field(
        default="text-embedding-3-small", alias="EMBEDDING_MODEL", min_length=1
    )
    rerank_mode: Literal["off", "bm25"] = Field(default="bm25", alias="RERANK_MODE")
    top_k_default: int = Field(default=6, alias="TOP_K_DEFAULT", ge=1, le=30)
    rerank_top_n: int = Field(default=20, alias="RERANK_TOP_N", ge=1, le=100)

    llm_provider: Literal["anthropic", "openai"] = Field(
        default="anthropic", alias="LLM_PROVIDER"
    )
    llm_model: str | None = Field(default=None, alias="LLM_MODEL")
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")

    demo_access_key: SecretStr | None = Field(default=None, alias="DEMO_ACCESS_KEY")
    admin_api_key: SecretStr | None = Field(default=None, alias="ADMIN_API_KEY")

    max_concurrent_ingestions: int = Field(
        default=2, alias="MAX_CONCURRENT_INGESTIONS", ge=1, le=8
    )

    @model_validator(mode="after")
    def validate_deployment(self) -> "Settings":
        if self.storage_dir.expanduser().resolve() == Path("/"):
            raise ValueError("STORAGE_DIR cannot be the filesystem root.")
        if not self.database_url.startswith("sqlite+aiosqlite:///"):
            raise ValueError("This local prototype supports only sqlite+aiosqlite DATABASE_URL values.")
        if self.upload_chunk_bytes > self.max_upload_bytes:
            raise ValueError("UPLOAD_CHUNK_BYTES cannot exceed MAX_UPLOAD_BYTES.")
        if self.rerank_top_n < self.top_k_default:
            raise ValueError("RERANK_TOP_N must be greater than or equal to TOP_K_DEFAULT.")
        if "*" in self.parsed_cors_origins():
            raise ValueError("Wildcard CORS origins are not allowed with credentialed requests.")
        if not self.parsed_allowed_hosts():
            raise ValueError("ALLOWED_HOSTS must contain at least one host.")
        if self.ocr_mode == "google_vision" and self.google_application_credentials is None:
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS is required when OCR_MODE=google_vision."
            )
        if self.app_mode == "hosted":
            demo_key = self.demo_access_key.get_secret_value() if self.demo_access_key else ""
            admin_key = self.admin_api_key.get_secret_value() if self.admin_api_key else ""
            if len(demo_key) < 16:
                raise ValueError("Hosted mode requires DEMO_ACCESS_KEY with at least 16 characters.")
            if len(admin_key) < 16:
                raise ValueError("Hosted mode requires ADMIN_API_KEY with at least 16 characters.")
            if demo_key == admin_key:
                raise ValueError("DEMO_ACCESS_KEY and ADMIN_API_KEY must be different.")
        return self

    def parsed_cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    def parsed_allowed_hosts(self) -> list[str]:
        return [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]

    def validate_embedding_config(self) -> None:
        key = self.openai_api_key.get_secret_value() if self.openai_api_key else ""
        if not key:
            raise ConfigError("Embedding provider is not configured.")
        if not self.embedding_model.strip():
            raise ConfigError("Embedding model is not configured.")

    def validate_llm_config(self) -> None:
        model = (self.llm_model or "").strip()
        if not model:
            raise ConfigError("Language model is not configured.")
        if self.llm_provider == "anthropic":
            key = self.anthropic_api_key.get_secret_value() if self.anthropic_api_key else ""
        else:
            key = self.openai_api_key.get_secret_value() if self.openai_api_key else ""
        if not key:
            raise ConfigError("Language model provider is not configured.")


@lru_cache
def get_settings() -> Settings:
    load_dotenv(override=False)
    return Settings()
