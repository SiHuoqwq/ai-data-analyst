import uuid

from app.v2.db.models import AnalysisRunModel, RunEventModel, utc_now
from app.v2.schemas.events import EVENT_PAYLOAD_MODELS, EventEnvelope


class EventEmitter:
    def emit(
        self,
        session,
        run: AnalysisRunModel,
        event_type: str,
        payload: dict,
        run_step_id: str | None = None,
    ) -> RunEventModel:
        payload_model = EVENT_PAYLOAD_MODELS[event_type]
        validated_payload = payload_model.model_validate(payload).model_dump(mode="json")
        run.last_event_sequence += 1
        timestamp = utc_now()
        event_id = str(uuid.uuid4())
        envelope = EventEnvelope(
            event_id=event_id,
            event_type=event_type,
            run_id=run.id,
            sequence=run.last_event_sequence,
            timestamp=timestamp,
            payload=validated_payload,
        )
        event = RunEventModel(
            id=event_id,
            run_id=run.id,
            run_step_id=run_step_id,
            sequence=run.last_event_sequence,
            event_type=event_type,
            schema_version=envelope.schema_version,
            payload_json=validated_payload,
            created_at=timestamp,
        )
        session.add(event)
        return event
