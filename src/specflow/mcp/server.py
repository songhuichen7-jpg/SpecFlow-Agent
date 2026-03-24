from __future__ import annotations

from typing import Any

from specflow.config import Settings, get_settings
from specflow.mcp.errors import (
    MCPError,
    PermissionDeniedError,
    ToolExecutionError,
    ToolNotFoundError,
)
from specflow.mcp.types import (
    MCPToolDefinition,
    MCPToolRequest,
    MCPToolResult,
    PermissionPolicy,
    ToolContext,
    ToolPermission,
)
from specflow.models import ExecutionEventType
from specflow.storage import ArtifactRepository, RunStateManager
from specflow.templates import TemplateLibrary, get_default_template_library


class MCPServer:
    """Minimal MCP server skeleton with registry, routing, and permission checks."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        artifact_repository: ArtifactRepository | None = None,
        run_state_manager: RunStateManager | None = None,
        template_library: TemplateLibrary | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_directories()
        self.artifact_repository = artifact_repository or ArtifactRepository(settings=self.settings)
        self.run_state_manager = run_state_manager or RunStateManager(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )
        self.template_library = template_library or get_default_template_library()
        self._tools: dict[str, MCPToolDefinition] = {}

    def register_tool(self, definition: MCPToolDefinition) -> None:
        self._tools[definition.full_name] = definition

    def register_tools(self, definitions: list[MCPToolDefinition]) -> None:
        for definition in definitions:
            self.register_tool(definition)

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": definition.name,
                "full_name": definition.full_name,
                "group": definition.group.value,
                "description": definition.description,
                "permission": definition.permission.value,
                "input_schema": definition.input_schema,
            }
            for definition in sorted(self._tools.values(), key=lambda tool: tool.full_name)
        ]

    def create_context(
        self,
        run_id: str,
        *,
        permission_policy: PermissionPolicy | None = None,
    ) -> ToolContext:
        return ToolContext(
            run_id=run_id,
            settings=self.settings,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
            template_library=self.template_library,
            permission_policy=permission_policy or PermissionPolicy(),
        )

    def invoke(
        self,
        tool_name: str,
        *,
        run_id: str,
        arguments: dict[str, Any] | None = None,
        permission_policy: PermissionPolicy | None = None,
    ) -> MCPToolResult:
        request = MCPToolRequest(
            tool_name=tool_name,
            run_id=run_id,
            arguments=arguments or {},
            permission_policy=permission_policy or PermissionPolicy(),
        )
        return self.handle_request(request)

    def handle_request(self, request: MCPToolRequest) -> MCPToolResult:
        definition = self._resolve_tool(request.tool_name)
        self._validate_permission(definition.permission, request.permission_policy)
        context = self.create_context(
            request.run_id,
            permission_policy=request.permission_policy,
        )
        try:
            output = definition.handler(context, **request.arguments)
        except (MCPError, PermissionDeniedError, ToolNotFoundError):
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Tool {definition.full_name!r} failed: {exc}") from exc

        self.run_state_manager.record_event(
            request.run_id,
            event_type=ExecutionEventType.TOOL_CALLED,
            message=f"Executed {definition.full_name}.",
            payload={"arguments": request.arguments, "tool": definition.full_name},
        )
        return MCPToolResult(
            tool_name=definition.full_name,
            group=definition.group,
            success=True,
            output=output,
            metadata={"permission": definition.permission.value},
        )

    def _resolve_tool(self, tool_name: str) -> MCPToolDefinition:
        if tool_name in self._tools:
            return self._tools[tool_name]
        matches = [
            tool for full_name, tool in self._tools.items() if full_name.endswith(f".{tool_name}")
        ]
        if len(matches) == 1:
            return matches[0]
        raise ToolNotFoundError(f"Unknown MCP tool: {tool_name}")

    def _validate_permission(
        self,
        permission: ToolPermission,
        policy: PermissionPolicy,
    ) -> None:
        if not policy.allows(permission):
            raise PermissionDeniedError(
                f"Tool requires {permission.value} permission, but the policy denied it."
            )
