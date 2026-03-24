from __future__ import annotations

from typing import Any

import pytest

from specflow.mcp import PermissionPolicy, SandboxViolationError, build_default_mcp_server
from specflow.models import ArtifactKind


def test_workspace_tools_obey_sandbox_and_delete_policy(sprint2_env: dict[str, Any]) -> None:
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]
    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Use workspace tools.",
    )
    server = build_default_mcp_server(
        settings=sprint2_env["settings"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=run_state_manager,
    )

    server.invoke(
        "workspace_tools.write_file",
        run_id=run.run_id,
        arguments={"path": "notes/readme.txt", "content": "hello"},
    )
    read = server.invoke(
        "workspace_tools.read_file",
        run_id=run.run_id,
        arguments={"path": "notes/readme.txt"},
    )
    listed = server.invoke(
        "workspace_tools.list_directory",
        run_id=run.run_id,
        arguments={"path": "notes"},
    )

    assert read.output["content"] == "hello"
    assert listed.output["entries"][0]["path"] == "notes/readme.txt"

    with pytest.raises(SandboxViolationError):
        server.invoke(
            "workspace_tools.write_file",
            run_id=run.run_id,
            arguments={"path": "../escape.txt", "content": "nope"},
        )

    deleted = server.invoke(
        "workspace_tools.delete_file",
        run_id=run.run_id,
        arguments={"path": "notes/readme.txt"},
        permission_policy=PermissionPolicy(allow_delete=True),
    )
    assert deleted.output["status"] == "deleted"


def test_spec_tools_read_summary_and_completeness(sprint2_env: dict[str, Any]) -> None:
    run_state_manager = sprint2_env["run_state_manager"]
    artifact_repository = sprint2_env["artifact_repository"]
    project_id = sprint2_env["project_id"]
    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Validate spec artifacts.",
    )
    server = build_default_mcp_server(
        settings=sprint2_env["settings"],
        artifact_repository=artifact_repository,
        run_state_manager=run_state_manager,
    )

    artifact_repository.save_artifact(
        run.run_id,
        name="spec.md",
        content="# Spec\n\nInternal ticket system.",
        kind=ArtifactKind.SPEC,
    )
    artifact_repository.save_artifact(
        run.run_id,
        name="plan.md",
        content="# Plan\n\nImplementation plan.",
        kind=ArtifactKind.PLAN,
    )
    artifact_repository.save_artifact(
        run.run_id,
        name="tasks.md",
        content="# Tasks\n\n- task one",
        kind=ArtifactKind.TASKS,
    )

    read = server.invoke("spec_tools.read_spec", run_id=run.run_id)
    summary = server.invoke("spec_tools.export_spec_summary", run_id=run.run_id)
    validation = server.invoke(
        "spec_tools.validate_spec_completeness",
        run_id=run.run_id,
        arguments={"require_contracts": True},
    )

    assert "Internal ticket system." in read.output["content"]
    assert summary.output["documents"][0]["headings"] == ["Spec"]
    assert "contracts/" in validation.output["missing_items"]
    assert validation.output["is_complete"] is False
