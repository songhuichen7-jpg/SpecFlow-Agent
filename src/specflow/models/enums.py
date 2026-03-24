from __future__ import annotations

from enum import StrEnum


class TemplateType(StrEnum):
    TICKET_SYSTEM = "ticket_system"
    LEDGER_SYSTEM = "ledger_system"
    APPROVAL_SYSTEM = "approval_system"
    CRUD_ADMIN = "crud_admin"


class RunStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_HUMAN = "waiting_for_human"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunPhase(StrEnum):
    CLARIFY = "clarify"
    SPECIFY = "specify"
    PLAN = "plan"
    TASKS = "tasks"
    IMPLEMENT = "implement"
    REVIEW = "review"
    DELIVER = "deliver"


class ExecutionMode(StrEnum):
    STANDARD = "standard"
    DEBUG = "debug"


class ArtifactKind(StrEnum):
    CHECKPOINT = "checkpoint"
    CONSTITUTION = "constitution"
    SPEC = "spec"
    CLARIFICATION_NOTES = "clarification_notes"
    PLAN = "plan"
    RESEARCH = "research"
    DATA_MODEL = "data_model"
    CONTRACT = "contract"
    TASKS = "tasks"
    REVIEW_REPORT = "review_report"
    TEST_REPORT = "test_report"
    RUN_LOG = "run_log"
    CODE_BUNDLE = "code_bundle"


class ArtifactFormat(StrEnum):
    MARKDOWN = "markdown"
    JSON = "json"
    YAML = "yaml"
    TEXT = "text"
    HTML = "html"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


class ReviewSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewIssueStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    FIXED = "fixed"
    DISMISSED = "dismissed"


class ExecutionEventType(StrEnum):
    CHECKPOINT_RESTORED = "checkpoint_restored"
    CHECKPOINT_SAVED = "checkpoint_saved"
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    PHASE_FAILED = "phase_failed"
    PHASE_ROLLED_BACK = "phase_rolled_back"
    HUMAN_GATE_REQUESTED = "human_gate_requested"
    HUMAN_GATE_APPROVED = "human_gate_approved"
    HUMAN_GATE_REJECTED = "human_gate_rejected"
    TOOL_CALLED = "tool_called"
    RETRY_SCHEDULED = "retry_scheduled"
