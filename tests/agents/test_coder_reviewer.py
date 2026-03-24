from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from specflow.agents import (
    ArchitectAgent,
    CoderAgent,
    ReviewerAgent,
    ReviewFixLoop,
)
from specflow.mcp import WorkspaceSandbox
from specflow.models import ExecutionEvent, ReviewIssue, RunPhase, RunStatus


def test_coder_agent_materializes_workspace_and_quality_reports(
    sprint2_env: dict[str, Any],
) -> None:
    run_id = _prepare_run_with_architect(sprint2_env)
    coder = _build_coder(sprint2_env)
    artifact_repository = sprint2_env["artifact_repository"]
    session_factory = sprint2_env["session_factory"]

    result = coder.run(run_id)

    sandbox = WorkspaceSandbox(
        run_id,
        settings=sprint2_env["settings"],
        artifact_repository=artifact_repository,
    )
    quality_report = artifact_repository.load_artifact(run_id, name="quality-report.json")
    manifest = artifact_repository.load_artifact(run_id, name="workspace-manifest.json")

    assert result.current_phase == RunPhase.IMPLEMENT
    assert all(gate.success for gate in result.quality_gates.values())
    assert sandbox.resolve("backend/app/routers/tickets.py").exists()
    assert sandbox.resolve("frontend/src/pages/TicketDashboardPage.tsx").exists()
    assert "backend/app/routers/tickets.py" in json.loads(manifest.content)["files"]
    assert json.loads(quality_report.content)["summary"]["all_checks_passed"] is True

    with session_factory() as session:
        events = list(
            session.scalars(select(ExecutionEvent).where(ExecutionEvent.run_id == run_id))
        )
    called_tools = {
        str(event.payload.get("tool")) for event in events if event.payload.get("tool") is not None
    }

    assert "scaffold_tools.create_project_skeleton" in called_tools
    assert "template_tools.get_template_content" in called_tools
    assert "workspace_tools.write_file" in called_tools
    assert "quality_tools.run_tests" in called_tools


def test_reviewer_agent_approves_clean_workspace(sprint2_env: dict[str, Any]) -> None:
    run_id = _prepare_run_with_architect(sprint2_env)
    coder = _build_coder(sprint2_env)
    reviewer = _build_reviewer(sprint2_env)
    artifact_repository = sprint2_env["artifact_repository"]

    coder.run(run_id)
    result = reviewer.run(run_id)
    report = artifact_repository.load_artifact(run_id, name="review-report.md")

    assert result.current_phase == RunPhase.REVIEW
    assert result.approved is True
    assert result.blocking is False
    assert result.issues == []
    assert "Status: approved" in report.content


def test_reviewer_agent_detects_missing_dashboard_page(sprint2_env: dict[str, Any]) -> None:
    run_id = _prepare_run_with_architect(sprint2_env)
    coder = _build_coder(sprint2_env)
    reviewer = _build_reviewer(sprint2_env)
    artifact_repository = sprint2_env["artifact_repository"]
    session_factory = sprint2_env["session_factory"]

    coder.run(run_id)
    sandbox = WorkspaceSandbox(
        run_id,
        settings=sprint2_env["settings"],
        artifact_repository=artifact_repository,
    )
    sandbox.delete_path("frontend/src/pages/TicketDashboardPage.tsx")

    result = reviewer.run(run_id)
    report = artifact_repository.load_artifact(run_id, name="review-report.md")

    assert result.approved is False
    assert result.blocking is True
    assert any("TicketDashboardPage.tsx" in issue.title for issue in result.issues)
    assert "TicketDashboardPage.tsx" in report.content

    with session_factory() as session:
        issues = list(session.scalars(select(ReviewIssue).where(ReviewIssue.run_id == run_id)))

    assert issues
    assert any(
        issue.code_reference == "frontend/src/pages/TicketDashboardPage.tsx" for issue in issues
    )


