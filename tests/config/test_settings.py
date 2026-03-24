from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from specflow.config import Settings


def test_settings_default_to_current_working_directory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = Settings(_env_file=None)

    assert settings.runtime_root == tmp_path
    assert settings.workspace_root == tmp_path / "runs"
    assert settings.data_root == tmp_path / ".specflow"
    assert str(tmp_path / ".specflow" / "specflow.db") in settings.resolved_database_url
    assert settings.project_root == Path(__file__).resolve().parents[2]


def test_settings_respect_environment_overrides(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    workspace_root = tmp_path / "workspace"
    data_root = tmp_path / "data"

    monkeypatch.setenv("SPECFLOW_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setenv("SPECFLOW_DATA_ROOT", str(data_root))
    monkeypatch.setenv(
        "SPECFLOW_DATABASE_URL", "postgresql+psycopg://specflow:pass@localhost/specflow"
    )

    settings = Settings(_env_file=None)
    settings.ensure_runtime_directories()

    assert settings.workspace_root == workspace_root
    assert settings.data_root == data_root
    assert settings.resolved_database_url == "postgresql+psycopg://specflow:pass@localhost/specflow"
    assert workspace_root.exists()
    assert data_root.exists()


def test_settings_resolve_relative_environment_paths_from_current_working_directory(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SPECFLOW_WORKSPACE_ROOT", "custom-runs")
    monkeypatch.setenv("SPECFLOW_DATA_ROOT", "custom-data")

    settings = Settings(_env_file=None)
    settings.ensure_runtime_directories()

    assert settings.workspace_root == tmp_path / "custom-runs"
    assert settings.data_root == tmp_path / "custom-data"
    assert (tmp_path / "custom-runs").exists()
    assert (tmp_path / "custom-data").exists()


def test_settings_read_openrouter_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SPECFLOW_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("SPECFLOW_LLM_MODEL", "openai/gpt-4.1-mini")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openrouter"
    assert settings.llm_model == "openai/gpt-4.1-mini"
    assert settings.openrouter_api_key is not None
    assert settings.llm_ready is True
    assert settings.resolved_llm_base_url == "https://openrouter.ai/api/v1"
