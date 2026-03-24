from __future__ import annotations

from typing import Any

from sqlalchemy import select

from specflow.agents import ArchitectAgent, ClarificationGraph
from specflow.models import ArtifactKind, RunPhase, TaskItem, TemplateProfile
from specflow.templates import DEFAULT_TEMPLATE_PROFILE, ensure_template_profile_record


def test_clarification_graph_caps_rounds_and_returns_structured_output() -> None:
    graph = ClarificationGraph()

    result = graph.run(
        request="帮我做一个内部工单管理系统",
        template_profile=DEFAULT_TEMPLATE_PROFILE,
        target_stack=DEFAULT_TEMPLATE_PROFILE.default_stack,
        supplemental_inputs=[],
        max_rounds=2,
    )

    assert result.is_complete is False
    assert result.completeness_score < 0.75
    assert result.rounds == []
    assert any("角色" in question for question in result.open_questions)


def test_architect_agent_generates_sprint4_artifacts(sprint2_env: dict[str, Any]) -> None:
    architect = ArchitectAgent(
        settings=sprint2_env["settings"],
        session_factory=sprint2_env["session_factory"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=sprint2_env["run_state_manager"],
        checkpoint_manager=sprint2_env["checkpoint_manager"],
    )
    run_state_manager = sprint2_env["run_state_manager"]
    artifact_repository = sprint2_env["artifact_repository"]
    session_factory = sprint2_env["session_factory"]
    project_id = sprint2_env["project_id"]

    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="帮我做一个内部工单管理系统，支持员工提交工单和管理员处理，包含附件和仪表盘。",
    )
    result = architect.run(
        run.run_id,
        supplemental_inputs=[
            (
                "需要部门维度、优先级 SLA、状态从 open -> in_progress "
                "-> resolved -> closed，角色包括员工、处理人、管理员。"
            )
        ],
    )

    current = run_state_manager.load_run(run.run_id)
    artifacts = artifact_repository.list_artifacts(run.run_id, latest_only=True)
    artifact_names = {artifact.name for artifact in artifacts}

    assert result.current_phase == RunPhase.TASKS
    assert current.current_phase == RunPhase.TASKS
    assert result.clarification.is_complete is True
    assert ".specify/memory/constitution.md" in artifact_names
    assert "clarification-notes.md" in artifact_names
    assert "spec.md" in artifact_names
    assert "data-model.md" in artifact_names
    assert "plan.md" in artifact_names
    assert "research.md" in artifact_names
    assert "contracts/openapi.yaml" in artifact_names
    assert "tasks.md" in artifact_names

    spec_artifact = artifact_repository.load_artifact(run.run_id, name="spec.md")
    contract_artifact = artifact_repository.load_artifact(run.run_id, name="contracts/openapi.yaml")
    tasks_artifact = artifact_repository.load_artifact(run.run_id, name="tasks.md")

    assert "内部工单系统" in spec_artifact.content
    assert "open -> in_progress -> resolved -> closed" in spec_artifact.content
    assert "/api/tickets" in contract_artifact.content
    assert "ARCH-001" in tasks_artifact.content

    with session_factory() as session:
        task_items = list(session.scalars(select(TaskItem).where(TaskItem.run_id == run.run_id)))

    assert len(task_items) == 6
    assert {task.task_key for task in task_items} == {
        "ARCH-001",
        "ARCH-002",
        "ARCH-003",
        "ARCH-004",
        "ARCH-005",
        "ARCH-006",
    }
    assert any(artifact.kind == ArtifactKind.CONTRACT for artifact in artifacts)


def test_default_template_profile_is_persistable(sprint2_env: dict[str, Any]) -> None:
    session_factory = sprint2_env["session_factory"]

    definition = ensure_template_profile_record(session_factory)

    with session_factory() as session:
        stored = session.scalar(
            select(TemplateProfile).where(
                TemplateProfile.slug == definition.slug,
                TemplateProfile.version == definition.version,
            )
        )

    assert stored is not None
    assert stored.defaults["attachments_enabled"] is True
    assert stored.constraints["workflow"]["states"] == list(DEFAULT_TEMPLATE_PROFILE.state_machine)
    assert len(stored.constraints["entities"]) == 5
