from __future__ import annotations

from langchain_core.language_models import BaseChatModel

from specflow.config import Settings, get_settings


def build_chat_model(settings: Settings | None = None) -> BaseChatModel | None:
    """Build the configured chat model or return `None` when LLM use is disabled."""

    resolved = settings or get_settings()
    provider = resolved.llm_provider.strip().lower()
    model_name = (resolved.llm_model or "").strip()

    if not model_name:
        return None

    if provider == "openrouter":
        if resolved.openrouter_api_key is None:
            raise ValueError(
                "OPENROUTER_API_KEY is required when SPECFLOW_LLM_PROVIDER=openrouter.",
            )

        from langchain_openrouter import ChatOpenRouter

        return ChatOpenRouter(
            model_name=model_name,
            openrouter_api_key=resolved.openrouter_api_key,
            temperature=resolved.llm_temperature,
            max_retries=2,
            openrouter_api_base=resolved.resolved_llm_base_url,
            app_url=resolved.openrouter_app_url,
            app_title=resolved.openrouter_app_title,
        )

    raise ValueError(f"Unsupported LLM provider: {resolved.llm_provider!r}.")
