import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get("DATABASE_URL", "")

engine = create_async_engine(DATABASE_URL) if DATABASE_URL else None
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False) if engine else None


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
