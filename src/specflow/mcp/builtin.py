from __future__ import annotations

from specflow.config import Settings
from specflow.mcp.server import MCPServer
from specflow.mcp.tools import (
    check_types,
    create_project_skeleton,
    delete_file,
    export_spec_summary,
    get_template_content,
    init_git_repo,
    list_available_templates,
    list_directory,
    read_file,
    read_spec,
    run_build,
    run_lint,
    run_tests,
    search_templates,
    validate_spec_completeness,
    write_file,
)
from specflow.mcp.types import MCPToolDefinition, ToolGroup, ToolPermission
from specflow.storage import ArtifactRepository, RunStateManager
from specflow.templates import TemplateLibrary


def default_tool_definitions() -> list[MCPToolDefinition]:
    return [
        MCPToolDefinition(
            name="create_project_skeleton",
            group=ToolGroup.SCAFFOLD_TOOLS,
            description="Create a starter project skeleton inside the run workspace.",
            permission=ToolPermission.WRITE,
            handler=create_project_skeleton,
            input_schema={"template_slug": "str", "overwrite": "bool"},
        ),
        MCPToolDefinition(
            name="init_git_repo",
            group=ToolGroup.SCAFFOLD_TOOLS,
            description="Initialize a git repository in the run workspace.",
            permission=ToolPermission.EXECUTE,
            handler=init_git_repo,
            input_schema={"initial_branch": "str", "write_gitignore": "bool"},
        ),
        MCPToolDefinition(
            name="search_templates",
            group=ToolGroup.TEMPLATE_TOOLS,
            description="Search the template catalog by query or category.",
            permission=ToolPermission.READ,
            handler=search_templates,
            input_schema={"query": "str | None", "category": "str | None"},
        ),
        MCPToolDefinition(
            name="get_template_content",
            group=ToolGroup.TEMPLATE_TOOLS,
            description="Return the full content for a named template asset.",
            permission=ToolPermission.READ,
            handler=get_template_content,
            input_schema={"key": "str"},
        ),
        MCPToolDefinition(
            name="list_available_templates",
            group=ToolGroup.TEMPLATE_TOOLS,
            description="List all available templates in the catalog.",
            permission=ToolPermission.READ,
            handler=list_available_templates,
            input_schema={"category": "str | None"},
        ),
        MCPToolDefinition(
            name="read_file",
            group=ToolGroup.WORKSPACE_TOOLS,
            description="Read a file from the run workspace sandbox.",
            permission=ToolPermission.READ,
            handler=read_file,
            input_schema={"path": "str"},
        ),
        MCPToolDefinition(
            name="write_file",
            group=ToolGroup.WORKSPACE_TOOLS,
            description="Write a file inside the run workspace sandbox.",
            permission=ToolPermission.WRITE,
            handler=write_file,
            input_schema={"path": "str", "content": "str", "overwrite": "bool"},
        ),
        MCPToolDefinition(
            name="list_directory",
            group=ToolGroup.WORKSPACE_TOOLS,
            description="List files and directories inside the workspace sandbox.",
            permission=ToolPermission.READ,
            handler=list_directory,
            input_schema={"path": "str"},
        ),
        MCPToolDefinition(
            name="delete_file",
            group=ToolGroup.WORKSPACE_TOOLS,
            description="Delete a file or directory from the workspace sandbox.",
            permission=ToolPermission.DELETE,
            handler=delete_file,
            input_schema={"path": "str", "recursive": "bool"},
        ),
        MCPToolDefinition(
            name="run_lint",
            group=ToolGroup.QUALITY_TOOLS,
            description="Run lint checks for a workspace subdirectory.",
            permission=ToolPermission.EXECUTE,
            handler=run_lint,
            input_schema={"path": "str", "command": "list[str] | None"},
        ),
        MCPToolDefinition(
            name="run_tests",
            group=ToolGroup.QUALITY_TOOLS,
            description="Run tests for a workspace subdirectory.",
            permission=ToolPermission.EXECUTE,
            handler=run_tests,
            input_schema={"path": "str", "command": "list[str] | None"},
        ),
        MCPToolDefinition(
            name="run_build",
            group=ToolGroup.QUALITY_TOOLS,
            description="Run a build or compilation check for a workspace subdirectory.",
            permission=ToolPermission.EXECUTE,
            handler=run_build,
            input_schema={"path": "str", "command": "list[str] | None"},
        ),
        MCPToolDefinition(
            name="check_types",
            group=ToolGroup.QUALITY_TOOLS,
            description="Run type checks for a workspace subdirectory.",
            permission=ToolPermission.EXECUTE,
            handler=check_types,
            input_schema={"path": "str", "command": "list[str] | None"},
        ),
        MCPToolDefinition(
            name="read_spec",
            group=ToolGroup.SPEC_TOOLS,
            description="Read a spec artifact saved in the artifact repository.",
            permission=ToolPermission.READ,
            handler=read_spec,
            input_schema={"artifact_name": "str"},
        ),
        MCPToolDefinition(
            name="export_spec_summary",
            group=ToolGroup.SPEC_TOOLS,
            description="Summarize available spec artifacts and extracted headings.",
            permission=ToolPermission.READ,
            handler=export_spec_summary,
            input_schema={"artifact_names": "list[str] | None"},
        ),
        MCPToolDefinition(
            name="validate_spec_completeness",
            group=ToolGroup.SPEC_TOOLS,
            description="Validate whether the required spec artifacts are present.",
            permission=ToolPermission.READ,
            handler=validate_spec_completeness,
            input_schema={"required_artifacts": "list[str] | None", "require_contracts": "bool"},
        ),
    ]


def build_default_mcp_server(
    *,
    settings: Settings | None = None,
    artifact_repository: ArtifactRepository | None = None,
    run_state_manager: RunStateManager | None = None,
    template_library: TemplateLibrary | None = None,
) -> MCPServer:
    server = MCPServer(
        settings=settings,
        artifact_repository=artifact_repository,
        run_state_manager=run_state_manager,
        template_library=template_library,
    )
    server.register_tools(default_tool_definitions())
    return server
