from __future__ import annotations

from pathlib import Path

import pytest

from specflow.config import Settings
from specflow.llm import build_chat_model


def test_build_chat_model_returns_none_without_model() -> None:
    settings = Settings(_env_file=None)

    assert build_chat_model(settings) is None


def test_build_chat_model_requires_openrouter_key(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path / "runs",
        data_root=tmp_path / ".specflow",
        llm_provider="openrouter",
        llm_model="openai/gpt-4.1-mini",
    )

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        build_chat_model(settings)


def test_build_chat_model_uses_openrouter_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    settings = Settings(
        _env_file=None,
        llm_provider="openrouter",
        llm_model="openai/gpt-4.1-mini",
    )
    model = build_chat_model(settings)

    assert model is not None
    assert model.__class__.__name__ == "ChatOpenRouter"
