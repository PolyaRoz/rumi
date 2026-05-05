import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    name: str = Field(default="Мой проект", max_length=255)
    segment: Literal["self", "invest"] = "self"
    budget_rub: int | None = Field(None, ge=0)


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(None, max_length=255)
    budget_rub: int | None = Field(None, ge=0)


class CreateRoomRequest(BaseModel):
    room_type: Literal[
        "living", "bedroom", "kitchen", "office",
        "bathroom", "dining", "hallway"
    ]
    style: Literal[
        "scandinavian", "modern", "classic",
        "loft", "japandi", "eclectic"
    ]
    budget_rub: int | None = Field(None, ge=0)
    area_sqm: float | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=2000)


class RoomSchema(BaseModel):
    id: uuid.UUID
    room_type: str
    style: str
    budget_rub: int | None
    area_sqm: float | None
    notes: str | None
    photos_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectSchema(BaseModel):
    id: uuid.UUID
    name: str
    segment: str
    budget_rub: int | None
    created_at: datetime
    updated_at: datetime
    rooms: list[RoomSchema] = []

    model_config = {"from_attributes": True}
