from __future__ import annotations


class MCPError(Exception):
    """Base exception for the MCP capability layer."""


class ToolNotFoundError(MCPError, LookupError):
    """Raised when a tool cannot be found in the MCP registry."""


class PermissionDeniedError(MCPError, PermissionError):
    """Raised when a tool invocation violates the permission policy."""


class SandboxViolationError(MCPError, ValueError):
    """Raised when a file operation escapes the allowed workspace sandbox."""


class ToolExecutionError(MCPError, RuntimeError):
    """Raised when a tool handler fails unexpectedly."""
