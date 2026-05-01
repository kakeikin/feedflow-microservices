import os
import httpx

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://localhost:8001")
VIDEO_SERVICE_URL = os.environ.get("VIDEO_SERVICE_URL", "http://localhost:8002")


async def get_video(video_id: str) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{VIDEO_SERVICE_URL}/videos/{video_id}")
        response.raise_for_status()
        return response.json()


async def patch_video_stats(video_id: str, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.patch(
            f"{VIDEO_SERVICE_URL}/videos/{video_id}/stats",
            json=payload,
        )
        response.raise_for_status()


async def patch_user_interest(user_id: str, tag: str, delta: float) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.patch(
            f"{USER_SERVICE_URL}/users/{user_id}/interests/{tag}",
            json={"delta": delta},
        )
        response.raise_for_status()
