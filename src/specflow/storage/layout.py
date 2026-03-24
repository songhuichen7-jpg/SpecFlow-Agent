from __future__ import annotations

from pathlib import Path

from specflow.storage.types import RunLayout, StorageBucket


def build_run_layout(workspace_root: Path, run_id: str) -> RunLayout:
    """Return the standard directory layout for a run."""
    root = workspace_root / run_id
    return RunLayout(
        run_id=run_id,
        root=root,
        artifacts_dir=root / StorageBucket.ARTIFACTS.value,
        workspace_dir=root / StorageBucket.WORKSPACE.value,
        reports_dir=root / StorageBucket.REPORTS.value,
    )


def ensure_run_layout(workspace_root: Path, run_id: str) -> RunLayout:
    """Create the run directory structure if it does not already exist."""
    layout = build_run_layout(workspace_root, run_id)
    layout.artifacts_dir.mkdir(parents=True, exist_ok=True)
    layout.workspace_dir.mkdir(parents=True, exist_ok=True)
    layout.reports_dir.mkdir(parents=True, exist_ok=True)
    return layout
