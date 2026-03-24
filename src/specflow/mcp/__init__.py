"""MCP capability layer."""

from specflow.mcp.builtin import build_default_mcp_server, default_tool_definitions
from specflow.mcp.errors import (
    MCPError,
    PermissionDeniedError,
    SandboxViolationError,
    ToolExecutionError,
    ToolNotFoundError,
)
from specflow.mcp.sandbox import WorkspaceSandbox
from specflow.mcp.server import MCPServer
from specflow.mcp.types import (
    MCPToolDefinition,
    MCPToolRequest,
    MCPToolResult,
    PermissionPolicy,
    ToolContext,
    ToolGroup,
    ToolPermission,
)

__all__ = [
    "MCPError",
    "MCPServer",
    "MCPToolDefinition",
    "MCPToolRequest",
    "MCPToolResult",
    "PermissionDeniedError",
    "PermissionPolicy",
    "SandboxViolationError",
    "ToolContext",
    "ToolExecutionError",
    "ToolGroup",
    "ToolNotFoundError",
    "ToolPermission",
    "WorkspaceSandbox",
    "build_default_mcp_server",
    "default_tool_definitions",
]
