from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from specflow.config import Settings, get_settings
from specflow.models import Artifact, ArtifactFormat, ArtifactKind
from specflow.storage.db import get_session_factory, session_scope
from specflow.storage.layout import build_run_layout, ensure_run_layout
from specflow.storage.types import RunLayout, StorageBucket, StoredArtifact


class ArtifactNotFoundError(LookupError):
    """Raised when an artifact or version cannot be found."""


class ArtifactRepository:
    """Persist and retrieve run-scoped artifacts on disk and in the database."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_directories()
        self.session_factory = session_factory or get_session_factory()

    def ensure_run_layout(self, run_id: str) -> RunLayout:
        return ensure_run_layout(self.settings.workspace_root, run_id)

    def get_run_layout(self, run_id: str) -> RunLayout:
        return build_run_layout(self.settings.workspace_root, run_id)

    def save_artifact(
        self,
        run_id: str,
        name: str,
        content: str | dict[str, Any] | list[Any],
        *,
        kind: ArtifactKind,
        artifact_format: ArtifactFormat | None = None,
        bucket: StorageBucket = StorageBucket.ARTIFACTS,
        mime_type: str | None = None,
        is_frozen: bool = False,
        details: dict[str, Any] | None = None,
    ) -> StoredArtifact:
        layout = self.ensure_run_layout(run_id)
        logical_path = self._normalize_relative_path(name)
        content_text, resolved_format = self._serialize_content(
            content, artifact_format, logical_path
        )

        with session_scope(self.session_factory) as session:
            version = self._next_version(session, run_id, logical_path)
            version_path, canonical_path = self._materialize_paths(
                layout=layout,
                logical_path=logical_path,
                bucket=bucket,
                version=version,
            )
            version_path.parent.mkdir(parents=True, exist_ok=True)
            canonical_path.parent.mkdir(parents=True, exist_ok=True)
            version_path.write_text(content_text, encoding="utf-8")
            canonical_path.write_text(content_text, encoding="utf-8")

            artifact = Artifact(
                run_id=run_id,
                name=logical_path,
                kind=kind,
                path=self._relative_to_run_root(layout.root, version_path),
                artifact_format=resolved_format,
                mime_type=mime_type,
                version=version,
                is_frozen=is_frozen,
                details={
                    "bucket": bucket.value,
                    "canonical_path": self._relative_to_run_root(layout.root, canonical_path),
                    "logical_path": logical_path,
                    **(details or {}),
                },
                content_hash=sha256(content_text.encode("utf-8")).hexdigest(),
            )
            session.add(artifact)
            session.flush()
            return self._to_stored_artifact(artifact, layout.root, content_text)

    def load_artifact(
        self,
        run_id: str,
        *,
        artifact_id: str | None = None,
        name: str | None = None,
        version: int | None = None,
    ) -> StoredArtifact:
        layout = self.get_run_layout(run_id)

        with session_scope(self.session_factory) as session:
            artifact = self._select_artifact(
                session=session,
                run_id=run_id,
                artifact_id=artifact_id,
                name=name,
                version=version,
            )
            content = (layout.root / artifact.path).read_text(encoding="utf-8")
            return self._to_stored_artifact(artifact, layout.root, content)

    def list_artifacts(
        self,
        run_id: str,
        *,
        kind: ArtifactKind | None = None,
        latest_only: bool = True,
    ) -> list[StoredArtifact]:
        layout = self.get_run_layout(run_id)

        with session_scope(self.session_factory) as session:
            statement = select(Artifact).where(Artifact.run_id == run_id)
            if kind is not None:
                statement = statement.where(Artifact.kind == kind)
            statement = statement.order_by(
                Artifact.name.asc(), Artifact.version.desc(), Artifact.created_at.desc()
            )

            artifacts = list(session.scalars(statement))
            if latest_only:
                latest_by_name: dict[str, Artifact] = {}
                for artifact in artifacts:
                    latest_by_name.setdefault(artifact.name, artifact)
                artifacts = list(latest_by_name.values())

            return [
                self._to_stored_artifact(
                    artifact,
                    layout.root,
                    (layout.root / artifact.path).read_text(encoding="utf-8"),
                )
                for artifact in artifacts
            ]

    def _next_version(self, session: Session, run_id: str, logical_path: str) -> int:
        statement = (
            select(Artifact)
            .where(Artifact.run_id == run_id, Artifact.name == logical_path)
            .order_by(Artifact.version.desc())
            .limit(1)
        )
        current = session.scalar(statement)
        return 1 if current is None else current.version + 1

    def _select_artifact(
        self,
        *,
        session: Session,
        run_id: str,
        artifact_id: str | None,
        name: str | None,
        version: int | None,
    ) -> Artifact:
        statement = select(Artifact).where(Artifact.run_id == run_id)
        if artifact_id is not None:
            statement = statement.where(Artifact.id == artifact_id)
        elif name is not None:
            statement = statement.where(Artifact.name == self._normalize_relative_path(name))
            if version is not None:
                statement = statement.where(Artifact.version == version)
            else:
                statement = statement.order_by(Artifact.version.desc()).limit(1)
        else:
            raise ValueError("Either artifact_id or name must be provided.")

        artifact = session.scalar(statement)
        if artifact is None:
            raise ArtifactNotFoundError(f"Artifact not found for run_id={run_id!r}.")
        return artifact

    def _materialize_paths(
        self,
        *,
        layout: RunLayout,
        logical_path: str,
        bucket: StorageBucket,
        version: int,
    ) -> tuple[Path, Path]:
        bucket_root = self._bucket_root(layout, bucket)
        logical = Path(logical_path)
        version_name = f"{logical.stem}.v{version}{logical.suffix}"
        version_path = bucket_root / ".versions" / logical.parent / version_name
        canonical_path = self._resolve_within_root(bucket_root, logical_path)
        return version_path, canonical_path

    def _bucket_root(self, layout: RunLayout, bucket: StorageBucket) -> Path:
        if bucket is StorageBucket.ARTIFACTS:
            return layout.artifacts_dir
        if bucket is StorageBucket.REPORTS:
            return layout.reports_dir
        return layout.workspace_dir

    def _normalize_relative_path(self, value: str) -> str:
        path = Path(value)
        if path.is_absolute():
            raise ValueError("Artifact names must be relative paths inside the run directory.")
        normalized = path.as_posix()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        if normalized in {"", "."}:
            raise ValueError("Artifact name cannot be empty.")
        parts = Path(normalized).parts
        if ".." in parts:
            raise ValueError("Artifact path cannot escape the run directory.")
        return normalized

    def _resolve_within_root(self, root: Path, relative_path: str) -> Path:
        resolved_root = root.resolve()
        resolved_path = (root / relative_path).resolve()
        resolved_path.relative_to(resolved_root)
        return resolved_path

    def _relative_to_run_root(self, run_root: Path, path: Path) -> str:
        return path.resolve().relative_to(run_root.resolve()).as_posix()

    def _serialize_content(
        self,
        content: str | dict[str, Any] | list[Any],
        artifact_format: ArtifactFormat | None,
        logical_path: str,
    ) -> tuple[str, ArtifactFormat]:
        if isinstance(content, str):
            resolved_format = artifact_format or self._infer_format(logical_path)
            return content, resolved_format
        resolved_format = artifact_format or ArtifactFormat.JSON
        return json.dumps(content, indent=2, ensure_ascii=True, sort_keys=True), resolved_format

    def _infer_format(self, logical_path: str) -> ArtifactFormat:
        suffix = Path(logical_path).suffix.lower()
        if suffix == ".md":
            return ArtifactFormat.MARKDOWN
        if suffix in {".yaml", ".yml"}:
            return ArtifactFormat.YAML
        if suffix == ".json":
            return ArtifactFormat.JSON
        if suffix == ".html":
            return ArtifactFormat.HTML
        return ArtifactFormat.TEXT

    def _to_stored_artifact(
        self, artifact: Artifact, run_root: Path, content: str
    ) -> StoredArtifact:
        canonical_path = run_root / str(artifact.details.get("canonical_path", artifact.path))
        version_path = run_root / artifact.path
        return StoredArtifact(
            artifact_id=artifact.id,
            run_id=artifact.run_id,
            name=artifact.name,
            kind=artifact.kind,
            artifact_format=artifact.artifact_format,
            version=artifact.version,
            is_frozen=artifact.is_frozen,
            mime_type=artifact.mime_type,
            path=artifact.path,
            canonical_path=canonical_path,
            version_path=version_path,
            details=dict(artifact.details),
            content_hash=artifact.content_hash,
            created_at=artifact.created_at,
            updated_at=artifact.updated_at,
            content=content,
        )
