from pydantic import BaseModel


class RankRequest(BaseModel):
    user_id: str
    candidate_video_ids: list[str]


class RankItem(BaseModel):
    video_id: str
    score: float
    reason: str
