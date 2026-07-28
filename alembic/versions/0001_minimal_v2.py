"""add minimal v2 analysis persistence

Revision ID: 0001_minimal_v2
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_minimal_v2"
down_revision = None
branch_labels = None
depends_on = None


def _create_v1_baseline_if_missing() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "files" not in existing:
        op.create_table(
            "files",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("filepath", sa.String(), nullable=False),
            sa.Column("file_type", sa.String(), nullable=False),
            sa.Column("row_count", sa.Integer()),
            sa.Column("col_count", sa.Integer()),
            sa.Column("columns_info", sa.JSON()),
            sa.Column("profile_report", sa.Text()),
            sa.Column("uploaded_at", sa.DateTime()),
        )
    if "conversations" not in existing:
        op.create_table(
            "conversations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("file_id", sa.String(), sa.ForeignKey("files.id"), nullable=False),
            sa.Column("title", sa.String()),
            sa.Column("mode", sa.String()),
            sa.Column("created_at", sa.DateTime()),
        )
    if "messages" not in existing:
        op.create_table(
            "messages",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "conv_id",
                sa.String(),
                sa.ForeignKey("conversations.id"),
                nullable=False,
            ),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.Text()),
            sa.Column("tool_calls", sa.JSON()),
            sa.Column("chart_ids", sa.JSON()),
            sa.Column("created_at", sa.DateTime()),
        )
    if "charts" not in existing:
        op.create_table(
            "charts",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "message_id",
                sa.String(),
                sa.ForeignKey("messages.id"),
                nullable=False,
            ),
            sa.Column("chart_type", sa.String(), nullable=False),
            sa.Column("title", sa.String()),
            sa.Column("filepath", sa.String(), nullable=False),
            sa.Column("config", sa.JSON()),
            sa.Column("created_at", sa.DateTime()),
        )


def upgrade() -> None:
    _create_v1_baseline_if_missing()
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("conversation_id", sa.String(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("dataset_version_id", sa.String(), sa.ForeignKey("files.id"), nullable=False),
        sa.Column("trigger_message_id", sa.String(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("answer_message_id", sa.String(), sa.ForeignKey("messages.id")),
        sa.Column("parent_run_id", sa.String(), sa.ForeignKey("analysis_runs.id")),
        sa.Column("retry_of_run_id", sa.String(), sa.ForeignKey("analysis_runs.id")),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_phase", sa.String()),
        sa.Column("context_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("progress_json", sa.JSON(), nullable=False),
        sa.Column("failure_json", sa.JSON()),
        sa.Column("requested_by", sa.String()),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("model_config_json", sa.JSON(), nullable=False),
        sa.Column("last_event_sequence", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("conversation_id", "idempotency_key"),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled')",
            name="ck_analysis_runs_status",
        ),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("run_id", sa.String(), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("plan_step_id", sa.String(100)),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_summary_json", sa.JSON()),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("error_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "sequence"),
        sa.UniqueConstraint("run_id", "idempotency_key"),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_run_steps_status",
        ),
    )
    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("dataset_version_id", sa.String(), sa.ForeignKey("files.id"), nullable=False),
        sa.Column("run_id", sa.String(), sa.ForeignKey("analysis_runs.id"), nullable=False),
        sa.Column("run_step_id", sa.String(), sa.ForeignKey("run_steps.id"), nullable=False),
        sa.Column("source_artifact_id", sa.String(), sa.ForeignKey("artifacts.id")),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content_format", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("storage_backend", sa.String(), nullable=False),
        sa.Column("storage_key", sa.String(1024)),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.BigInteger()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "artifact_type IN ('text','metric','table','chart')",
            name="ck_artifacts_type",
        ),
        sa.CheckConstraint(
            "status IN ('creating','ready','failed')",
            name="ck_artifacts_status",
        ),
    )
    op.create_table(
        "run_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_step_id",
            sa.String(),
            sa.ForeignKey("run_steps.id", ondelete="SET NULL"),
        ),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "sequence"),
    )


def downgrade() -> None:
    op.drop_table("run_events")
    op.drop_table("artifacts")
    op.drop_table("run_steps")
    op.drop_table("analysis_runs")
