from __future__ import annotations

from typing import Any

from specflow.mcp import build_default_mcp_server


def test_template_tools_search_list_and_get_content(sprint2_env: dict[str, Any]) -> None:
    run_state_manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]
    run = run_state_manager.create_run(
        project_id=project_id,
        input_prompt="Search template assets.",
    )
    server = build_default_mcp_server(
        settings=sprint2_env["settings"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=run_state_manager,
    )

    listed = server.invoke("template_tools.list_available_templates", run_id=run.run_id)
    searched = server.invoke(
        "template_tools.search_templates",
        run_id=run.run_id,
        arguments={"query": "ticket api"},
    )
    content = server.invoke(
        "template_tools.get_template_content",
        run_id=run.run_id,
        arguments={"key": "api/tickets_router.py"},
    )

    assert any(item["key"] == "api/tickets_router.py" for item in listed.output["templates"])
    assert searched.output["matches"][0]["key"] == "api/tickets_router.py"
    assert "APIRouter" in content.output["content"]
