from __future__ import annotations

import json
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from specflow.agents.architect.clarify import ClarificationGraph
from specflow.agents.architect.models import (
    ArchitectArtifactDraftBundle,
    ArchitectRunResult,
    ClarifiedRequirements,
    TaskDraft,
)
from specflow.config import Settings, get_settings
from specflow.llm import build_chat_model
from specflow.models import (
    ArtifactFormat,
    ArtifactKind,
    Project,
    RunPhase,
    TaskItem,
    TaskStatus,
)
from specflow.storage import ArtifactRepository, CheckpointManager, RunStateManager
from specflow.storage.db import get_session_factory, session_scope
from specflow.templates import (
    TemplateProfileDefinition,
    ensure_template_profile_record,
    get_template_profile_definition,
)


class ArchitectAgent:
    """Generate Spec Kit artifacts for the default ticket-system template."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: sessionmaker[Session] | None = None,
        artifact_repository: ArtifactRepository | None = None,
        run_state_manager: RunStateManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_directories()
        self.session_factory = (
            session_factory
            or (run_state_manager.session_factory if run_state_manager is not None else None)
            or get_session_factory()
        )
        self.artifact_repository = artifact_repository or ArtifactRepository(
            session_factory=self.session_factory,
            settings=self.settings,
        )
        self.run_state_manager = run_state_manager or RunStateManager(
            session_factory=self.session_factory,
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )
        self.checkpoint_manager = checkpoint_manager or CheckpointManager(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
        )
        self.chat_model = build_chat_model(self.settings) if self.settings.llm_model else None
        self.clarification_graph = ClarificationGraph()

    def run(
        self,
        run_id: str,
        *,
        supplemental_inputs: list[str] | None = None,
        max_clarification_rounds: int = 2,
    ) -> ArchitectRunResult:
        snapshot = self.run_state_manager.load_run(run_id)
        if snapshot.current_phase not in {
            RunPhase.CLARIFY,
            RunPhase.SPECIFY,
            RunPhase.PLAN,
            RunPhase.TASKS,
        }:
            raise ValueError(
                "Architect can only run before implementation. "
                f"Current phase: {snapshot.current_phase.value}."
            )

        project = self._load_project(snapshot.project_id)
        template_profile = get_template_profile_definition(template_type=project.template_type)
        ensure_template_profile_record(self.session_factory, profile=template_profile)

        artifact_versions: dict[str, int] = {}
        constitution = self._store_artifact(
            run_id=run_id,
            name=".specify/memory/constitution.md",
            content=self._render_constitution(project=project, profile=template_profile),
            kind=ArtifactKind.CONSTITUTION,
        )
        artifact_versions[constitution.name] = constitution.version

        clarification = self.clarification_graph.run(
            request=snapshot.input_prompt,
            template_profile=template_profile,
            target_stack=project.target_stack,
            supplemental_inputs=supplemental_inputs,
            max_rounds=max_clarification_rounds,
        )
        tasks = self._build_task_drafts(clarification=clarification, profile=template_profile)
        draft_bundle = self._render_artifact_bundle(
            project=project,
            clarification=clarification,
            profile=template_profile,
            tasks=tasks,
        )
        notes = self._store_artifact(
            run_id=run_id,
            name="clarification-notes.md",
            content=draft_bundle.clarification_notes_markdown,
            kind=ArtifactKind.CLARIFICATION_NOTES,
        )
        artifact_versions[notes.name] = notes.version
        self.checkpoint_manager.save_phase_checkpoint(
            run_id,
            phase=RunPhase.CLARIFY,
            state=clarification.model_dump(mode="python"),
            metadata={
                "source": "architect",
                "artifact_names": [constitution.name, notes.name],
            },
        )
        self._transition_if_current(
            run_id=run_id,
            current_phase=RunPhase.CLARIFY,
            target_phase=RunPhase.SPECIFY,
            summary="Architect clarified the request and initialized Spec Kit artifacts.",
        )

        spec = self._store_artifact(
            run_id=run_id,
            name="spec.md",
            content=draft_bundle.spec_markdown,
            kind=ArtifactKind.SPEC,
        )
        data_model = self._store_artifact(
            run_id=run_id,
            name="data-model.md",
            content=self._render_data_model(
                clarification=clarification,
                profile=template_profile,
            ),
            kind=ArtifactKind.DATA_MODEL,
        )
        artifact_versions[spec.name] = spec.version
        artifact_versions[data_model.name] = data_model.version
        self.checkpoint_manager.save_phase_checkpoint(
            run_id,
            phase=RunPhase.SPECIFY,
            state={
                "spec_artifacts": [spec.name, data_model.name],
                "clarification_complete": clarification.is_complete,
            },
            metadata={"source": "architect"},
        )
        self._transition_if_current(
            run_id=run_id,
            current_phase=RunPhase.SPECIFY,
            target_phase=RunPhase.PLAN,
            summary="Architect generated the specification and data model.",
        )

        plan = self._store_artifact(
            run_id=run_id,
            name="plan.md",
            content=draft_bundle.plan_markdown,
            kind=ArtifactKind.PLAN,
        )
        research = self._store_artifact(
            run_id=run_id,
            name="research.md",
            content=draft_bundle.research_markdown,
            kind=ArtifactKind.RESEARCH,
        )
        contract = self._store_artifact(
            run_id=run_id,
            name="contracts/openapi.yaml",
            content=self._render_openapi_contract(clarification=clarification),
            kind=ArtifactKind.CONTRACT,
            artifact_format=ArtifactFormat.YAML,
        )
        artifact_versions[plan.name] = plan.version
        artifact_versions[research.name] = research.version
        artifact_versions[contract.name] = contract.version
        self.checkpoint_manager.save_phase_checkpoint(
            run_id,
            phase=RunPhase.PLAN,
            state={
                "plan_artifacts": [plan.name, research.name, contract.name],
                "requested_capabilities": clarification.requested_capabilities,
            },
            metadata={"source": "architect"},
        )
        self._transition_if_current(
            run_id=run_id,
            current_phase=RunPhase.PLAN,
            target_phase=RunPhase.TASKS,
            summary=(
                "Architect produced the implementation plan, " "research notes, and API contracts."
            ),
        )

        tasks_artifact = self._store_artifact(
            run_id=run_id,
            name="tasks.md",
            content=self._render_tasks_markdown(tasks),
            kind=ArtifactKind.TASKS,
        )
        artifact_versions[tasks_artifact.name] = tasks_artifact.version
        self._sync_task_items(run_id=run_id, tasks=tasks)
        self.checkpoint_manager.save_phase_checkpoint(
            run_id,
            phase=RunPhase.TASKS,
            state={"tasks": [task.model_dump(mode="python") for task in tasks]},
            metadata={"source": "architect"},
        )

        final_snapshot = self.run_state_manager.load_run(run_id)
        return ArchitectRunResult(
            run_id=run_id,
            current_phase=final_snapshot.current_phase,
            clarification=clarification,
            artifact_versions=artifact_versions,
            task_items=tasks,
        )

    def _load_project(self, project_id: str) -> Project:
        with session_scope(self.session_factory) as session:
            project = session.get(Project, project_id)
            if project is None:
                raise ValueError(f"Project {project_id!r} does not exist.")
            return project

    def _transition_if_current(
        self,
        *,
        run_id: str,
        current_phase: RunPhase,
        target_phase: RunPhase,
        summary: str,
    ) -> None:
        snapshot = self.run_state_manager.load_run(run_id)
        if snapshot.current_phase == current_phase:
            self.run_state_manager.transition_to_phase(
                run_id,
                target_phase,
                summary=summary,
                message=f"Architect completed {current_phase.value}.",
            )

    def _store_artifact(
        self,
        *,
        run_id: str,
        name: str,
        content: str,
        kind: ArtifactKind,
        artifact_format: ArtifactFormat | None = None,
    ) -> Any:
        return self.artifact_repository.save_artifact(
            run_id,
            name=name,
            content=content,
            kind=kind,
            artifact_format=artifact_format,
            details={"generated_by": "architect"},
        )

    def _sync_task_items(self, *, run_id: str, tasks: list[TaskDraft]) -> None:
        with session_scope(self.session_factory) as session:
            existing = {
                item.task_key: item
                for item in session.scalars(select(TaskItem).where(TaskItem.run_id == run_id))
            }
            desired_keys = {task.task_key for task in tasks}

            for task in tasks:
                record = existing.get(task.task_key)
                if record is None:
                    session.add(
                        TaskItem(
                            run_id=run_id,
                            task_key=task.task_key,
                            title=task.title,
                            description=task.description,
                            status=TaskStatus.PENDING,
                            priority=task.priority,
                            sequence=task.sequence,
                            details=task.details,
                        )
                    )
                    continue
                record.title = task.title
                record.description = task.description
                record.status = TaskStatus.PENDING
                record.priority = task.priority
                record.sequence = task.sequence
                record.details = task.details
                record.completed_at = None

            for task_key, record in existing.items():
                if task_key not in desired_keys:
                    session.delete(record)

    def _build_task_drafts(
        self,
        *,
        clarification: ClarifiedRequirements,
        profile: TemplateProfileDefinition,
    ) -> list[TaskDraft]:
        api_paths = [api.base_path for api in profile.api_definitions]
        page_routes = [page.route for page in profile.pages]
        return [
            TaskDraft(
                task_key="ARCH-001",
                title="Build backend domain model and migrations",
                description=(
                    "Create SQLAlchemy models and persistence for ticket, user, "
                    "department, comment, and attachment entities."
                ),
                priority=100,
                sequence=1,
                details={"area": "backend", "entities": clarification.entities},
            ),
            TaskDraft(
                task_key="ARCH-002",
                title="Implement ticket CRUD and workflow APIs",
                description=(
                    "Expose paginated ticket endpoints, detail/update flows, "
                    "and safe status transitions."
                ),
                priority=95,
                sequence=2,
                details={
                    "area": "backend",
                    "paths": api_paths[:2],
                    "state_machine": clarification.state_machine,
                },
            ),
            TaskDraft(
                task_key="ARCH-003",
                title="Implement supporting directory and timeline APIs",
                description=(
                    "Add department, user lookup, comment timeline, "
                    "and attachment handling endpoints."
                ),
                priority=90,
                sequence=3,
                details={"area": "backend", "paths": api_paths[2:]},
            ),
            TaskDraft(
                task_key="ARCH-004",
                title="Build dashboard and ticket management UI",
                description=(
                    "Implement ticket list, detail, create, edit, and dashboard "
                    "pages in the React frontend."
                ),
                priority=90,
                sequence=4,
                details={"area": "frontend", "routes": page_routes},
            ),
            TaskDraft(
                task_key="ARCH-005",
                title="Wire RBAC and workflow guards",
                description=(
                    "Apply role-based visibility, department scoping, "
                    "and workflow transition validation across the stack."
                ),
                priority=88,
                sequence=5,
                details={"area": "cross-cutting", "roles": clarification.roles},
            ),
            TaskDraft(
                task_key="ARCH-006",
                title="Author automated tests and delivery notes",
                description=(
                    "Cover backend APIs, state transitions, and core frontend "
                    "flows with pytest and Playwright smoke tests."
                ),
                priority=80,
                sequence=6,
                details={
                    "area": "quality",
                    "acceptance_criteria": clarification.acceptance_criteria,
                },
            ),
        ]

    def _render_constitution(
        self,
        *,
        project: Project,
        profile: TemplateProfileDefinition,
    ) -> str:
        principles = "\n".join(
            f"{index}. {principle}"
            for index, principle in enumerate(profile.constitution_principles, start=1)
        )
        return f"""# Constitution

