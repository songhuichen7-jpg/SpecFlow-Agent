from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from specflow.agents.coder.blueprint import build_workspace_files
from specflow.agents.coder.models import CoderRunResult, QualityGateResult
from specflow.config import Settings, get_settings
from specflow.mcp import MCPServer, WorkspaceSandbox, build_default_mcp_server
from specflow.models import ArtifactFormat, ArtifactKind, RunPhase
from specflow.storage import ArtifactRepository, RunStateManager, StorageBucket
from specflow.storage.db import get_session_factory


class CoderAgent:
    """Materialize the generated workspace from frozen Sprint 4 artifacts."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: sessionmaker[Session] | None = None,
        artifact_repository: ArtifactRepository | None = None,
        run_state_manager: RunStateManager | None = None,
        mcp_server: MCPServer | None = None,
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

    def run(self, run_id: str, *, overwrite: bool = True) -> CoderRunResult:
        snapshot = self.run_state_manager.load_run(run_id)
        if snapshot.current_phase == RunPhase.TASKS:
            self.run_state_manager.transition_to_phase(
                run_id,
                RunPhase.IMPLEMENT,
                message="Coder started implementation from frozen tasks.",
                summary="Coder is materializing the workspace and quality gates.",
            )
        elif snapshot.current_phase is not RunPhase.IMPLEMENT:
            raise ValueError(
                "Coder can only start from tasks or implement. "
                f"Current phase: {snapshot.current_phase.value}."
            )
        return self._materialize_workspace(run_id, overwrite=overwrite)

    def fix_issues(
        self,
        run_id: str,
        *,
        issue_titles: list[str] | None = None,
        overwrite: bool = True,
    ) -> CoderRunResult:
        snapshot = self.run_state_manager.load_run(run_id)
        if snapshot.current_phase == RunPhase.REVIEW:
            self.run_state_manager.rollback_to_phase(
                run_id,
                RunPhase.IMPLEMENT,
                reason=(
                    "Applying reviewer fixes"
                    if not issue_titles
                    else f"Applying reviewer fixes: {', '.join(issue_titles)}"
                ),
            )
        elif snapshot.current_phase not in {RunPhase.IMPLEMENT, RunPhase.TASKS}:
            raise ValueError(
                "Coder fixes can only run from tasks, implement, or review. "
                f"Current phase: {snapshot.current_phase.value}."
            )
        return self._materialize_workspace(run_id, overwrite=overwrite)

    def _materialize_workspace(self, run_id: str, *, overwrite: bool) -> CoderRunResult:
        artifacts = {
            name: self.artifact_repository.load_artifact(run_id, name=name).content
            for name in ("spec.md", "data-model.md", "tasks.md", "contracts/openapi.yaml")
        }
        templates = self._load_template_assets(run_id)
        files = build_workspace_files(
            ticket_api_template=templates["api/tickets_router.py"],
            ticket_list_template=templates["pages/ticket-list.tsx"],
            ticket_detail_template=templates["pages/ticket-detail.tsx"],
            ticket_test_template=templates["tests/test_ticket_api.py"],
            playwright_config_template=templates["config/playwright.config.ts"],
            spec_excerpt=_first_non_heading_line(artifacts["spec.md"]),
            tasks_excerpt=_first_non_heading_line(artifacts["tasks.md"]),
        )

        scaffolded = self.mcp_server.invoke(
            "scaffold_tools.create_project_skeleton",
            run_id=run_id,
            arguments={"overwrite": overwrite},
        )
        written_files = list(scaffolded.output["created_files"])
        for path, content in files.items():
            self.mcp_server.invoke(
                "workspace_tools.write_file",
                run_id=run_id,
                arguments={"path": path, "content": content, "overwrite": overwrite},
            )
            if path not in written_files:
                written_files.append(path)

        quality_gates = self._run_quality_gates(run_id)
        quality_report = {
            "summary": {
                "all_checks_passed": all(result.success for result in quality_gates.values()),
                "spec_excerpt": _first_non_heading_line(artifacts["spec.md"]),
                "tasks_excerpt": _first_non_heading_line(artifacts["tasks.md"]),
            },
            "checks": {
                name: result.model_dump(mode="python") for name, result in quality_gates.items()
            },
        }
        sandbox = WorkspaceSandbox(
            run_id,
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )
        workspace_manifest = {
            "files": _list_workspace_files(sandbox.root),
            "contract_excerpt": _first_non_heading_line(artifacts["contracts/openapi.yaml"]),
        }

        artifact_versions: dict[str, int] = {}
        quality_artifact = self.artifact_repository.save_artifact(
            run_id,
            name="quality-report.json",
            content=quality_report,
            kind=ArtifactKind.TEST_REPORT,
            artifact_format=ArtifactFormat.JSON,
            bucket=StorageBucket.REPORTS,
            details={"generated_by": "coder"},
        )
        artifact_versions[quality_artifact.name] = quality_artifact.version
        manifest_artifact = self.artifact_repository.save_artifact(
            run_id,
            name="workspace-manifest.json",
            content=workspace_manifest,
            kind=ArtifactKind.CODE_BUNDLE,
            artifact_format=ArtifactFormat.JSON,
            details={"generated_by": "coder"},
        )
        artifact_versions[manifest_artifact.name] = manifest_artifact.version

        snapshot = self.run_state_manager.load_run(run_id)
        return CoderRunResult(
            run_id=run_id,
            current_phase=snapshot.current_phase,
            written_files=written_files,
            quality_gates=quality_gates,
            artifact_versions=artifact_versions,
        )

    def _load_template_assets(self, run_id: str) -> dict[str, str]:
        keys = (
            "api/tickets_router.py",
            "pages/ticket-list.tsx",
            "pages/ticket-detail.tsx",
            "tests/test_ticket_api.py",
            "config/playwright.config.ts",
        )
        return {
            key: self.mcp_server.invoke(
                "template_tools.get_template_content",
                run_id=run_id,
                arguments={"key": key},
            ).output["content"]
            for key in keys
        }

    def _run_quality_gates(self, run_id: str) -> dict[str, QualityGateResult]:
        quality_results = {
            "backend_lint": self.mcp_server.invoke(
                "quality_tools.run_lint",
                run_id=run_id,
                arguments={
                    "path": "backend",
                    "command": [sys.executable, "-m", "ruff", "check", "app", "tests"],
                },
            ).output,
            "backend_build": self.mcp_server.invoke(
                "quality_tools.run_build",
                run_id=run_id,
                arguments={"path": "backend"},
            ).output,
            "backend_tests": self.mcp_server.invoke(
                "quality_tools.run_tests",
                run_id=run_id,
                arguments={
                    "path": "backend",
                    "command": [sys.executable, "-m", "pytest", "tests", "-q"],
                },
            ).output,
            "backend_import_smoke": self.mcp_server.invoke(
                "quality_tools.check_types",
                run_id=run_id,
                arguments={
                    "path": "backend",
                    "command": [
                        sys.executable,
                        "-c",
                        (
                            "from app.main import app; "
                            "from app.services.ticket_service import ticket_service; "
                            "assert app.title; "
                            "assert ticket_service.list_users(); "
                            "print('backend-import-ok')"
                        ),
                    ],
                },
            ).output,
            "frontend_manifest": self.mcp_server.invoke(
                "quality_tools.run_build",
                run_id=run_id,
                arguments={
                    "path": "frontend",
                    "command": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "required = ["
                            "'src/App.tsx', "
                            "'src/components/TicketTable.tsx', "
                            "'src/pages/TicketDashboardPage.tsx', "
                            "'src/services/api.ts', "
                            "'src/types/ticket.ts', "
                            "'vite.config.ts'"
                            "]; "
                            "missing = [item for item in required if not Path(item).exists()]; "
                            "assert not missing, missing; "
                            "print('frontend-files-ok')"
                        ),
                    ],
                },
            ).output,
        }
        return {
            name: QualityGateResult(
                name=name,
                path=str(result["path"]),
                success=bool(result["success"]),
                command=[str(item) for item in result["command"]],
                returncode=int(result["returncode"]),
                stdout=str(result["stdout"]),
                stderr=str(result["stderr"]),
            )
            for name, result in quality_results.items()
        }


def _first_non_heading_line(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _list_workspace_files(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
