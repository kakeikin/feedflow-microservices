import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class UserInterest(Base):
    __tablename__ = "user_interests"
    __table_args__ = (UniqueConstraint("user_id", "tag"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    tag: Mapped[str] = mapped_column(String, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