## Project Context
- Project: {project.name}
- Template: {profile.name} ({profile.version})
- Target Stack: {project.target_stack}

## Working Principles
{principles}

## Default Delivery Scope
- Entities: {", ".join(entity.title for entity in profile.entities)}
- Pages: {", ".join(page.title for page in profile.pages)}
- APIs: {", ".join(api.base_path for api in profile.api_definitions)}
- Workflow: {" -> ".join(profile.state_machine)}
"""

    def _render_artifact_bundle(
        self,
        *,
        project: Project,
        clarification: ClarifiedRequirements,
        profile: TemplateProfileDefinition,
        tasks: list[TaskDraft],
    ) -> ArchitectArtifactDraftBundle:
        deterministic = ArchitectArtifactDraftBundle(
            clarification_notes_markdown=self._render_clarification_notes(clarification),
            spec_markdown=self._render_spec(project=project, clarification=clarification),
            plan_markdown=self._render_plan(clarification=clarification, profile=profile),
            research_markdown=self._render_research(
                clarification=clarification,
                profile=profile,
            ),
        )
        if self.chat_model is None:
            return deterministic

        structured_model = self.chat_model.with_structured_output(ArchitectArtifactDraftBundle)
        context = {
            "project": {
                "name": project.name,
                "template_type": project.template_type.value,
                "target_stack": project.target_stack,
                "description": project.description,
            },
            "clarification": clarification.model_dump(mode="python"),
            "tasks": [task.model_dump(mode="python") for task in tasks],
            "template_profile": {
                "slug": profile.slug,
                "name": profile.name,
                "version": profile.version,
                "pages": [page.to_payload() for page in profile.pages],
                "apis": [api.to_payload() for api in profile.api_definitions],
            },
            "starter_drafts": deterministic.model_dump(mode="python"),
        }

        try:
            draft = cast(
                ArchitectArtifactDraftBundle,
                structured_model.invoke(
                    [
                        SystemMessage(
                            content=(
                                "You are the SpecFlow architect writer. "
                                "Refine the provided starter drafts into concise, "
                                "implementation-ready artifacts. Do not invent scope "
                                "outside the clarified requirements. Preserve the same "
                                "workflow states, roles, APIs, and overall feature set. "
                                "Return plain markdown strings only, with no code fences."
                            )
                        ),
                        HumanMessage(
                            content=(
                                "Refine these architect artifacts for an internal system "
                                "delivery project.\n"
                                "Use the validated context and keep the result practical "
                                "for downstream implementation.\n\n"
                                f"{json.dumps(context, ensure_ascii=False, indent=2)}"
                            )
                        ),
                    ]
                ),
            )
        except Exception:
            return deterministic

        return ArchitectArtifactDraftBundle(
            clarification_notes_markdown=_sanitize_llm_text(
                draft.clarification_notes_markdown,
                deterministic.clarification_notes_markdown,
            ),
            spec_markdown=_sanitize_llm_text(
                draft.spec_markdown,
                deterministic.spec_markdown,
            ),
            plan_markdown=_sanitize_llm_text(
                draft.plan_markdown,
                deterministic.plan_markdown,
            ),
            research_markdown=_sanitize_llm_text(
                draft.research_markdown,
                deterministic.research_markdown,
            ),
        )

    def _render_clarification_notes(self, clarification: ClarifiedRequirements) -> str:
        rounds = []
        for round_item in clarification.rounds:
            questions = "\n".join(f"- {question.question}" for question in round_item.questions)
            answer = round_item.answer or "No supplemental input was provided."
            rounds.append(
                "\n".join(
                    [
                        f"### Round {round_item.round_number}",
                        f"- Gaps: {', '.join(round_item.gaps) or 'none'}",
                        questions or "- Questions: none",
                        f"- Answer: {answer}",
                    ]
                )
            )
        rounds_block = "\n\n".join(rounds) or "No clarification rounds were needed."
        assumptions = "\n".join(f"- {item}" for item in clarification.assumptions)
        open_questions = (
            "\n".join(f"- {question}" for question in clarification.open_questions)
            if clarification.open_questions
            else "- None. The requirement set is actionable."
        )
        return f"""# Clarification Notes

