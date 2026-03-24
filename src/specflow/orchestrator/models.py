from __future__ import annotations

from pydantic import BaseModel, Field

from specflow.models import ExecutionMode, RunPhase, RunStatus, TemplateType


class ProjectConfig(BaseModel):
    """Project bootstrap config for the supervisor orchestration layer."""

    name: str = "SpecFlow Ticket System"
    slug: str = "specflow-ticket-system"
    template_type: TemplateType = TemplateType.TICKET_SYSTEM
    target_stack: str = "fastapi-react-vite-typescript-postgresql"
    description: str | None = "Default project used by the SpecFlow supervisor integration tests."


class HumanGateRequest(BaseModel):
    """Serializable human gate request emitted by the supervisor."""

    run_id: str
    gate_name: str
    phase: RunPhase
    message: str
    payload: dict[str, object] = Field(default_factory=dict)


class HumanGateDecision(BaseModel):
    """Decision returned by a human gate provider or explicit resume call."""

    approved: bool
    reason: str


class SupervisorRunResult(BaseModel):
    """Top-level orchestration result for a run or resume action."""

    run_id: str
    project_id: str
    status: RunStatus
    current_phase: RunPhase
    mode: ExecutionMode
    review_approved: bool | None = None
    pending_gate: HumanGateRequest | None = None
    artifact_names: list[str] = Field(default_factory=list)
    workspace_root: str
    summary: str | None = None
