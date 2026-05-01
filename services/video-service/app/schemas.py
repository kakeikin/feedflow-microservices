from datetime import datetime
from pydantic import BaseModel, Field


class VideoCreate(BaseModel):
    title: str = Field(min_length=1)
    creator_id: str
    tags: list[str]
    duration_seconds: int = Field(gt=0)


class VideoStatsResponse(BaseModel):
    views: int
    likes: int
    skips: int
    completion_rate: float

    model_config = {"from_attributes": True}


class VideoResponse(BaseModel):
    id: str
    title: str
    creator_id: str
    tags: list[str]
    duration_seconds: int
    created_at: datetime
    stats: VideoStatsResponse

    model_config = {"from_attributes": True}


class StatsDelta(BaseModel):
    views_delta: int = 0
    likes_delta: int = 0
    skips_delta: int = 0
    completion_rate_sample: float | None = None


class StatsResponse(BaseModel):
    views: int
    likes: int
    skips: int
    completion_rate: float