## Original Request
{clarification.original_request}

## Clarified Summary
{clarification.requirement_summary}

## Coverage Snapshot
- Completeness Score: {clarification.completeness_score}
- Ready For Specification: {clarification.is_complete}
- Roles: {", ".join(clarification.roles)}
- Workflow: {" -> ".join(clarification.state_machine)}

## Clarification Rounds
{rounds_block}

## Assumptions
{assumptions}

## Open Questions
{open_questions}
"""

    def _render_spec(self, *, project: Project, clarification: ClarifiedRequirements) -> str:
        roles = "\n".join(f"- {role}" for role in clarification.roles)
        entities = "\n".join(f"- {entity}" for entity in clarification.entities)
        pages = "\n".join(f"- {page}" for page in clarification.pages)
        apis = "\n".join(f"- {api}" for api in clarification.apis)
        business_rules = "\n".join(f"- {rule}" for rule in clarification.business_rules)
        acceptance = "\n".join(f"- {criterion}" for criterion in clarification.acceptance_criteria)
        assumptions = "\n".join(f"- {item}" for item in clarification.assumptions)
        return f"""# Specification

## Product
- Name: {project.name}
- Template: {clarification.template_slug}
- Target Stack: {clarification.target_stack}

## Summary
{clarification.requirement_summary}

