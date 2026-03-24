from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from specflow.models import RunPhase


class ClarificationQuestion(BaseModel):
    """A single clarification question emitted by the LangGraph loop."""

    key: str
    question: str
    reason: str


class ClarificationRound(BaseModel):
    """Captured clarify round with questions and optional user input."""

    round_number: int
    gaps: list[str] = Field(default_factory=list)
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    answer: str | None = None


class ClarifiedRequirements(BaseModel):
    """Structured requirements used for downstream artifact generation."""

    title: str
    original_request: str
    requirement_summary: str
    template_slug: str
    template_version: str
    target_stack: str
    roles: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    pages: list[str] = Field(default_factory=list)
    apis: list[str] = Field(default_factory=list)
    state_machine: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    supplemental_notes: list[str] = Field(default_factory=list)
    requested_capabilities: list[str] = Field(default_factory=list)
    features: dict[str, bool] = Field(default_factory=dict)
    rounds: list[ClarificationRound] = Field(default_factory=list)
    completeness_score: float = 0.0
    is_complete: bool = False


class TaskDraft(BaseModel):
    """Deterministic task draft emitted by Architect."""

    task_key: str
    title: str
    description: str
    priority: int
    sequence: int
    details: dict[str, Any] = Field(default_factory=dict)


class ArchitectArtifactDraftBundle(BaseModel):
    """LLM-polished artifact drafts for the architect stage."""

    clarification_notes_markdown: str
    spec_markdown: str
    plan_markdown: str
    research_markdown: str


class ArchitectRunResult(BaseModel):
    """Returned summary after Architect finishes Sprint 4 scope."""

    run_id: str
    current_phase: RunPhase
    clarification: ClarifiedRequirements
    artifact_versions: dict[str, int] = Field(default_factory=dict)
    task_items: list[TaskDraft] = Field(default_factory=list)
