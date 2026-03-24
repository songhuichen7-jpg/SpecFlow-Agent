from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from specflow.config import Settings
from specflow.storage.artifacts import ArtifactRepository
from specflow.storage.runtime import RunStateManager
from specflow.templates import TemplateLibrary


class ToolGroup(StrEnum):
    SCAFFOLD_TOOLS = "scaffold_tools"
    TEMPLATE_TOOLS = "template_tools"
    WORKSPACE_TOOLS = "workspace_tools"
    QUALITY_TOOLS = "quality_tools"
    SPEC_TOOLS = "spec_tools"


class ToolPermission(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"


@dataclass(frozen=True)
class PermissionPolicy:
    """Permission flags checked before dispatching sensitive tools."""

    allow_read: bool = True
    allow_write: bool = True
    allow_execute: bool = True
    allow_delete: bool = False

    def allows(self, permission: ToolPermission) -> bool:
        if permission is ToolPermission.READ:
            return self.allow_read
        if permission is ToolPermission.WRITE:
            return self.allow_write
        if permission is ToolPermission.EXECUTE:
            return self.allow_execute
        return self.allow_delete


@dataclass(frozen=True)
class ToolContext:
    """Shared context passed to MCP tool handlers."""

    run_id: str
    settings: Settings
    artifact_repository: ArtifactRepository
    run_state_manager: RunStateManager
    template_library: TemplateLibrary
    permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)

    @property
    def workspace_root(self) -> Path:
        return self.artifact_repository.get_run_layout(self.run_id).workspace_dir


@dataclass(frozen=True)
class MCPToolDefinition:
    """Metadata and callable for a registered MCP tool."""

    name: str
    group: ToolGroup
    description: str
    permission: ToolPermission
    handler: Callable[..., Any]
    input_schema: dict[str, Any] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.group.value}.{self.name}"


@dataclass(frozen=True)
class MCPToolRequest:
    """Unified invocation request for MCP tools."""

    tool_name: str
    run_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    permission_policy: PermissionPolicy = field(default_factory=PermissionPolicy)


@dataclass(frozen=True)
class MCPToolResult:
    """Normalized MCP tool execution result."""

    tool_name: str
    group: ToolGroup
    success: bool
    output: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DirectoryEntry:
    """Serializable directory listing entry."""

    path: str
    is_dir: bool
    size: int