## Roles
{roles}

## Core Entities
{entities}

## Pages
{pages}

## APIs
{apis}

## Workflow
- {" -> ".join(clarification.state_machine)}

## Business Rules
{business_rules}

## Acceptance Criteria
{acceptance}

## Assumptions
{assumptions}
"""

    def _render_data_model(
        self,
        *,
        clarification: ClarifiedRequirements,
        profile: TemplateProfileDefinition,
    ) -> str:
        sections: list[str] = [
            "# Data Model",
            "",
            f"Target workflow: {' -> '.join(clarification.state_machine)}",
            "",
        ]
        for entity in profile.entities:
            sections.extend([f"## {entity.title}", entity.description, ""])
            for field in entity.fields:
                required = "required" if field.required else "optional"
                filters = "filterable" if field.filterable else "not filterable"
                sections.append(
                    f"- `{field.name}`: {field.field_type} "
                    f"({required}, {filters}) - {field.description}"
                )
            sections.append("")
        return "\n".join(sections).rstrip() + "\n"

    def _render_plan(
        self,
        *,
        clarification: ClarifiedRequirements,
        profile: TemplateProfileDefinition,
    ) -> str:
        page_titles = ", ".join(page.title for page in profile.pages)
        api_titles = ", ".join(api.title for api in profile.api_definitions)
        return f"""# Plan

