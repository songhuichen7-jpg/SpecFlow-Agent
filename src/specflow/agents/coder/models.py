from __future__ import annotations

from pydantic import BaseModel, Field

from specflow.models import RunPhase


class QualityGateResult(BaseModel):
    """Normalized quality gate result emitted by the Coder agent."""

    name: str
    path: str
    success: bool
    command: list[str] = Field(default_factory=list)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class CoderRunResult(BaseModel):
    """High-level summary after code materialization or fix-up."""

    run_id: str
    current_phase: RunPhase
    written_files: list[str] = Field(default_factory=list)
    quality_gates: dict[str, QualityGateResult] = Field(default_factory=dict)
    artifact_versions: dict[str, int] = Field(default_factory=dict)
