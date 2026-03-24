from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from specflow.config import Settings, reset_settings_cache
from specflow.models import Base, Project, TemplateType
from specflow.storage import ArtifactRepository, CheckpointManager, RunStateManager
from specflow.storage.db.session import reset_database_cache


@pytest.fixture(autouse=True)
def reset_singletons() -> Generator[None, None, None]:
    reset_settings_cache()
    reset_database_cache()
    yield
    reset_settings_cache()
    reset_database_cache()


@pytest.fixture
def sprint2_env(tmp_path: Path) -> Generator[dict[str, object], None, None]:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'specflow.db'}",
        workspace_root=tmp_path / "runs",
        data_root=tmp_path / ".specflow",
        checkpoint_backend="sqlite",
        store_backend="sqlite",
    )
    settings.ensure_runtime_directories()

    engine = create_engine(settings.resolved_database_url, future=True)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )
    Base.metadata.create_all(engine)

    with session_factory() as session:
        project = Project(
            id=str(uuid4()),
            name="Sprint Test Project",
            slug="sprint-test-project",
            template_type=TemplateType.TICKET_SYSTEM,
            target_stack="fastapi-react-vite-typescript-postgresql",
            description="Project used for storage and MCP tests.",
        )
        session.add(project)
        session.commit()
        project_id = project.id

    artifact_repository = ArtifactRepository(
        session_factory=session_factory,
        settings=settings,
    )
    run_state_manager = RunStateManager(
        session_factory=session_factory,
        settings=settings,
        artifact_repository=artifact_repository,
    )
    checkpoint_manager = CheckpointManager(
        settings=settings,
        artifact_repository=artifact_repository,
        run_state_manager=run_state_manager,
    )

    yield {
        "settings": settings,
        "engine": engine,
        "session_factory": session_factory,
        "project_id": project_id,
        "artifact_repository": artifact_repository,
        "run_state_manager": run_state_manager,
        "checkpoint_manager": checkpoint_manager,
    }

    engine.dispose()