## Delivery Strategy
- Start from backend-first domain modeling for {", ".join(clarification.entities)}.
- Implement contract-aligned APIs before wiring React pages.
- Freeze RBAC and workflow guards before feature polishing.

## Workstreams
### Backend
- Create persistence, services, and routers for ticket workflow.
- Cover CRUD, pagination, filters, comments, attachments, and dashboard summaries.

### Frontend
- Build pages: {page_titles}.
- Keep forms aligned with API contracts and workflow constraints.

### Quality
- Add pytest coverage for API contracts and state transitions.
- Add Playwright smoke flows for dashboard, create, detail, and edit journeys.

## Contract Targets
- APIs: {api_titles}
- Workflow states: {" -> ".join(clarification.state_machine)}
"""

    def _render_research(
        self,
        *,
        clarification: ClarifiedRequirements,
        profile: TemplateProfileDefinition,
    ) -> str:
        return f"""# Research

## Fixed Decisions
- Platform stack remains {clarification.target_stack}.
- The default template is {profile.slug} ({profile.version}).
- RBAC and workflow auditability are mandatory for v1.

## Key Tradeoffs
- Use a simplified notification posture in v1 unless later requirements force async channels.
- Prefer deterministic CRUD coverage over bespoke workflow branching.
- Keep the dashboard focused on queue metrics, SLA pressure, and department distribution.

## Open Risks
- Role or SLA assumptions may need revision after stakeholder review.
- Attachment storage strategy should stay abstract until implementation sprint.
- Frontend dashboard scope should avoid chart bloat in the first release.
"""

    def _render_openapi_contract(self, *, clarification: ClarifiedRequirements) -> str:
        states = "\n".join(f"                  - {state}" for state in clarification.state_machine)
        roles = "\n".join(f"                  - {role}" for role in clarification.roles)
        return f"""openapi: 3.1.0
info:
  title: Simplified Internal Ticket System API
  version: 1.0.0
paths:
  /api/tickets:
    get:
      summary: List tickets with pagination and filters
      parameters:
        - in: query
          name: page
          schema: {{ type: integer, minimum: 1 }}
        - in: query
          name: page_size
          schema: {{ type: integer, minimum: 1, maximum: 100 }}
        - in: query
          name: state
          schema:
            type: string
            enum:
{states}
    post:
      summary: Create a ticket
  /api/tickets/{{ticketId}}:
    get:
      summary: Retrieve ticket detail
    patch:
      summary: Update ticket metadata
  /api/tickets/{{ticketId}}/transition:
    post:
      summary: Change ticket state with audit comment
  /api/tickets/{{ticketId}}/comments:
    get:
      summary: List ticket comments
    post:
      summary: Add a ticket comment
  /api/tickets/{{ticketId}}/attachments:
    get:
      summary: List ticket attachments
    post:
      summary: Upload an attachment
  /api/users:
    get:
      summary: List users available for routing and assignment
  /api/departments:
    get:
      summary: List departments for routing and filtering
  /api/dashboard/summary:
    get:
      summary: Get queue summary metrics
components:
  schemas:
    Ticket:
      type: object
      required: [id, title, state, priority, requester_id, department_id]
      properties:
        id: {{ type: string, format: uuid }}
        title: {{ type: string }}
        description: {{ type: string }}
        state:
          type: string
          enum:
{states}
        priority: {{ type: string }}
        requester_id: {{ type: string, format: uuid }}
        assignee_id: {{ type: string, format: uuid, nullable: true }}
        department_id: {{ type: string, format: uuid }}
    User:
      type: object
      required: [id, name, email, role]
      properties:
        id: {{ type: string, format: uuid }}
        name: {{ type: string }}
        email: {{ type: string, format: email }}
        role:
          type: string
          enum:
{roles}
"""

    def _render_tasks_markdown(self, tasks: list[TaskDraft]) -> str:
        lines = ["# Tasks", ""]
        for task in tasks:
            lines.append(f"## {task.task_key} - {task.title}")
            lines.append(task.description)
            lines.append(f"- Priority: {task.priority}")
            lines.append(f"- Sequence: {task.sequence}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _sanitize_llm_text(value: str, fallback: str) -> str:
    stripped = value.strip()
    if not stripped:
        return fallback
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
    return stripped or fallback
