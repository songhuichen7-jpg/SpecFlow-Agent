from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from specflow.models.enums import ArtifactFormat, ArtifactKind, ExecutionMode, RunPhase, RunStatus


class StorageBucket(StrEnum):
    ARTIFACTS = "artifacts"
    REPORTS = "reports"
    WORKSPACE = "workspace"


@dataclass(frozen=True)
class RunLayout:
    """Filesystem layout for a single run workspace."""

    run_id: str
    root: Path
    artifacts_dir: Path
    workspace_dir: Path
    reports_dir: Path

    @property
    def checkpoints_dir(self) -> Path:
        return self.artifacts_dir / "checkpoints"


@dataclass(frozen=True)
class RunStateSnapshot:
    """Detached representation of persisted run state."""

    run_id: str
    project_id: str
    status: RunStatus
    current_phase: RunPhase
    mode: ExecutionMode
    input_prompt: str
    summary: str | None
    retry_count: int
    human_gate_pending: bool
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredArtifact:
    """Artifact metadata and loaded content."""

    artifact_id: str
    run_id: str
    name: str
    kind: ArtifactKind
    artifact_format: ArtifactFormat
    version: int
    is_frozen: bool
    mime_type: str | None
    path: str
    canonical_path: Path
    version_path: Path
    details: dict[str, Any]
    content_hash: str | None
    created_at: datetime
    updated_at: datetime
    content: str
