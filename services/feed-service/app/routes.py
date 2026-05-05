import logging
from fastapi import APIRouter, HTTPException
from . import clients, cache
from .schemas import FeedItem, FeedResponse
from .metrics import FEED_CACHE_HIT_TOTAL, FEED_CACHE_MISS_TOTAL, FEED_FALLBACK_TOTAL

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "feed-service", "status": "ok"}


@router.get("/feed/{user_id}", response_model=FeedResponse)
async def get_feed(user_id: str) -> FeedResponse:
    cached = await cache.get_feed(user_id)
    if cached is not None:
        FEED_CACHE_HIT_TOTAL.inc()
        items = [FeedItem(**item) for item in cached]
        return FeedResponse(user_id=user_id, source="cache_hit", items=items)

    FEED_CACHE_MISS_TOTAL.inc()

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
        await cache.set_feed(user_id, [item.model_dump() for item in items])
        return FeedResponse(user_id=user_id, source="personalized_ranking", items=items)
    except Exception as exc:
        logger.warning("Ranking failed for user %s, falling back to trending: %s", user_id, exc)
        FEED_FALLBACK_TOTAL.inc()
        items = [
            FeedItem(video_id=v["id"], score=0.0, reason="trending_fallback")
            for v in trending
        ]
        return FeedResponse(user_id=user_id, source="trending_fallback", items=items)
