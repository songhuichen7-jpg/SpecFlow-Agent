"""Storage primitives and repositories."""

from __future__ import annotations

from typing import Any

from specflow.storage.db import Base, create_session, get_engine, get_session_factory, session_scope

__all__ = [
    "ArtifactNotFoundError",
    "ArtifactRepository",
    "Base",
    "CheckpointManager",
    "InvalidPhaseTransitionError",
    "PhaseCheckpoint",
    "RunLayout",
    "RunNotFoundError",
    "RunStateManager",
    "RunStateSnapshot",
    "StorageBucket",
    "create_session",
    "get_engine",
    "get_session_factory",
    "session_scope",
]


def __getattr__(name: str) -> Any:
    if name in {"ArtifactNotFoundError", "ArtifactRepository"}:
        from specflow.storage.artifacts import ArtifactNotFoundError, ArtifactRepository

        exports = {
            "ArtifactNotFoundError": ArtifactNotFoundError,
            "ArtifactRepository": ArtifactRepository,
        }
        return exports[name]
    if name in {"CheckpointManager", "PhaseCheckpoint"}:
        from specflow.storage.checkpoints import CheckpointManager, PhaseCheckpoint

        exports = {
            "CheckpointManager": CheckpointManager,
            "PhaseCheckpoint": PhaseCheckpoint,
        }
        return exports[name]
    if name in {
        "InvalidPhaseTransitionError",
        "RunNotFoundError",
        "RunStateManager",
        "RunStateSnapshot",
    }:
        from specflow.storage.runtime import (
            InvalidPhaseTransitionError,
            RunNotFoundError,
            RunStateManager,
        )
        from specflow.storage.types import RunStateSnapshot

        exports = {
            "InvalidPhaseTransitionError": InvalidPhaseTransitionError,
            "RunNotFoundError": RunNotFoundError,
            "RunStateManager": RunStateManager,
            "RunStateSnapshot": RunStateSnapshot,
        }
        return exports[name]
    if name in {"RunLayout", "StorageBucket"}:
        from specflow.storage.types import RunLayout, StorageBucket

        exports = {
            "RunLayout": RunLayout,
            "StorageBucket": StorageBucket,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
