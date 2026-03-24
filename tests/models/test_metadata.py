from __future__ import annotations

from sqlalchemy import create_engine, inspect

from specflow.models import Base


def test_metadata_includes_sprint_one_tables() -> None:
    expected_tables = {
        "artifact",
        "execution_event",
        "project",
        "review_issue",
        "run",
        "task_item",
        "template_profile",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_models_create_successfully_on_sqlite() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) == {
        "artifact",
        "execution_event",
        "project",
        "review_issue",
        "run",
        "task_item",
        "template_profile",
    }
