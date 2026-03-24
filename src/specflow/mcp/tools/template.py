from __future__ import annotations

from specflow.mcp.types import ToolContext


def search_templates(
    context: ToolContext,
    *,
    query: str | None = None,
    category: str | None = None,
) -> dict[str, object]:
    matches = context.template_library.search_templates(query, category=category)
    return {"query": query, "category": category, "matches": matches}


def get_template_content(context: ToolContext, *, key: str) -> dict[str, object]:
    asset = context.template_library.get_template(key)
    return {"template": asset.to_metadata(), "content": asset.content}


def list_available_templates(
    context: ToolContext,
    *,
    category: str | None = None,
) -> dict[str, object]:
    if category is None:
        templates = context.template_library.list_templates()
    else:
        templates = context.template_library.search_templates(None, category=category)
    return {"category": category, "templates": templates}
