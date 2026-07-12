import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.automation import TaskCreate, TaskResponse, PlanResponse, ApiResponse
from app.services.automation.task_service import TaskService
from app.services.automation.planning_service import PlanningService

router = APIRouter()
task_service = TaskService()
planning_service = PlanningService()


@router.post("/tasks", response_model=ApiResponse[TaskResponse], status_code=status.HTTP_201_CREATED)
async def create_task(
    task_in: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Creates a new goal-driven automation task in the system."""
    try:
        task = await task_service.create_task(
            db=db,
            user_id=current_user.id,
            goal=task_in.goal,
            conversation_id=task_in.conversation_id
        )
        return ApiResponse(success=True, message="Task created successfully", data=task)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/tasks", response_model=ApiResponse[List[TaskResponse]])
async def list_tasks(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Lists all active automation tasks for the authenticated user."""
    tasks = await task_service.list_tasks(db=db, user_id=current_user.id, limit=limit, offset=offset)
    return ApiResponse(success=True, message="Tasks retrieved successfully", data=tasks)


@router.get("/tasks/{task_id}", response_model=ApiResponse[TaskResponse])
async def get_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetches details of a specific automation task, including generated plans."""
    task = await task_service.get_task(db=db, task_id=task_id, user_id=current_user.id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or access denied."
        )
    return ApiResponse(success=True, message="Task retrieved successfully", data=task)


@router.get("/plans/{plan_id}", response_model=ApiResponse[PlanResponse])
async def get_plan(
    plan_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Fetches an execution plan by its ID."""
    plan = await planning_service.get_plan(db=db, plan_id=plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found."
        )
    
    # Simple security verification: check if task is owned by the user
    task = await task_service.get_task(db=db, task_id=plan.task_id, user_id=current_user.id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this execution plan."
        )
    return ApiResponse(success=True, message="Plan retrieved successfully", data=plan)


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse[TaskResponse])
async def cancel_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Aborts/cancels task execution, transitioning state to CANCELLED."""
    try:
        task = await task_service.cancel_task(db=db, task_id=task_id, user_id=current_user.id)
        return ApiResponse(success=True, message="Task cancelled successfully", data=task)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/tasks/{task_id}/retry", response_model=ApiResponse[TaskResponse])
async def retry_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retries a failed task, transitioning state back to RETRYING/EXECUTING."""
    try:
        task = await task_service.retry_task(db=db, task_id=task_id, user_id=current_user.id)
        return ApiResponse(success=True, message="Task queued for retry successfully", data=task)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
