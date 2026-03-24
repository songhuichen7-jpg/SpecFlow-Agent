"""Initial Sprint 1 schema."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260324_0001"
down_revision = None
branch_labels = None
depends_on = None


artifact_format = sa.Enum(
    "markdown",
    "json",
    "yaml",
    "text",
    "html",
    name="artifact_format",
    native_enum=False,
)
artifact_kind = sa.Enum(
    "checkpoint",
    "constitution",
    "spec",
    "clarification_notes",
    "plan",
    "research",
    "data_model",
    "contract",
    "tasks",
    "review_report",
    "test_report",
    "run_log",
    "code_bundle",
    name="artifact_kind",
    native_enum=False,
)
execution_event_type = sa.Enum(
    "checkpoint_restored",
    "checkpoint_saved",
    "phase_started",
    "phase_completed",
    "phase_failed",
    "phase_rolled_back",
    "human_gate_requested",
    "human_gate_approved",
    "human_gate_rejected",
    "tool_called",
    "retry_scheduled",
    name="execution_event_type",
    native_enum=False,
)
execution_mode = sa.Enum("standard", "debug", name="execution_mode", native_enum=False)
review_issue_status = sa.Enum(
    "open",
    "accepted",
    "fixed",
    "dismissed",
    name="review_issue_status",
    native_enum=False,
)
review_severity = sa.Enum(
    "low",
    "medium",
    "high",
    "critical",
    name="review_severity",
    native_enum=False,
)
run_phase = sa.Enum(
    "clarify",
    "specify",
    "plan",
    "tasks",
    "implement",
    "review",
    "deliver",
    name="run_phase",
    native_enum=False,
)
run_status = sa.Enum(
    "pending",
    "in_progress",
    "waiting_for_human",
    "completed",
    "failed",
    "cancelled",
    name="run_status",
    native_enum=False,
)
task_status = sa.Enum(
    "pending",
    "in_progress",
    "blocked",
    "done",
    "failed",
    name="task_status",
    native_enum=False,
)
template_type = sa.Enum(
    "ticket_system",
    "ledger_system",
    "approval_system",
    "crud_admin",
    name="template_type",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("template_type", template_type, nullable=False),
        sa.Column("target_stack", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project")),
        sa.UniqueConstraint("slug", name=op.f("uq_project_slug")),
    )
    op.create_index(op.f("ix_project_template_type"), "project", ["template_type"], unique=False)

    op.create_table(
        "template_profile",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("template_type", template_type, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_stack", sa.String(length=255), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("defaults", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_profile")),
        sa.UniqueConstraint("slug", "version", name=op.f("uq_template_profile_slug")),
    )
    op.create_index(
        op.f("ix_template_profile_template_type"),
        "template_profile",
        ["template_type"],
        unique=False,
    )

    op.create_table(
        "run",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("current_phase", run_phase, nullable=False),
        sa.Column("mode", execution_mode, nullable=False),
        sa.Column("input_prompt", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("human_gate_pending", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_run_project_id_project")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run")),
    )
    op.create_index(op.f("ix_run_current_phase"), "run", ["current_phase"], unique=False)
    op.create_index(op.f("ix_run_status"), "run", ["status"], unique=False)

    op.create_table(
        "artifact",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", artifact_kind, nullable=False),
        sa.Column("path", sa.String(length=1024), nullable=False),
        sa.Column("artifact_format", artifact_format, nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("is_frozen", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"], name=op.f("fk_artifact_run_id_run")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_artifact")),
    )
    op.create_index(op.f("ix_artifact_kind"), "artifact", ["kind"], unique=False)
    op.create_index(op.f("ix_artifact_run_id"), "artifact", ["run_id"], unique=False)

    op.create_table(
        "task_item",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("task_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", task_status, nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sequence", sa.Integer(), server_default="0", nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"], name=op.f("fk_task_item_run_id_run")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_item")),
        sa.UniqueConstraint("run_id", "task_key", name=op.f("uq_task_item_run_id")),
    )
    op.create_index(op.f("ix_task_item_status"), "task_item", ["status"], unique=False)

    op.create_table(
        "review_issue",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", review_severity, nullable=False),
        sa.Column("status", review_issue_status, nullable=False),
        sa.Column("spec_reference", sa.String(length=255), nullable=True),
        sa.Column("code_reference", sa.String(length=255), nullable=True),
        sa.Column("suggested_fix", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"], ["artifact.id"], name=op.f("fk_review_issue_artifact_id_artifact")
        ),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"], name=op.f("fk_review_issue_run_id_run")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_issue")),
    )
    op.create_index(op.f("ix_review_issue_severity"), "review_issue", ["severity"], unique=False)
    op.create_index(op.f("ix_review_issue_status"), "review_issue", ["status"], unique=False)

    op.create_table(
        "execution_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("phase", run_phase, nullable=False),
        sa.Column("event_type", execution_event_type, nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"], name=op.f("fk_execution_event_run_id_run")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_event")),
    )
    op.create_index(
        op.f("ix_execution_event_event_type"), "execution_event", ["event_type"], unique=False
    )
    op.create_index(op.f("ix_execution_event_phase"), "execution_event", ["phase"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_execution_event_phase"), table_name="execution_event")
    op.drop_index(op.f("ix_execution_event_event_type"), table_name="execution_event")
    op.drop_table("execution_event")

    op.drop_index(op.f("ix_review_issue_status"), table_name="review_issue")
    op.drop_index(op.f("ix_review_issue_severity"), table_name="review_issue")
    op.drop_table("review_issue")

    op.drop_index(op.f("ix_task_item_status"), table_name="task_item")
    op.drop_table("task_item")

    op.drop_index(op.f("ix_artifact_run_id"), table_name="artifact")
    op.drop_index(op.f("ix_artifact_kind"), table_name="artifact")
    op.drop_table("artifact")

    op.drop_index(op.f("ix_run_status"), table_name="run")
    op.drop_index(op.f("ix_run_current_phase"), table_name="run")
    op.drop_table("run")

    op.drop_index(op.f("ix_template_profile_template_type"), table_name="template_profile")
    op.drop_table("template_profile")

    op.drop_index(op.f("ix_project_template_type"), table_name="project")
    op.drop_table("project")

    template_type.drop(op.get_bind(), checkfirst=False)
    task_status.drop(op.get_bind(), checkfirst=False)
    run_status.drop(op.get_bind(), checkfirst=False)
    run_phase.drop(op.get_bind(), checkfirst=False)
    review_severity.drop(op.get_bind(), checkfirst=False)
    review_issue_status.drop(op.get_bind(), checkfirst=False)
    execution_mode.drop(op.get_bind(), checkfirst=False)
    execution_event_type.drop(op.get_bind(), checkfirst=False)
    artifact_kind.drop(op.get_bind(), checkfirst=False)
    artifact_format.drop(op.get_bind(), checkfirst=False)
