from __future__ import annotations

from typing import Any

from deepagents import create_deep_agent
from langchain.tools import tool

from specflow.orchestrator.models import ProjectConfig
from specflow.orchestrator.supervisor import SupervisorOrchestrator


def build_supervisor_harness(
    orchestrator: SupervisorOrchestrator,
    *,
    model: str | None = None,
    debug: bool = False,
) -> Any:
    """Create a thin Deep Agents wrapper around the deterministic supervisor."""

    @tool
    def start_supervised_run(
        prompt: str,
        mode: str = "standard",
    ) -> dict[str, Any]:
        """Start a new SpecFlow supervisor run."""

        result = orchestrator.start_run(
            input_prompt=prompt,
            mode=mode,
            project_config=ProjectConfig(),
        )
        return result.model_dump(mode="python")

    @tool
    def resume_supervised_run(
        run_id: str,
        approved: bool | None = None,
    ) -> dict[str, Any]:
        """Resume a paused supervisor run."""

        result = orchestrator.resume_run(run_id, decision=approved)
        return result.model_dump(mode="python")

    @tool
    def get_supervised_run_status(run_id: str) -> dict[str, Any]:
        """Get the current state for a SpecFlow supervisor run."""

        return orchestrator.get_run_status(run_id).model_dump(mode="python")

    return create_deep_agent(
        model=model,
        tools=[
            start_supervised_run,
            resume_supervised_run,
            get_supervised_run_status,
        ],
        system_prompt=(
            "You orchestrate SpecFlow runs. Start, resume, and inspect runs "
            "via the provided tools. "
            "Prefer artifact-driven progress and surface pending human gates clearly."
        ),
        debug=debug,
        name="specflow-supervisor",
    )
