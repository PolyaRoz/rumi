import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Integer, Text, ForeignKey, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)

    name: Mapped[str] = mapped_column(String(255), default="Мой проект")
    budget_rub: Mapped[int | None] = mapped_column(Integer)
    segment: Mapped[str] = mapped_column(String(10), default="self")  # self | invest

    # Только для сегмента invest
    address: Mapped[str | None] = mapped_column(Text)
    rental_rate_rub: Mapped[int | None] = mapped_column(Integer)

    share_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship(back_populates="projects")
    rooms: Mapped[list["Room"]] = relationship(
        back_populates="project", lazy="selectin", cascade="all, delete-orphan"
    )


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)

    room_type: Mapped[str] = mapped_column(String(50))
    # living | bedroom | kitchen | office | bathroom | dining | hallway

    style: Mapped[str] = mapped_column(String(50))
    # scandinavian | modern | classic | loft | japandi | eclectic

    budget_rub: Mapped[int | None] = mapped_column(Integer)
    area_sqm: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="rooms")
    photos: Mapped[list["RoomPhoto"]] = relationship(
        back_populates="room", lazy="selectin", cascade="all, delete-orphan"
    )
    variants: Mapped[list["RoomVariant"]] = relationship(
        back_populates="room", lazy="selectin", cascade="all, delete-orphan"
    )


class RoomPhoto(Base):
    __tablename__ = "room_photos"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)

    s3_key: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    uploaded_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    room: Mapped["Room"] = relationship(back_populates="photos")


class RoomVariant(Base):
    __tablename__ = "room_variants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(64))

    index: Mapped[int] = mapped_column(Integer, default=0)
    style_label: Mapped[str | None] = mapped_column(String(100))
    image_s3_key: Mapped[str | None] = mapped_column(Text)
    thumbnail_s3_key: Mapped[str | None] = mapped_column(Text)

    prompt_used: Mapped[str | None] = mapped_column(Text)
    generation_seed: Mapped[int | None] = mapped_column(Integer)

    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    total_cost_rub: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    room: Mapped["Room"] = relationship(back_populates="variants")
