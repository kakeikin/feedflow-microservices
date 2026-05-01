from fastapi import APIRouter, HTTPException
from . import clients
from .schemas import FeedItem, FeedResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "feed-service", "status": "ok"}


@router.get("/feed/{user_id}", response_model=FeedResponse)
async def get_feed(user_id: str) -> FeedResponse:
    try:
        trending = await clients.get_trending_videos()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Video service unavailable") from exc

    candidate_ids = [v["id"] for v in trending]

    try:
        ranked = await clients.rank_videos(user_id, candidate_ids)
        items = [
            FeedItem(video_id=r["video_id"], score=r["score"], reason=r["reason"])
            for r in ranked
        ]
        return FeedResponse(user_id=user_id, source="personalized_ranking", items=items)
    except Exception:
        # Graceful degradation: ranking service unavailable or non-2xx (spec-defined fallback)
        items = [
            FeedItem(video_id=v["id"], score=0.0, reason="trending_fallback")
            for v in trending
        ]
        return FeedResponse(user_id=user_id, source="trending_fallback", items=items)
