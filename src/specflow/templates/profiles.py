from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from specflow.models import TemplateProfile, TemplateType
from specflow.storage.db import session_scope

DEFAULT_TEMPLATE_SLUG = "ticket-system"
DEFAULT_TARGET_STACK = "fastapi-react-vite-typescript-postgresql"
DEFAULT_TEMPLATE_VERSION = "1.0.0"


@dataclass(frozen=True)
class TemplateEntityField:
    """Field definition for a generated domain entity."""

    name: str
    field_type: str
    description: str
    required: bool = True
    filterable: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "field_type": self.field_type,
            "description": self.description,
            "required": self.required,
            "filterable": self.filterable,
        }


@dataclass(frozen=True)
class TemplateEntityDefinition:
    """Entity definition used by the Architect agent."""

    key: str
    title: str
    description: str
    fields: tuple[TemplateEntityField, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "description": self.description,
            "fields": [field.to_payload() for field in self.fields],
        }


@dataclass(frozen=True)
class TemplatePageDefinition:
    """Default page definition for the scaffolded product."""

    key: str
    title: str
    route: str
    description: str

    def to_payload(self) -> dict[str, str]:
        return {
            "key": self.key,
            "title": self.title,
            "route": self.route,
            "description": self.description,
        }


@dataclass(frozen=True)
class TemplateApiDefinition:
    """API surface definition for the template profile."""

    key: str
    title: str
    base_path: str
    operations: tuple[str, ...]
    description: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "base_path": self.base_path,
            "operations": list(self.operations),
            "description": self.description,
        }


@dataclass(frozen=True)
class TemplateProfileDefinition:
    """Serializable template profile consumed by Architect and MCP tools."""

    name: str
    slug: str
    version: str
    template_type: TemplateType
    description: str
    default_stack: str
    entities: tuple[TemplateEntityDefinition, ...]
    pages: tuple[TemplatePageDefinition, ...]
    api_definitions: tuple[TemplateApiDefinition, ...]
    roles: tuple[str, ...]
    state_machine: tuple[str, ...]
    constitution_principles: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]

    def constraints_payload(self) -> dict[str, Any]:
        return {
            "rbac": {
                "enabled": True,
                "roles": list(self.roles),
                "policy": "requester_scope + department_scope + admin_override",
            },
            "workflow": {
                "states": list(self.state_machine),
                "requires_comment_on_transition": True,
                "audit_log_required": True,
            },
            "api": {
                "pagination_required": True,
                "supports_filters": ["keyword", "state", "priority", "department_id"],
                "resources": [api.to_payload() for api in self.api_definitions],
            },
            "entities": [entity.to_payload() for entity in self.entities],
            "pages": [page.to_payload() for page in self.pages],
        }

    def defaults_payload(self) -> dict[str, Any]:
        return {
            "entities": [entity.key for entity in self.entities],
            "page_routes": {page.key: page.route for page in self.pages},
            "api_paths": {api.key: api.base_path for api in self.api_definitions},
            "dashboard_metrics": [
                "open_tickets",
                "sla_breaches",
                "tickets_by_department",
                "tickets_by_state",
            ],
            "attachments_enabled": True,
            "comment_threads_enabled": True,
            "sample_seed_data": True,
        }

    def to_record_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "slug": self.slug,
            "version": self.version,
            "template_type": self.template_type,
            "description": self.description,
            "default_stack": self.default_stack,
            "constraints": self.constraints_payload(),
            "defaults": self.defaults_payload(),
            "is_active": True,
        }


