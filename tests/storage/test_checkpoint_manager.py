from __future__ import annotations

import operator
from types import SimpleNamespace
from typing import Annotated, Any, cast

from deepagents.backends import CompositeBackend
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore
from typing_extensions import TypedDict

from specflow.models import RunPhase
from specflow.storage import CheckpointManager


class MessageState(TypedDict):
    messages: Annotated[list[str], operator.add]


def append_checkpoint_message(state: MessageState) -> dict[str, list[str]]:
    return {"messages": ["checkpointed"]}


def test_checkpoint_manager_saves_and_restores_phase_snapshots(sprint2_env: dict[str, Any]) -> None:
    manager = sprint2_env["checkpoint_manager"]
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]

    assert isinstance(manager, CheckpointManager)
    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Checkpoint the current state.",
    )
    run = run_state_manager.transition_to_phase(run.run_id, RunPhase.SPECIFY)

    saved = manager.save_phase_checkpoint(
        run.run_id,
        phase=RunPhase.SPECIFY,
        state={"spec": "draft-1"},
        metadata={"source": "architect"},
    )
    restored = manager.load_phase_checkpoint(run.run_id, phase=RunPhase.SPECIFY)
    latest = manager.resume_from_latest_phase(run.run_id)

    assert saved.phase == RunPhase.SPECIFY
    assert restored.state == {"spec": "draft-1"}
    assert restored.metadata["source"] == "architect"
    assert "saved_at" in restored.metadata
    assert latest.artifact_id == saved.artifact_id


def test_checkpoint_manager_opens_persistent_store_and_checkpointer(
    sprint2_env: dict[str, Any],
) -> None:
    manager = sprint2_env["checkpoint_manager"]
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]

    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Resume graph execution.",
    )

    with manager.open_store() as store:
        store.put(("specflow", "tests"), "answer", {"value": 42})

    with manager.open_store() as store:
        restored = store.get(("specflow", "tests"), "answer")
        assert restored is not None
        assert restored.value["value"] == 42

    with manager.open_checkpointer() as saver:
        graph = (
            StateGraph(MessageState)
            .add_node("append", append_checkpoint_message)
            .add_edge(START, "append")
            .add_edge("append", END)
            .compile(checkpointer=saver)
        )
        config = cast(RunnableConfig, manager.thread_config(run.run_id))
        graph_runtime = cast(Any, graph)
        first = graph_runtime.invoke({"messages": ["hello"]}, config)
        second = graph_runtime.invoke({"messages": ["again"]}, config)

    assert first["messages"] == ["hello", "checkpointed"]
    assert second["messages"] == ["hello", "checkpointed", "again", "checkpointed"]


def test_checkpoint_manager_builds_deepagents_backend_factory(sprint2_env: dict[str, Any]) -> None:
    manager = sprint2_env["checkpoint_manager"]
    settings = sprint2_env["settings"]

    runtime = SimpleNamespace(
        store=InMemoryStore(),
        config={"configurable": {"thread_id": "run-123"}},
        state={},
    )
    backend = manager.create_backend_factory()(runtime)

    assert isinstance(backend, CompositeBackend)
    assert settings.persistent_memory_route in backend.routes
