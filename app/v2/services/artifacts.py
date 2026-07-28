import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.v2.db.models import ArtifactModel, AnalysisRunModel, RunStepModel, utc_now
from app.v2.schemas.artifacts import (
    ChartArtifactPayload,
    MetricArtifactPayload,
    TableArtifactPayload,
    TextArtifactPayload,
)


PAYLOAD_MODELS = {
    "text": TextArtifactPayload,
    "metric": MetricArtifactPayload,
    "table": TableArtifactPayload,
    "chart": ChartArtifactPayload,
}


@dataclass
class ArtifactDraft:
    artifact_type: str
    title: str
    content_format: str
    payload: dict | None = None
    row_count: int | None = None
    chart_filepath: str | None = None
    chart_type: str | None = None
    alt_text: str | None = None


class ArtifactFactory:
    def create(
        self,
        session,
        run: AnalysisRunModel,
        step: RunStepModel,
        draft: ArtifactDraft,
    ) -> ArtifactModel:
        artifact_id = str(uuid.uuid4())
        storage_key = None
        storage_backend = "inline"

        if draft.artifact_type == "chart":
            chart_path = Path(draft.chart_filepath or "").resolve()
            chart_root = Path(settings.chart_dir).resolve()
            if chart_root not in chart_path.parents:
                raise ValueError("chart file is outside managed storage")
            storage_key = chart_path.name
            storage_backend = "local"
            payload = {
                "renderer": "static-image",
                "chart_type": draft.chart_type,
                "title": draft.title,
                "image_url": f"/api/v2/artifacts/{artifact_id}/download",
                "alt_text": draft.alt_text,
            }
            content_bytes = chart_path.read_bytes()
        else:
            payload = draft.payload or {}
            content_bytes = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")

        validated_payload = PAYLOAD_MODELS[draft.artifact_type].model_validate(
            payload
        ).model_dump(mode="json")
        now = utc_now()
        artifact = ArtifactModel(
            id=artifact_id,
            dataset_version_id=run.dataset_version_id,
            run_id=run.id,
            run_step_id=step.id,
            artifact_type=draft.artifact_type,
            status="ready",
            title=draft.title,
            content_format=draft.content_format,
            payload_json=validated_payload,
            storage_backend=storage_backend,
            storage_key=storage_key,
            sha256=hashlib.sha256(content_bytes).hexdigest(),
            size_bytes=len(content_bytes),
            row_count=draft.row_count,
            created_at=now,
            updated_at=now,
            ready_at=now,
        )
        session.add(artifact)
        return artifact
