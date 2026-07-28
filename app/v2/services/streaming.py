import asyncio
import json
import time
import uuid

from app.db.database import SessionLocal
from app.v2.db.models import AnalysisRunModel, RunEventModel, as_utc, utc_now
from app.v2.schemas.events import EventEnvelope, HeartbeatPayload
from app.v2.services.runs import RunServiceError


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


def _wire_event(envelope: EventEnvelope) -> str:
    data = envelope.model_dump_json()
    return (
        f"id: {envelope.event_id}\n"
        f"event: {envelope.event_type}\n"
        f"data: {data}\n\n"
    )


class RunEventStream:
    def sequence_for_event(self, run_id: str, event_id: str) -> int:
        session = SessionLocal()
        try:
            event = (
                session.query(RunEventModel)
                .filter_by(id=event_id, run_id=run_id)
                .first()
            )
            if not event:
                raise RunServiceError(
                    "INVALID_EVENT_CURSOR", "事件游标无效", 400
                )
            return event.sequence
        finally:
            session.close()

    async def stream(self, request, run_id: str, after_sequence: int = 0):
        session = SessionLocal()
        try:
            run = session.get(AnalysisRunModel, run_id)
            if not run:
                raise RunServiceError("RUN_NOT_FOUND", "分析任务不存在", 404)
        finally:
            session.close()

        last_sequence = after_sequence
        last_heartbeat = time.monotonic()
        while True:
            if await request.is_disconnected():
                return
            session = SessionLocal()
            try:
                run = session.get(AnalysisRunModel, run_id)
                events = (
                    session.query(RunEventModel)
                    .filter(
                        RunEventModel.run_id == run_id,
                        RunEventModel.sequence > last_sequence,
                    )
                    .order_by(RunEventModel.sequence)
                    .all()
                )
                terminal = run.status in TERMINAL_STATUSES
                current_sequence = run.last_event_sequence
            finally:
                session.close()

            for event in events:
                envelope = EventEnvelope(
                    event_id=event.id,
                    event_type=event.event_type,
                    run_id=event.run_id,
                    sequence=event.sequence,
                    timestamp=as_utc(event.created_at),
                    schema_version=event.schema_version,
                    payload=event.payload_json,
                )
                last_sequence = event.sequence
                yield _wire_event(envelope)

            if terminal and last_sequence >= current_sequence:
                return

            if not events and time.monotonic() - last_heartbeat >= 15:
                now = utc_now()
                payload = HeartbeatPayload(
                    server_time=now.isoformat().replace("+00:00", "Z"),
                    last_event_sequence=current_sequence,
                ).model_dump(mode="json")
                heartbeat = EventEnvelope(
                    event_id=str(uuid.uuid4()),
                    event_type="heartbeat",
                    run_id=run_id,
                    sequence=max(current_sequence, 1),
                    timestamp=now,
                    payload=payload,
                )
                yield _wire_event(heartbeat)
                last_heartbeat = time.monotonic()

            await asyncio.sleep(0.05)
