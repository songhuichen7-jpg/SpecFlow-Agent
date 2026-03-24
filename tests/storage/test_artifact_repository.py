from __future__ import annotations

from typing import Any

import pytest

from specflow.models import ArtifactKind
from specflow.storage import ArtifactRepository


def test_artifact_repository_versions_and_loads(sprint2_env: dict[str, Any]) -> None:
    repository = sprint2_env["artifact_repository"]
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]

    assert isinstance(repository, ArtifactRepository)
    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Build the specification artifacts.",
    )

    first = repository.save_artifact(
        run.run_id,
        name="spec.md",
        content="# Spec v1",
        kind=ArtifactKind.SPEC,
    )
    second = repository.save_artifact(
        run.run_id,
        name="spec.md",
        content="# Spec v2",
        kind=ArtifactKind.SPEC,
        is_frozen=True,
    )
    hidden = repository.save_artifact(
        run.run_id,
        name=".specify/memory/constitution.md",
        content="Constitution text",
        kind=ArtifactKind.CONSTITUTION,
    )

    latest = repository.load_artifact(run.run_id, name="spec.md")
    original = repository.load_artifact(run.run_id, name="spec.md", version=1)
    listed = repository.list_artifacts(run.run_id)

    assert first.version == 1
    assert second.version == 2
    assert second.is_frozen is True
    assert latest.content == "# Spec v2"
    assert original.content == "# Spec v1"
    assert latest.canonical_path.read_text(encoding="utf-8") == "# Spec v2"
    assert ".versions/spec.v2.md" in latest.version_path.as_posix()
    assert hidden.name == ".specify/memory/constitution.md"
    assert {artifact.name for artifact in listed} == {
        "spec.md",
        ".specify/memory/constitution.md",
    }


def test_artifact_repository_rejects_directory_traversal(sprint2_env: dict[str, Any]) -> None:
    repository = sprint2_env["artifact_repository"]
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]

    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Build the specification artifacts.",
    )

    with pytest.raises(ValueError):
        repository.save_artifact(
            run.run_id,
            name="../escape.md",
            content="nope",
            kind=ArtifactKind.SPEC,
        )
