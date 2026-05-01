import os
import httpx

USER_SERVICE_URL = os.environ.get("USER_SERVICE_URL", "http://user-service:8001")
VIDEO_SERVICE_URL = os.environ.get("VIDEO_SERVICE_URL", "http://video-service:8002")


async def get_user_interests(user_id: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{USER_SERVICE_URL}/users/{user_id}/interests")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        return []


async def get_video(video_id: str) -> dict | None:
    """Returns video data dict or None if the fetch fails for any reason."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{VIDEO_SERVICE_URL}/videos/{video_id}")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        return None