def test_reviewer_agent_uses_model_for_report_narrative(sprint2_env: dict[str, Any]) -> None:
    run_id = _prepare_run_with_architect(sprint2_env)
    coder = _build_coder(sprint2_env)
    artifact_repository = sprint2_env["artifact_repository"]

    class _FakeStructuredReviewer:
        def invoke(self, _messages: list[object]) -> object:
            from specflow.agents.reviewer.models import ReviewNarrativeBundle

            return ReviewNarrativeBundle(
                verdict_summary="LLM summary: implementation is ready for delivery.",
                next_steps_markdown="- LLM step: publish the generated workspace artifacts.",
                risk_note="LLM note: no material risk remains in this pass.",
            )

    class _FakeReviewerModel:
        def with_structured_output(self, _schema: object) -> _FakeStructuredReviewer:
            return _FakeStructuredReviewer()

    reviewer = _build_reviewer(sprint2_env, chat_model=_FakeReviewerModel())

    coder.run(run_id)
    result = reviewer.run(run_id)
    report = artifact_repository.load_artifact(run_id, name="review-report.md")

    assert result.approved is True
    assert "LLM summary: implementation is ready for delivery." in report.content
    assert "LLM step: publish the generated workspace artifacts." in report.content
    assert "LLM note: no material risk remains in this pass." in report.content


def test_review_fix_loop_repairs_missing_file(sprint2_env: dict[str, Any]) -> None:
    run_id = _prepare_run_with_architect(sprint2_env)
    coder = _build_coder(sprint2_env)
    reviewer = _build_reviewer(sprint2_env)
    loop = ReviewFixLoop(
        settings=sprint2_env["settings"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=sprint2_env["run_state_manager"],
        coder=coder,
        reviewer=reviewer,
    )
    artifact_repository = sprint2_env["artifact_repository"]
    run_state_manager = sprint2_env["run_state_manager"]

    coder.run(run_id)
    sandbox = WorkspaceSandbox(
        run_id,
        settings=sprint2_env["settings"],
        artifact_repository=artifact_repository,
    )
    sandbox.delete_path("frontend/src/pages/TicketDashboardPage.tsx")

    result = loop.run(run_id, max_iterations=1)
    current = run_state_manager.load_run(run_id)

    assert result.approved is True
    assert result.requires_human_arbitration is False
    assert result.iterations == 1
    assert sandbox.resolve("frontend/src/pages/TicketDashboardPage.tsx").exists()
    assert current.current_phase == RunPhase.REVIEW
    assert current.human_gate_pending is False


def test_review_fix_loop_requests_human_gate_when_budget_exhausted(
    sprint2_env: dict[str, Any],
) -> None:
    run_id = _prepare_run_with_architect(sprint2_env)
    coder = _build_coder(sprint2_env)
    reviewer = _build_reviewer(sprint2_env)
    loop = ReviewFixLoop(
        settings=sprint2_env["settings"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=sprint2_env["run_state_manager"],
        coder=coder,
        reviewer=reviewer,
    )
    artifact_repository = sprint2_env["artifact_repository"]
    run_state_manager = sprint2_env["run_state_manager"]

    coder.run(run_id)
    sandbox = WorkspaceSandbox(
        run_id,
        settings=sprint2_env["settings"],
        artifact_repository=artifact_repository,
    )
    sandbox.delete_path("frontend/src/pages/TicketDashboardPage.tsx")

    result = loop.run(run_id, max_iterations=0)
    current = run_state_manager.load_run(run_id)

    assert result.approved is False
    assert result.requires_human_arbitration is True
    assert current.current_phase == RunPhase.REVIEW
    assert current.human_gate_pending is True
    assert current.status == RunStatus.WAITING_FOR_HUMAN


def _prepare_run_with_architect(sprint2_env: dict[str, Any]) -> str:
    architect = ArchitectAgent(
        settings=sprint2_env["settings"],
        session_factory=sprint2_env["session_factory"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=sprint2_env["run_state_manager"],
        checkpoint_manager=sprint2_env["checkpoint_manager"],
    )
    run = sprint2_env["run_state_manager"].create_run(
        project_id=sprint2_env["project_id"],
        input_prompt="帮我做一个内部工单管理系统，支持员工提交工单、管理员处理、附件和仪表盘。",
    )
    architect.run(
        run.run_id,
        supplemental_inputs=[
            (
                "需要部门维度、状态从 open -> in_progress -> resolved -> closed，"
                "角色包括员工、处理人、管理员，并且要保留评论时间线。"
            )
        ],
    )
    return run.run_id


def _build_coder(sprint2_env: dict[str, Any]) -> CoderAgent:
    return CoderAgent(
        settings=sprint2_env["settings"],
        session_factory=sprint2_env["session_factory"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=sprint2_env["run_state_manager"],
    )


def _build_reviewer(sprint2_env: dict[str, Any], *, chat_model: Any | None = None) -> ReviewerAgent:
    return ReviewerAgent(
        settings=sprint2_env["settings"],
        session_factory=sprint2_env["session_factory"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=sprint2_env["run_state_manager"],
        chat_model=chat_model,
    )
