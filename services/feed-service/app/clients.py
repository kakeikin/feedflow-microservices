import os
import httpx

VIDEO_SERVICE_URL = os.environ.get("VIDEO_SERVICE_URL", "http://video-service:8002")
RANKING_SERVICE_URL = os.environ.get("RANKING_SERVICE_URL", "http://ranking-service:8004")


async def get_trending_videos() -> list[dict]:
    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.get(f"{VIDEO_SERVICE_URL}/videos/trending")
        response.raise_for_status()
        return response.json()


async def rank_videos(user_id: str, video_ids: list[str]) -> list[dict]:
    async with httpx.AsyncClient(timeout=3.0) as client:
        response = await client.post(
            f"{RANKING_SERVICE_URL}/rank",
            json={"user_id": user_id, "candidate_video_ids": video_ids},
        )
        response.raise_for_status()
        return response.json()
