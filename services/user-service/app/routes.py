import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from .database import get_db
from .models import User, UserInterest
from .schemas import UserCreate, UserResponse, InterestCreate, InterestResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"service": "user-service", "status": "ok"}


@router.post("/users", status_code=201, response_model=UserResponse)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        display_name=body.display_name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")
    return user


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/users/{user_id}/interests", response_model=list[InterestResponse])
async def get_interests(user_id: str, db: AsyncSession = Depends(get_db)):
    user_result = await db.execute(select(User).where(User.id == user_id))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")
    result = await db.execute(
        select(UserInterest).where(UserInterest.user_id == user_id)
    )
    return result.scalars().all()


@router.post("/users/{user_id}/interests", status_code=201, response_model=InterestResponse)
async def add_interest(user_id: str, body: InterestCreate, db: AsyncSession = Depends(get_db)):
    user_result = await db.execute(select(User).where(User.id == user_id))
    if not user_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found")
    now = datetime.now(timezone.utc)
    stmt = pg_insert(UserInterest).values(
        id=str(uuid.uuid4()),
        user_id=user_id,
        tag=body.tag,
        score=body.score,
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=["user_id", "tag"],
        set_={"score": body.score, "updated_at": now},
    )
    await db.execute(stmt)
    await db.commit()
    result = await db.execute(
        select(UserInterest).where(
            UserInterest.user_id == user_id,
            UserInterest.tag == body.tag,
        )
    )
    return result.scalar_one()
