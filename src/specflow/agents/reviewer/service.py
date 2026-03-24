from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from specflow.agents.reviewer.models import (
    ReviewerFinding,
    ReviewNarrativeBundle,
    ReviewRunResult,
)
from specflow.config import Settings, get_settings
from specflow.llm import build_chat_model
from specflow.mcp import MCPServer, WorkspaceSandbox, build_default_mcp_server
from specflow.models import (
    ArtifactKind,
    ReviewIssue,
    ReviewIssueStatus,
    ReviewSeverity,
    RunPhase,
)
from specflow.storage import ArtifactRepository, RunStateManager, StorageBucket
from specflow.storage.db import get_session_factory, session_scope


class ReviewerAgent:
    """Compare frozen Sprint 4 artifacts against the generated workspace."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: sessionmaker[Session] | None = None,
        artifact_repository: ArtifactRepository | None = None,
        run_state_manager: RunStateManager | None = None,
        mcp_server: MCPServer | None = None,
        chat_model: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_directories()
        self.session_factory = (
            session_factory
            or (run_state_manager.session_factory if run_state_manager is not None else None)
            or get_session_factory()
        )
        self.artifact_repository = artifact_repository or ArtifactRepository(
            session_factory=self.session_factory,
            settings=self.settings,
        )
        self.run_state_manager = run_state_manager or RunStateManager(
            session_factory=self.session_factory,
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )
        self.mcp_server = mcp_server or build_default_mcp_server(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
        )
        self.chat_model = chat_model or (
            build_chat_model(self.settings) if self.settings.llm_model else None
        )

    def run(self, run_id: str) -> ReviewRunResult:
        snapshot = self.run_state_manager.load_run(run_id)
        if snapshot.current_phase == RunPhase.IMPLEMENT:
            self.run_state_manager.transition_to_phase(
                run_id,
                RunPhase.REVIEW,
                message="Reviewer started spec compliance review.",
                summary="Reviewer is validating workspace output against the frozen spec.",
            )
        elif snapshot.current_phase is not RunPhase.REVIEW:
            raise ValueError(
                "Reviewer can only run from implement or review. "
                f"Current phase: {snapshot.current_phase.value}."
            )

        spec = self.artifact_repository.load_artifact(run_id, name="spec.md")
        contract = self.artifact_repository.load_artifact(run_id, name="contracts/openapi.yaml")
        data_model = self.artifact_repository.load_artifact(run_id, name="data-model.md")
        quality_report = self.artifact_repository.load_artifact(run_id, name="quality-report.json")
        quality_payload = json.loads(quality_report.content)
        quality_checks = {
            name: bool(check["success"])
            for name, check in quality_payload.get("checks", {}).items()
        }

        sandbox = WorkspaceSandbox(
            run_id,
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )
        issues = self._collect_findings(
            run_id=run_id,
            sandbox=sandbox,
            spec_content=spec.content,
            contract_content=contract.content,
            data_model_content=data_model.content,
            quality_checks=quality_checks,
        )
        blocking = any(
            issue.severity in {ReviewSeverity.HIGH, ReviewSeverity.CRITICAL} for issue in issues
        )
        approved = not blocking and not issues
        narrative = self._build_review_narrative(
            spec_content=spec.content,
            issues=issues,
            quality_checks=quality_checks,
            approved=approved,
        )

        report = self.artifact_repository.save_artifact(
            run_id,
            name="review-report.md",
            content=self._render_review_report(
                issues=issues,
                quality_checks=quality_checks,
                approved=approved,
                narrative=narrative,
            ),
            kind=ArtifactKind.REVIEW_REPORT,
            bucket=StorageBucket.REPORTS,
            details={"generated_by": "reviewer", "blocking": blocking},
        )
        self._sync_review_issues(run_id=run_id, issues=issues, artifact_id=report.artifact_id)

        snapshot = self.run_state_manager.load_run(run_id)
        return ReviewRunResult(
            run_id=run_id,
            current_phase=snapshot.current_phase,
            approved=approved,
            blocking=blocking,
            report_version=report.version,
            issues=issues,
            quality_checks=quality_checks,
        )

    def _collect_findings(
        self,
        *,
        run_id: str,
        sandbox: WorkspaceSandbox,
        spec_content: str,
        contract_content: str,
        data_model_content: str,
        quality_checks: dict[str, bool],
    ) -> list[ReviewerFinding]:
        findings: list[ReviewerFinding] = []
        findings.extend(self._missing_file_findings(sandbox))
        findings.extend(
            self._api_contract_findings(run_id=run_id, contract_content=contract_content)
        )
        findings.extend(
            self._data_model_findings(run_id=run_id, data_model_content=data_model_content)
        )
        findings.extend(self._workspace_content_findings(run_id=run_id, spec_content=spec_content))
        for name, success in quality_checks.items():
            if success:
                continue
            findings.append(
                ReviewerFinding(
                    title=f"Quality gate failed: {name}",
                    description=(
                        f"The generated workspace did not pass the `{name}` quality gate."
                    ),
                    severity=ReviewSeverity.CRITICAL,
                    spec_reference="tasks.md#ARCH-006",
                    code_reference="quality-report.json",
                    suggested_fix=(
                        "Regenerate the affected workspace files and rerun the relevant "
                        "quality tool before requesting review again."
                    ),
                )
            )
        return findings

    def _missing_file_findings(self, sandbox: WorkspaceSandbox) -> list[ReviewerFinding]:
        required_files = {
            "backend/app/routers/tickets.py": ("spec.md#APIs", ReviewSeverity.CRITICAL),
            "backend/app/routers/directories.py": ("spec.md#APIs", ReviewSeverity.HIGH),
            "backend/app/routers/dashboard.py": ("spec.md#Pages", ReviewSeverity.HIGH),
            "backend/app/models/ticket.py": ("data-model.md#Ticket", ReviewSeverity.CRITICAL),
            "backend/app/services/ticket_service.py": ("plan.md#Backend", ReviewSeverity.HIGH),
            "backend/tests/test_tickets.py": ("tasks.md#ARCH-006", ReviewSeverity.HIGH),
            "frontend/src/pages/TicketListPage.tsx": ("spec.md#Pages", ReviewSeverity.HIGH),
            "frontend/src/pages/TicketDetailPage.tsx": ("spec.md#Pages", ReviewSeverity.HIGH),
            "frontend/src/pages/TicketCreatePage.tsx": ("spec.md#Pages", ReviewSeverity.HIGH),
            "frontend/src/pages/TicketEditPage.tsx": ("spec.md#Pages", ReviewSeverity.HIGH),
            "frontend/src/pages/TicketDashboardPage.tsx": ("spec.md#Pages", ReviewSeverity.HIGH),
            "frontend/src/components/TicketTable.tsx": ("plan.md#Frontend", ReviewSeverity.MEDIUM),
            "README.md": ("plan.md#Delivery Strategy", ReviewSeverity.MEDIUM),
        }
        findings: list[ReviewerFinding] = []
        for path, (reference, severity) in required_files.items():
            if sandbox.resolve(path).exists():
                continue
            findings.append(
                ReviewerFinding(
                    title=f"Missing implementation artifact: {path}",
                    description=f"The generated workspace is missing `{path}`.",
                    severity=severity,
                    spec_reference=reference,
                    code_reference=path,
                    suggested_fix=(
                        "Regenerate the workspace file from the frozen template/profile set."
                    ),
                )
            )
        return findings

    def _api_contract_findings(
        self,
        *,
        run_id: str,
        contract_content: str,
    ) -> list[ReviewerFinding]:
        files = {
            "tickets": self._read_workspace_file(run_id, "backend/app/routers/tickets.py"),
            "directories": self._read_workspace_file(run_id, "backend/app/routers/directories.py"),
            "dashboard": self._read_workspace_file(run_id, "backend/app/routers/dashboard.py"),
        }
        requirements = {
            "/api/tickets": (
                files["tickets"],
                "Ticket CRUD router is missing the main resource path.",
            ),
            "/transition": (files["tickets"], "Ticket workflow transition endpoint is missing."),
            "/comments": (files["tickets"], "Ticket comment timeline endpoints are missing."),
            "/attachments": (files["tickets"], "Ticket attachment endpoints are missing."),
            "/api/users": (files["directories"], "User directory endpoint is missing."),
            "/api/departments": (files["directories"], "Department directory endpoint is missing."),
            "/api/dashboard": (files["dashboard"], "Dashboard summary endpoint is missing."),
        }
        findings: list[ReviewerFinding] = []
        for token, (content, description) in requirements.items():
            if token not in contract_content:
                continue
            if token in content:
                continue
            findings.append(
                ReviewerFinding(
                    title=f"Contract drift: missing token `{token}`",
                    description=description,
                    severity=ReviewSeverity.HIGH,
                    spec_reference="contracts/openapi.yaml",
                    code_reference="backend/app/routers",
                    suggested_fix=(
                        "Align the router implementation with the frozen OpenAPI contract."
                    ),
                )
            )
        return findings

    def _data_model_findings(
        self,
        *,
        run_id: str,
        data_model_content: str,
    ) -> list[ReviewerFinding]:
        model_content = self._read_workspace_file(run_id, "backend/app/models/ticket.py")
        required_tokens = (
            "class TicketRecord",
            "class UserRecord",
            "class DepartmentRecord",
            "class CommentRecord",
            "class AttachmentRecord",
            "state",
            "priority",
            "department_id",
        )
        if all(token in model_content for token in required_tokens):
            return []
        return (
            [
                ReviewerFinding(
                    title="Data model coverage is incomplete",
                    description=(
                        "The generated backend models do not cover all required entities or fields."
                    ),
                    severity=ReviewSeverity.CRITICAL,
                    spec_reference="data-model.md",
                    code_reference="backend/app/models/ticket.py",
                    suggested_fix=(
                        "Regenerate the domain model module so ticket, user, department, "
                        "comment, and attachment coverage matches the frozen data model."
                    ),
                )
            ]
            if "## Ticket" in data_model_content
            else []
        )

    def _workspace_content_findings(
        self,
        *,
        run_id: str,
        spec_content: str,
    ) -> list[ReviewerFinding]:
        app_content = self._read_workspace_file(run_id, "frontend/src/App.tsx")
        readme_content = self._read_workspace_file(run_id, "README.md")
        findings: list[ReviewerFinding] = []
        if "TicketDashboardPage" not in app_content and "Dashboard" in spec_content:
            findings.append(
                ReviewerFinding(
                    title="Dashboard page is not wired into the frontend shell",
                    description=(
                        "The spec requires a dashboard page, but the frontend shell "
                        "does not render it."
                    ),
                    severity=ReviewSeverity.HIGH,
                    spec_reference="spec.md#Pages",
                    code_reference="frontend/src/App.tsx",
                    suggested_fix=(
                        "Import and render the dashboard page in the frontend application shell."
                    ),
                )
            )
        if "Sprint 5" not in readme_content:
            findings.append(
                ReviewerFinding(
                    title="README lacks implementation context",
                    description=(
                        "The generated README should summarize the frozen scope "
                        "and workspace layout."
                    ),
                    severity=ReviewSeverity.MEDIUM,
                    spec_reference="plan.md#Delivery Strategy",
                    code_reference="README.md",
                    suggested_fix=("Regenerate README.md with scope, structure, and run commands."),
                )
            )
        return findings

    def _read_workspace_file(self, run_id: str, path: str) -> str:
        try:
            return self.mcp_server.invoke(
                "workspace_tools.read_file",
                run_id=run_id,
                arguments={"path": path},
            ).output["content"]
        except FileNotFoundError:
            return ""

    def _sync_review_issues(
        self,
        *,
        run_id: str,
        issues: Iterable[ReviewerFinding],
        artifact_id: str,
    ) -> None:
        with session_scope(self.session_factory) as session:
            session.execute(delete(ReviewIssue).where(ReviewIssue.run_id == run_id))
            for issue in issues:
                session.add(
                    ReviewIssue(
                        run_id=run_id,
                        artifact_id=artifact_id,
                        title=issue.title,
                        description=issue.description,
                        severity=issue.severity,
                        status=ReviewIssueStatus.OPEN,
                        spec_reference=issue.spec_reference,
                        code_reference=issue.code_reference,
                        suggested_fix=issue.suggested_fix,
                    )
                )

    def _render_review_report(
        self,
        *,
        issues: list[ReviewerFinding],
        quality_checks: dict[str, bool],
        approved: bool,
        narrative: ReviewNarrativeBundle,
    ) -> str:
        verdict = "approved" if approved else "changes requested"
        checks = "\n".join(
            f"- {name}: {'passed' if success else 'failed'}"
            for name, success in sorted(quality_checks.items())
        )
        if not issues:
            findings = "No blocking or advisory findings were detected."
        else:
            findings = "\n\n".join(
                [
                    "\n".join(
                        [
                            f"### {issue.severity.value.upper()} - {issue.title}",
                            f"- Description: {issue.description}",
                            f"- Spec Reference: {issue.spec_reference or 'n/a'}",
                            f"- Code Reference: {issue.code_reference or 'n/a'}",
                            f"- Suggested Fix: {issue.suggested_fix or 'n/a'}",
                        ]
                    )
                    for issue in issues
                ]
            )
        risk_note = f"## Risk Note\n{narrative.risk_note}\n\n" if narrative.risk_note else ""
        return (
            "# Review Report\n\n"
            "## Verdict\n"
            f"- Status: {verdict}\n"
            f"- Blocking: {_is_blocking(issues)}\n\n"
            "## Summary\n"
            f"{narrative.verdict_summary}\n\n"
            "## Quality Gates\n"
            f"{checks}\n\n"
            f"{risk_note}"
            "## Findings\n"
            f"{findings}\n\n"
            "## Next Steps\n"
            f"{narrative.next_steps_markdown}\n"
        )

    def _build_review_narrative(
        self,
        *,
        spec_content: str,
        issues: list[ReviewerFinding],
        quality_checks: dict[str, bool],
        approved: bool,
    ) -> ReviewNarrativeBundle:
        deterministic = ReviewNarrativeBundle(
            verdict_summary=_default_verdict_summary(issues=issues, approved=approved),
            next_steps_markdown=_default_next_steps(issues=issues, approved=approved),
            risk_note=_default_risk_note(issues=issues),
        )
        if self.chat_model is None:
            return deterministic

        structured_model = self.chat_model.with_structured_output(ReviewNarrativeBundle)
        context = {
            "approved": approved,
            "quality_checks": quality_checks,
            "issues": [issue.model_dump(mode="python") for issue in issues],
            "spec_excerpt": spec_content[:2000],
            "starter_narrative": deterministic.model_dump(mode="python"),
        }

        try:
            draft = cast(
                ReviewNarrativeBundle,
                structured_model.invoke(
                    [
                        SystemMessage(
                            content=(
                                "You are the SpecFlow reviewer narrator. "
                                "Refine the provided review summary while preserving "
                                "the actual verdict, risk posture, and listed findings. "
                                "Keep the tone crisp and practical. "
                                "Do not invent extra defects or approvals."
                            )
                        ),
                        HumanMessage(
                            content=(
                                "Refine this review narrative for an engineering team.\n\n"
                                f"{json.dumps(context, ensure_ascii=False, indent=2)}"
                            )
                        ),
                    ]
                ),
            )
        except Exception:
            return deterministic

        return ReviewNarrativeBundle(
            verdict_summary=_sanitize_review_text(
                draft.verdict_summary,
                deterministic.verdict_summary,
            ),
            next_steps_markdown=_sanitize_review_text(
                draft.next_steps_markdown,
                deterministic.next_steps_markdown,
            ),
            risk_note=_sanitize_optional_review_text(
                draft.risk_note,
                deterministic.risk_note,
            ),
        )


def _is_blocking(issues: list[ReviewerFinding]) -> bool:
    return any(issue.severity in {ReviewSeverity.HIGH, ReviewSeverity.CRITICAL} for issue in issues)


def _default_verdict_summary(*, issues: list[ReviewerFinding], approved: bool) -> str:
    if approved:
        return (
            "The generated workspace aligns with the frozen specification, contract, "
            "and quality gates reviewed in this pass."
        )
    blocking_count = sum(
        1 for issue in issues if issue.severity in {ReviewSeverity.HIGH, ReviewSeverity.CRITICAL}
    )
    return (
        "The workspace is not ready for delivery yet. "
        f"This review found {len(issues)} issue(s), including {blocking_count} blocking item(s)."
    )


def _default_next_steps(*, issues: list[ReviewerFinding], approved: bool) -> str:
    if approved:
        return "- Proceed to final delivery and keep the current artifact set frozen."
    ordered = issues[:3]
    if not ordered:
        return "- Re-run the reviewer after regenerating the workspace."
    return "\n".join(f"- {issue.suggested_fix or issue.title}" for issue in ordered)


def _default_risk_note(*, issues: list[ReviewerFinding]) -> str | None:
    critical = [issue.title for issue in issues if issue.severity is ReviewSeverity.CRITICAL]
    if not critical:
        return None
    return f"Critical attention required for: {', '.join(critical)}."


def _sanitize_review_text(value: str, fallback: str) -> str:
    stripped = value.strip()
    if not stripped:
        return fallback
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
    return stripped or fallback


def _sanitize_optional_review_text(value: str | None, fallback: str | None) -> str | None:
    if value is None:
        return fallback
    stripped = _sanitize_review_text(value, fallback or "")
    return stripped or fallback
