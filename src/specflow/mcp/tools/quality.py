from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from specflow.mcp.sandbox import WorkspaceSandbox
from specflow.mcp.types import ToolContext


def run_lint(
    context: ToolContext,
    *,
    path: str = ".",
    command: list[str] | None = None,
) -> dict[str, object]:
    return _run_quality_command(context, path=path, command=command, default="lint")


def run_tests(
    context: ToolContext,
    *,
    path: str = ".",
    command: list[str] | None = None,
) -> dict[str, object]:
    return _run_quality_command(context, path=path, command=command, default="test")


def run_build(
    context: ToolContext,
    *,
    path: str = ".",
    command: list[str] | None = None,
) -> dict[str, object]:
    return _run_quality_command(context, path=path, command=command, default="build")


def check_types(
    context: ToolContext,
    *,
    path: str = ".",
    command: list[str] | None = None,
) -> dict[str, object]:
    return _run_quality_command(context, path=path, command=command, default="typecheck")


def _run_quality_command(
    context: ToolContext,
    *,
    path: str,
    command: list[str] | None,
    default: str,
) -> dict[str, object]:
    sandbox = WorkspaceSandbox(
        context.run_id,
        settings=context.settings,
        artifact_repository=context.artifact_repository,
    )
    working_directory = sandbox.resolve(path)
    if not working_directory.is_dir():
        raise NotADirectoryError(path)

    resolved_command = command or _detect_default_command(working_directory, default)
    completed = subprocess.run(
        resolved_command,
        cwd=working_directory,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "path": path,
        "command": resolved_command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "success": completed.returncode == 0,
    }


def _detect_default_command(working_directory: Path, default: str) -> list[str]:
    package_json = working_directory / "package.json"
    if package_json.exists():
        package = json.loads(package_json.read_text(encoding="utf-8"))
        scripts = package.get("scripts", {})
        aliases = {
            "lint": ("lint",),
            "test": ("test",),
            "build": ("build",),
            "typecheck": ("typecheck", "check-types"),
        }[default]
        for alias in aliases:
            if alias in scripts:
                return ["npm", "run", alias]

    if default == "lint":
        return ["ruff", "check", "."]
    if default == "test":
        return ["pytest"]
    if default == "build":
        return [sys.executable, "-m", "compileall", "."]
    return ["mypy", "."]
