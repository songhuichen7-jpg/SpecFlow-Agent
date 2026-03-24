from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, PrivateAttr, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_runtime_path(value: Path, runtime_root: Path) -> Path:
    if value.is_absolute():
        return value.resolve()
    return (runtime_root / value).resolve()


class Settings(BaseSettings):
    """Application settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SPECFLOW_",
        extra="ignore",
        validate_default=True,
    )

    app_name: str = "SpecFlow-Agent"
    environment: str = "development"
    debug: bool = False
    llm_provider: str = "openai"
    llm_model: str | None = None
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_base_url: str | None = None
    openrouter_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENROUTER_API_KEY", "SPECFLOW_OPENROUTER_API_KEY"),
    )
    openrouter_app_url: str | None = Field(
        default="https://localhost/specflow-agent",
        validation_alias=AliasChoices("OPENROUTER_APP_URL", "SPECFLOW_OPENROUTER_APP_URL"),
    )
    openrouter_app_title: str | None = Field(
        default="SpecFlow-Agent",
        validation_alias=AliasChoices("OPENROUTER_APP_TITLE", "SPECFLOW_OPENROUTER_APP_TITLE"),
    )
    database_url: str | None = None
    workspace_root: Path = Field(default=Path("runs"))
    data_root: Path = Field(default=Path(".specflow"))
    checkpoint_backend: Literal["memory", "sqlite", "postgres"] = "sqlite"
    checkpoint_path: Path = Field(default=Path("langgraph/checkpoints.sqlite"))
    checkpoint_url: str | None = None
    store_backend: Literal["memory", "sqlite", "postgres"] = "sqlite"
    store_path: Path = Field(default=Path("langgraph/store.sqlite"))
    store_url: str | None = None
    persistent_memory_route: str = "/memories/"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    _runtime_root: Path = PrivateAttr(default_factory=lambda: Path.cwd().resolve())

    @model_validator(mode="after")
    def normalize_paths(self) -> Self:
        self._runtime_root = Path.cwd().resolve()
        self.workspace_root = _resolve_runtime_path(self.workspace_root, self._runtime_root)
        self.data_root = _resolve_runtime_path(self.data_root, self._runtime_root)
        self.checkpoint_path = self._resolve_data_path(self.checkpoint_path)
        self.store_path = self._resolve_data_path(self.store_path)
        return self

    def _resolve_data_path(self, value: Path) -> Path:
        if value.is_absolute():
            return value.resolve()
        return (self.data_root / value).resolve()

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def runtime_root(self) -> Path:
        return self._runtime_root

    @property
    def resolved_llm_base_url(self) -> str | None:
        if self.llm_base_url:
            return self.llm_base_url
        if self.llm_provider.strip().lower() == "openrouter":
            return "https://openrouter.ai/api/v1"
        return None

    @property
    def llm_ready(self) -> bool:
        provider = self.llm_provider.strip().lower()
        if not self.llm_model:
            return False
        if provider == "openrouter":
            return self.openrouter_api_key is not None
        return False

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        database_path = self.data_root / "specflow.db"
        return f"sqlite+pysqlite:///{database_path}"

    def ensure_runtime_directories(self) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
