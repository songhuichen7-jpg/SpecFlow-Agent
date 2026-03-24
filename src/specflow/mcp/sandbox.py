from __future__ import annotations

import shutil
from pathlib import Path

from specflow.config import Settings, get_settings
from specflow.mcp.errors import SandboxViolationError
from specflow.mcp.types import DirectoryEntry
from specflow.storage.artifacts import ArtifactRepository


class WorkspaceSandbox:
    """Run-scoped sandbox that constrains file operations to the workspace tree."""

    def __init__(
        self,
        run_id: str,
        *,
        settings: Settings | None = None,
        artifact_repository: ArtifactRepository | None = None,
    ) -> None:
        self.run_id = run_id
        self.settings = settings or get_settings()
        self.artifact_repository = artifact_repository or ArtifactRepository(settings=self.settings)
        self.layout = self.artifact_repository.ensure_run_layout(run_id)

    @property
    def root(self) -> Path:
        return self.layout.workspace_dir

    def resolve(self, relative_path: str = ".") -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as exc:
            raise SandboxViolationError(
                f"Path {relative_path!r} escapes the workspace sandbox for run {self.run_id!r}."
            ) from exc
        return resolved

    def read_file(self, path: str) -> str:
        return self.resolve(path).read_text(encoding="utf-8")

    def write_file(
        self,
        path: str,
        content: str,
        *,
        overwrite: bool = True,
        create_parents: bool = True,
    ) -> Path:
        target = self.resolve(path)
        if target.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {path}")
        if create_parents:
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def list_directory(self, path: str = ".") -> list[DirectoryEntry]:
        directory = self.resolve(path)
        if not directory.is_dir():
            raise NotADirectoryError(path)
        entries = [
            DirectoryEntry(
                path=item.relative_to(self.root).as_posix(),
                is_dir=item.is_dir(),
                size=0 if item.is_dir() else item.stat().st_size,
            )
            for item in sorted(directory.iterdir(), key=lambda child: child.name)
        ]
        return entries

    def delete_path(self, path: str, *, recursive: bool = False) -> None:
        target = self.resolve(path)
        if not target.exists():
            raise FileNotFoundError(path)
        if target.is_dir():
            if not recursive:
                raise IsADirectoryError(f"Directory deletion requires recursive=True: {path}")
            shutil.rmtree(target)
            return
        target.unlink()
