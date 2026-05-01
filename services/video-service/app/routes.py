import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from .database import get_db
from .models import Video, VideoStats
from .schemas import VideoCreate, VideoResponse, StatsDelta, StatsResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "video-service", "status": "ok"}


@router.post("/videos", status_code=201, response_model=VideoResponse)
async def create_video(body: VideoCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    video_id = str(uuid.uuid4())
    video = Video(
        id=video_id,
        title=body.title,
        creator_id=body.creator_id,
        tags=body.tags,
        duration_seconds=body.duration_seconds,
        created_at=now,
    )
    db.add(video)
    # Atomic: create stats alongside video in same transaction
    stats = VideoStats(id=str(uuid.uuid4()), video_id=video_id, updated_at=now)
    db.add(stats)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Constraint violation")
    # Reload with selectinload to ensure stats relationship is populated for response serialization
    result = await db.execute(
        select(Video).options(selectinload(Video.stats)).where(Video.id == video_id)
    )
    return result.scalar_one()


@router.get("/videos", response_model=list[VideoResponse])
async def list_videos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).options(selectinload(Video.stats)))
    return result.scalars().all()


# CRITICAL: /videos/trending MUST be defined before /videos/{video_id}
@router.get("/videos/trending", response_model=list[VideoResponse])
async def get_trending(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video)
        .options(selectinload(Video.stats))
        .join(VideoStats, Video.id == VideoStats.video_id)
        .order_by(VideoStats.likes.desc(), VideoStats.views.desc(), Video.created_at.desc())
        .limit(20)
    )
    return result.scalars().all()


@router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(video_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Video).options(selectinload(Video.stats)).where(Video.id == video_id)
    )
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.patch("/videos/{video_id}/stats", response_model=StatsResponse)
async def patch_stats(video_id: str, body: StatsDelta, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Video).where(Video.id == video_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Video not found")

    values = {
        "views": VideoStats.views + body.views_delta,
        "likes": VideoStats.likes + body.likes_delta,
        "skips": VideoStats.skips + body.skips_delta,
        "updated_at": datetime.now(timezone.utc),
    }
    if body.completion_rate_sample is not None:
        # Uses pre-increment VideoStats.views (old value before views_delta is applied)
        values["completion_rate"] = (
            (VideoStats.completion_rate * VideoStats.views + body.completion_rate_sample)
            / (VideoStats.views + 1)
        )

    stmt = (
        update(VideoStats)
        .where(VideoStats.video_id == video_id)
        .values(**values)
        .returning(
            VideoStats.views,
            VideoStats.likes,
            VideoStats.skips,
            VideoStats.completion_rate,
        )
    )
    result = await db.execute(stmt)
    row = result.fetchone()
    await db.commit()
    return StatsResponse(
        views=row.views,
        likes=row.likes,
        skips=row.skips,
        completion_rate=row.completion_rate,
    )
