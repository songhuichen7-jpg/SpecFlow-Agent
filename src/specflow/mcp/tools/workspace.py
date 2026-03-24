from __future__ import annotations

from specflow.mcp.sandbox import WorkspaceSandbox
from specflow.mcp.types import ToolContext


def read_file(context: ToolContext, *, path: str) -> dict[str, str]:
    sandbox = WorkspaceSandbox(
        context.run_id,
        settings=context.settings,
        artifact_repository=context.artifact_repository,
    )
    return {"path": path, "content": sandbox.read_file(path)}


def write_file(
    context: ToolContext,
    *,
    path: str,
    content: str,
    overwrite: bool = True,
) -> dict[str, str]:
    sandbox = WorkspaceSandbox(
        context.run_id,
        settings=context.settings,
        artifact_repository=context.artifact_repository,
    )
    written = sandbox.write_file(path, content, overwrite=overwrite)
    return {"path": written.relative_to(sandbox.root).as_posix(), "status": "written"}


def list_directory(context: ToolContext, *, path: str = ".") -> dict[str, object]:
    sandbox = WorkspaceSandbox(
        context.run_id,
        settings=context.settings,
        artifact_repository=context.artifact_repository,
    )
    entries = sandbox.list_directory(path)
    return {
        "path": path,
        "entries": [
            {"path": entry.path, "is_dir": entry.is_dir, "size": entry.size} for entry in entries
        ],
    }


def delete_file(
    context: ToolContext,
    *,
    path: str,
    recursive: bool = False,
) -> dict[str, str]:
    sandbox = WorkspaceSandbox(
        context.run_id,
        settings=context.settings,
        artifact_repository=context.artifact_repository,
    )
    sandbox.delete_path(path, recursive=recursive)
    return {"path": path, "status": "deleted"}
