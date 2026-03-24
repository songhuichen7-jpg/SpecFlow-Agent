from __future__ import annotations

import subprocess

from specflow.mcp.sandbox import WorkspaceSandbox
from specflow.mcp.types import ToolContext
from specflow.templates import DEFAULT_TEMPLATE_SLUG


def create_project_skeleton(
    context: ToolContext,
    *,
    template_slug: str = DEFAULT_TEMPLATE_SLUG,
    overwrite: bool = False,
) -> dict[str, object]:
    scaffold = context.template_library.get_project_scaffold(template_slug)
    sandbox = WorkspaceSandbox(
        context.run_id,
        settings=context.settings,
        artifact_repository=context.artifact_repository,
    )

    created_files: list[str] = []
    skipped_files: list[str] = []
    for relative_path, content in scaffold.items():
        target = sandbox.resolve(relative_path)
        if target.exists() and not overwrite:
            skipped_files.append(relative_path)
            continue
        sandbox.write_file(relative_path, content, overwrite=True)
        created_files.append(relative_path)

    return {
        "template_slug": template_slug,
        "workspace_root": str(sandbox.root),
        "created_files": created_files,
        "skipped_files": skipped_files,
    }


def init_git_repo(
    context: ToolContext,
    *,
    initial_branch: str = "main",
    write_gitignore: bool = True,
) -> dict[str, object]:
    sandbox = WorkspaceSandbox(
        context.run_id,
        settings=context.settings,
        artifact_repository=context.artifact_repository,
    )
    if write_gitignore and not sandbox.resolve(".gitignore").exists():
        sandbox.write_file(
            ".gitignore",
            "node_modules/\ndist/\n.pytest_cache/\n__pycache__/\n*.pyc\n",
            overwrite=False,
        )

    command = ["git", "init", "-b", initial_branch]
    try:
        completed = subprocess.run(
            command,
            cwd=sandbox.root,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        completed = subprocess.run(
            ["git", "init"],
            cwd=sandbox.root,
            capture_output=True,
            text=True,
            check=True,
        )

    return {
        "workspace_root": str(sandbox.root),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
