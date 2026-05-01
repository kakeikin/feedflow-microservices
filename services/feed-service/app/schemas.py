from pydantic import BaseModel


class FeedItem(BaseModel):
    video_id: str
    score: float
    reason: str


class FeedResponse(BaseModel):
    user_id: str
    source: str
    items: list[FeedItem]
