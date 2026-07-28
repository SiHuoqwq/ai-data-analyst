import asyncio
import json
import time

from sqlalchemy.exc import IntegrityError

from app.db.database import SessionLocal
from app.v2.db.models import AnalysisRunModel, RunEventModel, as_utc, utc_now
from app.v2.schemas.events import EventEnvelope, HeartbeatPayload
from app.v2.services.events import EventEmitter
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
    def emit_heartbeat(self, run_id: str) -> RunEventModel | None:
        session = SessionLocal()
        try:
            run = session.get(AnalysisRunModel, run_id)
            if not run or run.status in TERMINAL_STATUSES:
                return None
            now = utc_now()
            if (
                run.heartbeat_at
                and (now - as_utc(run.heartbeat_at)).total_seconds() < 15
            ):
                return None
            payload = HeartbeatPayload(
                server_time=now.isoformat().replace("+00:00", "Z"),
                last_event_sequence=run.last_event_sequence + 1,
            ).model_dump(mode="json")
            event = EventEmitter().emit(session, run, "heartbeat", payload)
            run.heartbeat_at = now
            session.commit()
            session.refresh(event)
            session.expunge(event)
            return event
        except IntegrityError:
            # Another subscriber may have persisted the same interval heartbeat.
            # Its event will be observed by this subscriber on the next poll.
            session.rollback()
            return None
        finally:
            session.close()

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
                heartbeat = self.emit_heartbeat(run_id)
                if heartbeat:
                    envelope = EventEnvelope(
                        event_id=heartbeat.id,
                        event_type=heartbeat.event_type,
                        run_id=heartbeat.run_id,
                        sequence=heartbeat.sequence,
                        timestamp=as_utc(heartbeat.created_at),
                        schema_version=heartbeat.schema_version,
                        payload=heartbeat.payload_json,
                    )
                    last_sequence = heartbeat.sequence
                    yield _wire_event(envelope)
                last_heartbeat = time.monotonic()

            await asyncio.sleep(0.05)
