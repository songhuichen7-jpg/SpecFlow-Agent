from __future__ import annotations

from pydantic import BaseModel, Field

from specflow.models import ReviewSeverity, RunPhase


class ReviewerFinding(BaseModel):
    """Structured reviewer issue derived from spec-to-code comparisons."""

    title: str
    description: str
    severity: ReviewSeverity
    spec_reference: str | None = None
    code_reference: str | None = None
    suggested_fix: str | None = None


class ReviewNarrativeBundle(BaseModel):
    """LLM-polished reviewer narrative sections."""

    verdict_summary: str
    next_steps_markdown: str
    risk_note: str | None = None


class ReviewRunResult(BaseModel):
    """High-level review outcome for a generated workspace."""

    run_id: str
    current_phase: RunPhase
    approved: bool
    blocking: bool
    report_version: int
    issues: list[ReviewerFinding] = Field(default_factory=list)
    quality_checks: dict[str, bool] = Field(default_factory=dict)