DEFAULT_TEMPLATE_PROFILE = TemplateProfileDefinition(
    name="Simplified Internal Ticket System",
    slug=DEFAULT_TEMPLATE_SLUG,
    version=DEFAULT_TEMPLATE_VERSION,
    template_type=TemplateType.TICKET_SYSTEM,
    description=(
        "A simplified internal ticket system profile with RBAC, ticket workflow, "
        "dashboard views, and standard CRUD surfaces."
    ),
    default_stack=DEFAULT_TARGET_STACK,
    entities=(
        TemplateEntityDefinition(
            key="ticket",
            title="Ticket",
            description="Core work item tracked through an internal support workflow.",
            fields=(
                TemplateEntityField("id", "uuid", "Primary identifier."),
                TemplateEntityField("title", "string", "Short problem summary."),
                TemplateEntityField("description", "text", "Detailed request body."),
                TemplateEntityField("state", "enum", "Workflow state.", filterable=True),
                TemplateEntityField("priority", "enum", "SLA priority tier.", filterable=True),
                TemplateEntityField("requester_id", "uuid", "Submitting user."),
                TemplateEntityField("assignee_id", "uuid", "Current owner.", required=False),
                TemplateEntityField("department_id", "uuid", "Owning department.", filterable=True),
                TemplateEntityField("created_at", "datetime", "Creation timestamp."),
                TemplateEntityField("updated_at", "datetime", "Last update timestamp."),
            ),
        ),
        TemplateEntityDefinition(
            key="user",
            title="User",
            description="System user participating in the ticket workflow.",
            fields=(
                TemplateEntityField("id", "uuid", "Primary identifier."),
                TemplateEntityField("name", "string", "Display name."),
                TemplateEntityField("email", "string", "Unique email address."),
                TemplateEntityField("role", "enum", "RBAC role.", filterable=True),
                TemplateEntityField("department_id", "uuid", "Home department.", required=False),
            ),
        ),
        TemplateEntityDefinition(
            key="department",
            title="Department",
            description="Department or support queue responsible for tickets.",
            fields=(
                TemplateEntityField("id", "uuid", "Primary identifier."),
                TemplateEntityField("name", "string", "Department name."),
                TemplateEntityField("code", "string", "Short unique code."),
                TemplateEntityField("manager_id", "uuid", "Department owner.", required=False),
            ),
        ),
        TemplateEntityDefinition(
            key="comment",
            title="Comment",
            description="Conversation timeline entry for a ticket.",
            fields=(
                TemplateEntityField("id", "uuid", "Primary identifier."),
                TemplateEntityField("ticket_id", "uuid", "Owning ticket."),
                TemplateEntityField("author_id", "uuid", "Comment author."),
                TemplateEntityField("body", "text", "Comment content."),
                TemplateEntityField("is_internal", "boolean", "Visibility within support team."),
                TemplateEntityField("created_at", "datetime", "Creation timestamp."),
            ),
        ),
        TemplateEntityDefinition(
            key="attachment",
            title="Attachment",
            description="Uploaded file associated with a ticket or comment.",
            fields=(
                TemplateEntityField("id", "uuid", "Primary identifier."),
                TemplateEntityField("ticket_id", "uuid", "Owning ticket."),
                TemplateEntityField("comment_id", "uuid", "Source comment.", required=False),
                TemplateEntityField("file_name", "string", "Original file name."),
                TemplateEntityField("content_type", "string", "MIME type."),
                TemplateEntityField("storage_path", "string", "Stored file path."),
                TemplateEntityField("uploaded_by", "uuid", "Uploader."),
            ),
        ),
    ),
    pages=(
        TemplatePageDefinition(
            key="ticket_list",
            title="Ticket List",
            route="/tickets",
            description="Searchable and paginated ticket inbox.",
        ),
        TemplatePageDefinition(
            key="ticket_detail",
            title="Ticket Detail",
            route="/tickets/:ticketId",
            description="Ticket timeline, metadata, comments, and state changes.",
        ),
        TemplatePageDefinition(
            key="ticket_create",
            title="Create Ticket",
            route="/tickets/new",
            description="Requester flow for submitting a new ticket.",
        ),
        TemplatePageDefinition(
            key="ticket_edit",
            title="Edit Ticket",
            route="/tickets/:ticketId/edit",
            description="Agent and admin flow for updating ticket metadata.",
        ),
        TemplatePageDefinition(
            key="dashboard",
            title="Operations Dashboard",
            route="/dashboard",
            description="High-level queue metrics and SLA overview.",
        ),
    ),
    api_definitions=(
        TemplateApiDefinition(
            key="tickets",
            title="Tickets API",
            base_path="/api/tickets",
            operations=("list", "create", "get", "update", "transition"),
            description="CRUD endpoints and state transitions for tickets.",
        ),
        TemplateApiDefinition(
            key="users",
            title="Users API",
            base_path="/api/users",
            operations=("list", "get"),
            description="User directory and role lookup.",
        ),
        TemplateApiDefinition(
            key="departments",
            title="Departments API",
            base_path="/api/departments",
            operations=("list", "get"),
            description="Department metadata for routing and filtering.",
        ),
        TemplateApiDefinition(
            key="comments",
            title="Comments API",
            base_path="/api/tickets/{ticketId}/comments",
            operations=("list", "create"),
            description="Ticket timeline comments.",
        ),
        TemplateApiDefinition(
            key="attachments",
            title="Attachments API",
            base_path="/api/tickets/{ticketId}/attachments",
            operations=("list", "create", "delete"),
            description="Attachment upload and retrieval.",
        ),
        TemplateApiDefinition(
            key="dashboard",
            title="Dashboard API",
            base_path="/api/dashboard/summary",
            operations=("get",),
            description="Queue summary and SLA metrics.",
        ),
    ),
    roles=("requester", "assignee", "admin"),
    state_machine=("open", "in_progress", "resolved", "closed"),
    constitution_principles=(
        "Spec artifacts are the single source of truth for generated delivery.",
        "RBAC, auditability, and ticket state transitions are mandatory constraints.",
        "Generated APIs must remain paginated, typed, and traceable to business entities.",
        "Every phase should leave behind deterministic artifacts that can be reviewed manually.",
    ),
    acceptance_criteria=(
        "Requesters can create and track their own tickets end-to-end.",
        "Agents can triage, update, and transition tickets with timeline comments.",
        "Admins can manage departments, users, and workflow-safe overrides.",
        "Dashboard metrics expose queue size, SLA pressure, and department distribution.",
        "All list endpoints support pagination and common operational filters.",
        "Attachments and comments remain attached to the relevant ticket timeline.",
    ),
)


def get_template_profile_definition(
    *,
    template_slug: str | None = None,
    template_type: TemplateType | None = None,
) -> TemplateProfileDefinition:
    if template_slug not in {None, DEFAULT_TEMPLATE_SLUG}:
        raise KeyError(f"Unsupported template slug: {template_slug!r}")
    if template_type not in {None, TemplateType.TICKET_SYSTEM}:
        raise KeyError(f"Unsupported template type: {template_type!r}")
    return DEFAULT_TEMPLATE_PROFILE


def ensure_template_profile_record(
    session_factory: sessionmaker[Session],
    *,
    profile: TemplateProfileDefinition | None = None,
) -> TemplateProfileDefinition:
    definition = profile or DEFAULT_TEMPLATE_PROFILE
    payload = definition.to_record_payload()

    with session_scope(session_factory) as session:
        existing = session.scalar(
            select(TemplateProfile).where(
                TemplateProfile.slug == definition.slug,
                TemplateProfile.version == definition.version,
            )
        )
        if existing is None:
            session.add(TemplateProfile(**payload))
        else:
            existing.name = payload["name"]
            existing.template_type = payload["template_type"]
            existing.description = payload["description"]
            existing.default_stack = payload["default_stack"]
            existing.constraints = payload["constraints"]
            existing.defaults = payload["defaults"]
            existing.is_active = payload["is_active"]

    return definition
