from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore
from langgraph.store.sqlite import SqliteStore

from specflow.config import Settings, get_settings
from specflow.models import ArtifactFormat, ArtifactKind, ExecutionEventType, RunPhase
from specflow.storage.artifacts import ArtifactRepository
from specflow.storage.runtime import RunStateManager
from specflow.storage.types import StorageBucket


@dataclass(frozen=True)
class PhaseCheckpoint:
    """A materialized phase checkpoint loaded from the artifact store."""

    artifact_id: str
    run_id: str
    phase: RunPhase
    version: int
    state: dict[str, Any]
    metadata: dict[str, Any]


class CheckpointManager:
    """Bridge LangGraph persistence, Deep Agents backends, and phase snapshots."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        artifact_repository: ArtifactRepository | None = None,
        run_state_manager: RunStateManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_directories()
        self.artifact_repository = artifact_repository or ArtifactRepository(settings=self.settings)
        self.run_state_manager = run_state_manager or RunStateManager(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )

    def thread_config(self, run_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": run_id}}

    @contextmanager
    def open_checkpointer(self) -> Iterator[BaseCheckpointSaver]:
        backend = self.settings.checkpoint_backend
        if backend == "memory":
            yield InMemorySaver()
            return
        if backend == "sqlite":
            with SqliteSaver.from_conn_string(str(self.settings.checkpoint_path)) as saver:
                saver.setup()
                yield saver
            return
        if self.settings.checkpoint_url is None:
            raise ValueError("SPECFLOW_CHECKPOINT_URL is required for postgres checkpoint backend.")
        with PostgresSaver.from_conn_string(self.settings.checkpoint_url) as saver:
            saver.setup()
            yield saver

    @contextmanager
    def open_store(self) -> Iterator[BaseStore]:
        backend = self.settings.store_backend
        if backend == "memory":
            yield InMemoryStore()
            return
        if backend == "sqlite":
            with SqliteStore.from_conn_string(str(self.settings.store_path)) as store:
                store.setup()
                yield store
            return
        if self.settings.store_url is None:
            raise ValueError("SPECFLOW_STORE_URL is required for postgres store backend.")
        with PostgresStore.from_conn_string(self.settings.store_url) as store:
            store.setup()
            yield store

    def create_backend_factory(self) -> Callable[[Any], CompositeBackend]:
        route = self.settings.persistent_memory_route

        def namespace(context: Any) -> tuple[str, ...]:
            runtime_config = getattr(context.runtime, "config", {})
            configurable = (
                runtime_config.get("configurable", {}) if isinstance(runtime_config, dict) else {}
            )
            thread_id = str(configurable.get("thread_id", "default"))
            return ("specflow", "runs", thread_id, "memory")

        def factory(runtime: Any) -> CompositeBackend:
            return CompositeBackend(
                default=StateBackend(runtime),
                routes={
                    route: StoreBackend(runtime, namespace=namespace),
                },
            )

        return factory

    def save_phase_checkpoint(
        self,
        run_id: str,
        *,
        phase: RunPhase,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> PhaseCheckpoint:
        checkpoint_metadata = {
            "saved_at": datetime.now(UTC).isoformat(),
            **(metadata or {}),
        }
        payload = {
            "run_id": run_id,
            "phase": phase.value,
            "state": state,
            "metadata": checkpoint_metadata,
        }
        stored = self.artifact_repository.save_artifact(
            run_id,
            name=f"checkpoints/{phase.value}.json",
            content=payload,
            kind=ArtifactKind.CHECKPOINT,
            artifact_format=ArtifactFormat.JSON,
            bucket=StorageBucket.ARTIFACTS,
            details={
                "phase": phase.value,
                "checkpoint_type": "phase",
                "saved_at": checkpoint_metadata["saved_at"],
            },
        )
        self.run_state_manager.record_event(
            run_id,
            event_type=ExecutionEventType.CHECKPOINT_SAVED,
            message=f"Saved checkpoint for {phase.value}.",
            phase=phase,
            payload={"artifact_id": stored.artifact_id, "version": stored.version},
        )
        return self._to_phase_checkpoint(stored.content, stored.artifact_id, run_id, stored.version)

    def load_phase_checkpoint(
        self,
        run_id: str,
        *,
        phase: RunPhase,
        version: int | None = None,
    ) -> PhaseCheckpoint:
        stored = self.artifact_repository.load_artifact(
            run_id,
            name=f"checkpoints/{phase.value}.json",
            version=version,
        )
        checkpoint = self._to_phase_checkpoint(
            stored.content, stored.artifact_id, run_id, stored.version
        )
        self.run_state_manager.record_event(
            run_id,
            event_type=ExecutionEventType.CHECKPOINT_RESTORED,
            message=f"Restored checkpoint for {phase.value}.",
            phase=phase,
            payload={"artifact_id": stored.artifact_id, "version": stored.version},
        )
        return checkpoint

    def load_latest_checkpoint(self, run_id: str) -> PhaseCheckpoint:
        checkpoints = self.artifact_repository.list_artifacts(
            run_id,
            kind=ArtifactKind.CHECKPOINT,
            latest_only=False,
        )
        if not checkpoints:
            raise LookupError(f"No checkpoints found for run {run_id!r}.")
        latest = max(
            checkpoints,
            key=lambda artifact: (
                str(artifact.details.get("saved_at", "")),
                artifact.version,
            ),
        )
        checkpoint = self._to_phase_checkpoint(
            latest.content, latest.artifact_id, run_id, latest.version
        )
        self.run_state_manager.record_event(
            run_id,
            event_type=ExecutionEventType.CHECKPOINT_RESTORED,
            message=f"Restored latest checkpoint for {checkpoint.phase.value}.",
            phase=checkpoint.phase,
            payload={"artifact_id": latest.artifact_id, "version": latest.version},
        )
        return checkpoint

    def resume_from_latest_phase(self, run_id: str) -> PhaseCheckpoint:
        return self.load_latest_checkpoint(run_id)

    def _to_phase_checkpoint(
        self,
        raw_content: str,
        artifact_id: str,
        run_id: str,
        version: int,
    ) -> PhaseCheckpoint:
        payload = json.loads(raw_content)
        return PhaseCheckpoint(
            artifact_id=artifact_id,
            run_id=run_id,
            phase=RunPhase(payload["phase"]),
            version=version,
            state=dict(payload["state"]),
            metadata=dict(payload.get("metadata", {})),
        )
