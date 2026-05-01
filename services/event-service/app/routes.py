import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .database import get_db
from .models import Event
from .schemas import EventCreate, EventResponse
from . import publisher

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "event-service", "status": "ok"}


@router.post("/events")
async def create_event(
    body: EventCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    event = Event(
        id=str(uuid.uuid4()),
        user_id=body.user_id,
        video_id=body.video_id,
        event_type=body.event_type,
        completion_rate=body.completion_rate,
        watch_time_seconds=body.watch_time_seconds,
        idempotency_key=body.idempotency_key,
        created_at=datetime.now(timezone.utc),
    )
    db.add(event)
    try:
        await db.commit()
        event_data = {
            "event_id": event.id,
            "user_id": event.user_id,
            "video_id": event.video_id,
            "event_type": event.event_type,
            "completion_rate": event.completion_rate,
            "watch_time_seconds": event.watch_time_seconds,
        }
        background_tasks.add_task(publisher.publish_event, event_data)
        return JSONResponse(status_code=201, content={"id": event.id, "status": "created"})
    except IntegrityError as exc:
        await db.rollback()
        pg_code = getattr(exc.orig, "pgcode", None)
        if pg_code == "23505":
            return JSONResponse(status_code=200, content={"status": "duplicate_ignored"})
        raise


@router.get("/events", response_model=list[EventResponse])
async def list_events(user_id: str | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Event)
    if user_id:
        query = query.where(Event.user_id == user_id)
    result = await db.execute(query)
    return result.scalars().all()
