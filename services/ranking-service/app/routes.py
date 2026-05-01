from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from . import clients
from .schemas import RankRequest, RankItem
from .ranking import (
    compute_interest_match,
    compute_freshness,
    compute_engagement,
    compute_completion_quality,
    compute_final_score,
)

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "ranking-service", "status": "ok"}


@router.post("/rank", response_model=list[RankItem])
async def rank_videos(body: RankRequest) -> list[RankItem]:
    user_interests = await clients.get_user_interests(body.user_id)

    videos = []
    for video_id in body.candidate_video_ids:
        video = await clients.get_video(video_id)
        if video is not None:
            videos.append(video)

    if not videos:
        return []

    max_net_engagement = max(
        max(0, v.get("stats", {}).get("likes", 0) - v.get("stats", {}).get("skips", 0))
        for v in videos
    )

    results = []
    for video in videos:
        stats = video.get("stats", {})
        tags = video.get("tags", [])
        created_at_str = video.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            created_at = datetime.now(timezone.utc) - timedelta(days=9)  # beyond 7-day decay window → freshness=0.0

        interest = compute_interest_match(tags, user_interests)
        freshness = compute_freshness(created_at)
        engagement = compute_engagement(
            stats.get("likes", 0),
            stats.get("skips", 0),
            max_net_engagement,
        )
        completion_quality = compute_completion_quality(stats.get("completion_rate", 0.0))
        score = compute_final_score(interest, freshness, engagement, completion_quality)

        matched_tags = [t for t in tags if any(i["tag"] == t for i in user_interests)]
        reason = (
            f"matched user interest tags: {', '.join(matched_tags)}"
            if matched_tags
            else "no interest match"
        )

        results.append(RankItem(video_id=video["id"], score=score, reason=reason))

    results.sort(key=lambda x: x.score, reverse=True)
    return results
