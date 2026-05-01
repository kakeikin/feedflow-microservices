from datetime import datetime
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    email: str
    display_name: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InterestCreate(BaseModel):
    tag: str
    score: float = Field(ge=0.0, le=1.0)


class InterestResponse(BaseModel):
    tag: str
    score: float

    model_config = {"from_attributes": True}


class InterestDelta(BaseModel):
    delta: float
