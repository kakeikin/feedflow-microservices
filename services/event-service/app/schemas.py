from datetime import datetime
from typing import Literal
from pydantic import BaseModel

EventType = Literal["watch", "like", "skip", "complete", "share", "comment"]


class EventCreate(BaseModel):
    user_id: str
    video_id: str
    event_type: EventType
    completion_rate: float | None = None
    watch_time_seconds: int | None = None
    idempotency_key: str


class EventResponse(BaseModel):
    id: str
    user_id: str
    video_id: str
    event_type: str
    completion_rate: float | None = None
    watch_time_seconds: int | None = None
    idempotency_key: str
    created_at: datetime

    model_config = {"from_attributes": True}
