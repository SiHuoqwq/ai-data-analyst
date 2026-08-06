import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from app.db.database import Base


V2Base = Base


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def as_utc(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


class AnalysisRunModel(V2Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        UniqueConstraint("conversation_id", "idempotency_key"),
        CheckConstraint(
            "status IN ('queued','running','completed','failed','cancelled')",
            name="ck_analysis_runs_status",
        ),
    )

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    dataset_version_id = Column(String, ForeignKey("files.id"), nullable=False)
    trigger_message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    answer_message_id = Column(String, ForeignKey("messages.id"), nullable=True)
    parent_run_id = Column(String, ForeignKey("analysis_runs.id"), nullable=True)
    retry_of_run_id = Column(String, ForeignKey("analysis_runs.id"), nullable=True)
    status = Column(String, nullable=False)
    current_phase = Column(String, nullable=True)
    context_snapshot_json = Column(JSON, nullable=False, default=dict)
    progress_json = Column(JSON, nullable=False, default=dict)
    failure_json = Column(JSON, nullable=True)
    requested_by = Column(String, nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    model_config_json = Column(JSON, nullable=False, default=dict)
    last_event_sequence = Column(BigInteger, nullable=False, default=0)
    cancel_requested_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)


class RunStepModel(V2Base):
    __tablename__ = "run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence"),
        UniqueConstraint("run_id", "idempotency_key"),
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_run_steps_status",
        ),
    )

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("analysis_runs.id"), nullable=False)
    plan_step_id = Column(String(100), nullable=True)
    sequence = Column(Integer, nullable=False)
    phase = Column(String, nullable=False)
    operation = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
    status = Column(String, nullable=False)
    input_json = Column(JSON, nullable=False, default=dict)
    output_summary_json = Column(JSON, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=1)
    idempotency_key = Column(String(160), nullable=False)
    error_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)


class ArtifactModel(V2Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('text','metric','table','chart')",
            name="ck_artifacts_type",
        ),
        CheckConstraint(
            "status IN ('creating','ready','failed')",
            name="ck_artifacts_status",
        ),
    )

    id = Column(String, primary_key=True)
    dataset_version_id = Column(String, ForeignKey("files.id"), nullable=False)
    run_id = Column(String, ForeignKey("analysis_runs.id"), nullable=False)
    run_step_id = Column(String, ForeignKey("run_steps.id"), nullable=False)
    source_artifact_id = Column(String, ForeignKey("artifacts.id"), nullable=True)
    artifact_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    title = Column(String(300), nullable=False)
    content_format = Column(String(100), nullable=False)
    payload_json = Column(JSON, nullable=False)
    storage_backend = Column(String, nullable=False)
    storage_key = Column(String(1024), nullable=True)
    sha256 = Column(String(64), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    row_count = Column(BigInteger, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    ready_at = Column(DateTime(timezone=True), nullable=True)


class RunEventModel(V2Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)

    id = Column(String, primary_key=True)
    run_id = Column(
        String,
        ForeignKey("analysis_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_step_id = Column(
        String,
        ForeignKey("run_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    sequence = Column(BigInteger, nullable=False)
    event_type = Column(String, nullable=False)
    schema_version = Column(String(20), nullable=False, default="1.0")
    payload_json = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)


class DatasetRecommendationModel(V2Base):
    __tablename__ = "dataset_recommendations"
    __table_args__ = (
        CheckConstraint(
            "source IN ('model','template')",
            name="ck_dataset_recommendations_source",
        ),
    )

    id = Column(String, primary_key=True)
    dataset_version_id = Column(
        String,
        ForeignKey("files.id"),
        nullable=False,
        unique=True,
    )
    recommendations_json = Column(JSON, nullable=False)
    source = Column(String, nullable=False)
    provider_name = Column(String, nullable=True)
    provider_model = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
