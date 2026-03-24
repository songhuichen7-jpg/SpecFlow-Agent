from __future__ import annotations

import sys
from typing import Any

from specflow.mcp import build_default_mcp_server


def test_scaffold_and_quality_tools(sprint2_env: dict[str, Any]) -> None:
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]
    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Scaffold and validate project.",
    )
    server = build_default_mcp_server(
        settings=sprint2_env["settings"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=run_state_manager,
    )

    scaffolded = server.invoke(
        "scaffold_tools.create_project_skeleton",
        run_id=run.run_id,
    )
    git = server.invoke(
        "scaffold_tools.init_git_repo",
        run_id=run.run_id,
    )
    build = server.invoke(
        "quality_tools.run_build",
        run_id=run.run_id,
        arguments={"path": "backend"},
    )
    lint = server.invoke(
        "quality_tools.run_lint",
        run_id=run.run_id,
        arguments={
            "command": [sys.executable, "-c", "print('lint-ok')"],
        },
    )

    assert "backend/app/main.py" in scaffolded.output["created_files"]
    assert git.output["workspace_root"].endswith(run.run_id + "/workspace")
    assert build.output["success"] is True
    assert lint.output["stdout"] == "lint-ok"
