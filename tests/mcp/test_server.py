from __future__ import annotations

from typing import Any

import pytest

from specflow.mcp import (
    PermissionDeniedError,
    PermissionPolicy,
    ToolNotFoundError,
    build_default_mcp_server,
)
from specflow.models import RunPhase


def test_mcp_server_lists_tools_and_dispatches_by_short_name(sprint2_env: dict[str, Any]) -> None:
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]

    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Use the MCP server.",
    )
    server = build_default_mcp_server(
        settings=sprint2_env["settings"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=run_state_manager,
    )

    tool_names = {tool["full_name"] for tool in server.list_tools()}
    result = server.invoke("list_available_templates", run_id=run.run_id)

    assert "workspace_tools.write_file" in tool_names
    assert "quality_tools.run_tests" in tool_names
    assert result.success is True
    assert result.group.value == "template_tools"

    run = run_state_manager.transition_to_phase(run.run_id, RunPhase.SPECIFY)
    assert run.current_phase == RunPhase.SPECIFY


def test_mcp_server_enforces_permissions_and_missing_tools(sprint2_env: dict[str, Any]) -> None:
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]

    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Use the MCP server.",
    )
    server = build_default_mcp_server(
        settings=sprint2_env["settings"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=run_state_manager,
    )

    with pytest.raises(PermissionDeniedError):
        server.invoke(
            "workspace_tools.delete_file",
            run_id=run.run_id,
            arguments={"path": "notes.txt"},
            permission_policy=PermissionPolicy(allow_delete=False),
        )

    with pytest.raises(ToolNotFoundError):
        server.invoke("unknown_tool", run_id=run.run_id)
