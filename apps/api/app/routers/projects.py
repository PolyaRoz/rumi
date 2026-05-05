import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import CurrentUser
from app.models.project import Project, Room
from app.schemas.common import ApiResponse
from app.schemas.project import (
    CreateProjectRequest,
    CreateRoomRequest,
    ProjectSchema,
    RoomSchema,
    UpdateProjectRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ApiResponse[list[ProjectSchema]])
async def list_projects(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return ApiResponse(data=[ProjectSchema.model_validate(p) for p in projects])


@router.post("", response_model=ApiResponse[ProjectSchema], status_code=201)
async def create_project(
    body: CreateProjectRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    project = Project(
        user_id=current_user.id,
        name=body.name,
        segment=body.segment,
        budget_rub=body.budget_rub,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ApiResponse(data=ProjectSchema.model_validate(project))


@router.get("/{project_id}", response_model=ApiResponse[ProjectSchema])
async def get_project(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return ApiResponse(data=ProjectSchema.model_validate(project))


@router.patch("/{project_id}", response_model=ApiResponse[ProjectSchema])
async def update_project(
    project_id: uuid.UUID,
    body: UpdateProjectRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if body.name is not None:
        project.name = body.name
    if body.budget_rub is not None:
        project.budget_rub = body.budget_rub

    await db.commit()
    await db.refresh(project)
    return ApiResponse(data=ProjectSchema.model_validate(project))


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()


@router.get("/{project_id}/rooms", response_model=ApiResponse[list[RoomSchema]])
async def list_rooms(
    project_id: uuid.UUID,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Room).where(Room.project_id == project_id).order_by(Room.created_at)
    )
    rooms = result.scalars().all()
    return ApiResponse(data=[RoomSchema.model_validate(r) for r in rooms])


@router.post("/{project_id}/rooms", response_model=ApiResponse[RoomSchema], status_code=201)
async def create_room(
    project_id: uuid.UUID,
    body: CreateRoomRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    room = Room(
        project_id=project_id,
        room_type=body.room_type,
        style=body.style,
        budget_rub=body.budget_rub,
        area_sqm=body.area_sqm,
        notes=body.notes,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return ApiResponse(data=RoomSchema.model_validate(room))
