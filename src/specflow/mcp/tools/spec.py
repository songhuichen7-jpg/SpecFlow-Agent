from __future__ import annotations

from specflow.mcp.types import ToolContext

DEFAULT_REQUIRED_SPEC_ITEMS = (
    "spec.md",
    "plan.md",
    "tasks.md",
    "data-model.md",
    "research.md",
)


def read_spec(context: ToolContext, *, artifact_name: str = "spec.md") -> dict[str, object]:
    artifact = context.artifact_repository.load_artifact(context.run_id, name=artifact_name)
    return {
        "artifact_name": artifact_name,
        "content": artifact.content,
        "version": artifact.version,
        "path": artifact.path,
    }


def export_spec_summary(
    context: ToolContext,
    *,
    artifact_names: list[str] | None = None,
) -> dict[str, object]:
    requested = artifact_names or list(DEFAULT_REQUIRED_SPEC_ITEMS)
    documents: list[dict[str, object]] = []
    missing: list[str] = []

    for name in requested:
        try:
            artifact = context.artifact_repository.load_artifact(context.run_id, name=name)
        except LookupError:
            missing.append(name)
            continue
        documents.append(
            {
                "artifact_name": name,
                "version": artifact.version,
                "headings": _extract_headings(artifact.content),
                "preview": _extract_preview(artifact.content),
            }
        )

    return {"documents": documents, "missing": missing}


def validate_spec_completeness(
    context: ToolContext,
    *,
    required_artifacts: list[str] | None = None,
    require_contracts: bool = False,
) -> dict[str, object]:
    required = required_artifacts or list(DEFAULT_REQUIRED_SPEC_ITEMS)
    artifacts = context.artifact_repository.list_artifacts(context.run_id)
    present = {artifact.name for artifact in artifacts}
    missing = [name for name in required if name not in present]

    has_contracts = any(name.startswith("contracts/") for name in present)
    if require_contracts and not has_contracts:
        missing.append("contracts/")

    total_expected = len(required) + (1 if require_contracts else 0)
    completeness = 0.0 if total_expected == 0 else (total_expected - len(missing)) / total_expected

    return {
        "is_complete": not missing,
        "missing_items": missing,
        "present_items": sorted(present),
        "completeness_score": round(completeness, 2),
    }


def _extract_headings(content: str) -> list[str]:
    return [line.lstrip("# ").strip() for line in content.splitlines() if line.startswith("#")]


def _extract_preview(content: str, limit: int = 180) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:limit]
    return ""
