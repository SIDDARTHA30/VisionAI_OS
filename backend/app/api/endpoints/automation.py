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


# ─── Milestone 4.2: Enterprise Tool Framework & Plugin Architecture Endpoints ───

from app.tools.registry import tool_registry
from app.tools.factory import ToolFactory
from app.tools.manager import ToolManager
from app.tools.context import ToolContext
from app.tools.result import ToolResult
from app.tools.schemas import ToolHealth
from pydantic import BaseModel, Field
import tempfile
from pathlib import Path
from typing import Dict, Optional


class ToolExecuteRequest(BaseModel):
    arguments: dict
    session_id: Optional[uuid.UUID] = None
    config: Optional[dict] = None


@router.get("/tools", response_model=ApiResponse[List[dict]])
async def list_registered_tools(current_user: User = Depends(get_current_user)):
    """List all registered pluggable tools and their schemas."""
    tools_list = []
    for tool in tool_registry.list():
        tools_list.append(tool.metadata.model_dump())
    return ApiResponse(success=True, message="Tools list retrieved successfully", data=tools_list)


@router.get("/tools/health", response_model=ApiResponse[Dict[str, ToolHealth]])
async def check_tools_health(current_user: User = Depends(get_current_user)):
    """Run health checks on all registered tool dependencies."""
    health_results = {}
    for tool in tool_registry.list():
        health_results[tool.metadata.name] = await tool.health_check()
    return ApiResponse(success=True, message="Tools health check completed", data=health_results)


@router.post("/tools/{name}/execute", response_model=ApiResponse[ToolResult])
async def execute_tool_endpoint(
    name: str,
    exec_req: ToolExecuteRequest,
    current_user: User = Depends(get_current_user)
):
    """Test execution harness for invoking tools synchronously."""
    try:
        tool = ToolFactory.create(name)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{name}' not found in registry."
        )

    # Instantiate temporary workspace paths
    with tempfile.TemporaryDirectory() as tmp_dir:
        workspace_path = Path(tmp_dir) / "workspace"
        workspace_path.mkdir(parents=True, exist_ok=True)
        temp_path = Path(tmp_dir) / "temp"
        temp_path.mkdir(parents=True, exist_ok=True)

        context = ToolContext(
            request_id=uuid.uuid4(),
            trace_id=uuid.uuid4(),
            session_id=exec_req.session_id or uuid.uuid4(),
            user_id=current_user.id,
            correlation_id=uuid.uuid4(),
            logger=logging.getLogger(f"app.tools.execution.{name}"),
            workspace=workspace_path,
            temp_dir=temp_path,
            config=exec_req.config or {}
        )

        manager = ToolManager()
        result = await manager.execute_tool(tool, exec_req.arguments, context)
        return ApiResponse(success=result.success, message="Execution finished", data=result)


# ─── Milestone 4.3: AI Planner & Goal Decomposition Engine Endpoints ───

from app.services.automation.planning_service import PlanningService


class PlanValidateDryRunRequest(BaseModel):
    goal: str = Field(..., min_length=5, description="Goal objective to dry-run validation.")


@router.post("/tasks/{task_id}/plan", response_model=ApiResponse[PlanResponse])
async def execute_task_planning(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Triggers autonomous goal decomposition via Gemini and returns the saved Plan."""
    planning_srv = PlanningService()
    try:
        plan = await planning_srv.generate_plan_from_goal(db=db, task_id=task_id, user_id=current_user.id)
        return ApiResponse(success=True, message="Plan generated successfully", data=plan)
    except (TaskNotFoundError, InvalidStateTransitionError) as ie:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ie))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Planning execution failed: {str(e)}")


@router.post("/tasks/{task_id}/plan/validate", response_model=ApiResponse[dict])
async def validate_plan_dry_run(
    task_id: uuid.UUID,
    validate_req: PlanValidateDryRunRequest,
    current_user: User = Depends(get_current_user)
):
    """Runs a dry-run planner generation and validation without database writes."""
    planning_srv = PlanningService()
    try:
        plan_dict = await planning_srv.validate_plan_from_goal_dry_run(task_id=task_id, goal=validate_req.goal)
        return ApiResponse(success=True, message="Plan validated successfully", data=plan_dict)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Dry-run validation failed: {str(e)}")


@router.get("/planner/health", response_model=ApiResponse[dict])
async def check_planner_health(current_user: User = Depends(get_current_user)):
    """Evaluate planning connection checks and registry status."""
    registry_size = len(tool_registry.list())
    gemini_status = "HEALTHY" if settings.GOOGLE_API_KEY else "DEGRADED"

    data = {
        "status": "HEALTHY" if registry_size > 0 and gemini_status == "HEALTHY" else "DEGRADED",
        "gemini_connectivity": gemini_status,
        "tool_registry_available": "HEALTHY" if registry_size > 0 else "UNHEALTHY",
        "registered_tools_count": registry_size,
        "last_checked": datetime.now(timezone.utc)
    }
    return ApiResponse(success=True, message="Planner health verification completed", data=data)


# ─── Milestone 4.4: Enterprise AI Execution Engine & Orchestrator Endpoints ───

from app.services.automation.execution_orchestrator import ExecutionOrchestrator
from app.services.automation.execution_policy import execution_policy
from app.services.automation.resource_manager import resource_manager

orchestrator = ExecutionOrchestrator()


@router.post("/tasks/{task_id}/execute", status_code=status.HTTP_202_ACCEPTED)
async def execute_task_endpoint(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Triggers the execution orchestrator run in the background."""
    task = await TaskRepository().get_by_id(db, task_id, current_user.id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    # Execute asynchronously in background task loop
    asyncio.create_task(orchestrator.execute_task_plan(task_id, current_user.id))

    return ApiResponse(
        success=True,
        message="Task execution loop started asynchronously",
        data={"task_id": str(task_id), "status": "QUEUED"}
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task_endpoint(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Signals graceful cancellation to terminate active steps."""
    task = await TaskRepository().get_by_id(db, task_id, current_user.id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    await orchestrator.cancel_task(task_id, current_user.id)
    return ApiResponse(success=True, message="Task cancellation triggered successfully", data=None)


@router.get("/tasks/{task_id}/status")
async def get_task_status_endpoint(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Retrieves overall task state and progress values."""
    task = await TaskRepository().get_by_id(db, task_id, current_user.id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found.")

    # Find the latest plan
    stmt = select(Plan).where(Plan.task_id == task_id, Plan.is_latest == True).options(selectinload(Plan.steps))
    res = await db.execute(stmt)
    plan = res.scalars().first()

    steps_data = []
    if plan and plan.steps:
        for s in plan.steps:
            steps_data.append({
                "step_number": s.step_number,
                "tool_name": s.tool_name,
                "status": s.status,
                "completed_at": s.completed_at
            })

    return ApiResponse(
        success=True,
        message="Task status retrieved successfully",
        data={
            "task_id": str(task_id),
            "status": task.status,
            "version": task.version,
            "steps": steps_data
        }
    )


@router.get("/tasks/{task_id}/logs")
async def get_task_logs_endpoint(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns accumulated stdout logs from execution steps."""
    stmt = select(Plan).where(Plan.task_id == task_id, Plan.is_latest == True)
    res = await db.execute(stmt)
    plan = res.scalars().first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution plan not found.")

    stmt_exec = select(Execution).where(Execution.plan_id == plan.id).order_by(Execution.created_at.desc())
    res_exec = await db.execute(stmt_exec)
    execution = res_exec.scalars().first()
    if not execution:
        return ApiResponse(success=True, message="No execution history found", data="")

    return ApiResponse(success=True, message="Execution logs retrieved successfully", data=execution.logs or "")


@router.get("/tasks/{task_id}/results")
async def get_task_results_endpoint(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Returns compiled execution output results."""
    stmt = select(Plan).where(Plan.task_id == task_id, Plan.is_latest == True).options(selectinload(Plan.steps))
    res = await db.execute(stmt)
    plan = res.scalars().first()
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

    results = {}
    if plan.steps:
        for s in plan.steps:
            if s.result_output:
                results[f"step_{s.step_number}"] = s.result_output

    return ApiResponse(success=True, message="Execution results retrieved successfully", data=results)


@router.get("/executor/health")
async def get_executor_health(current_user: User = Depends(get_current_user)):
    """Evaluate orchestrator queue status, policy validations and workspace directory structures."""
    registry_size = len(tool_registry.list())
    data = {
        "status": "HEALTHY" if registry_size > 0 else "DEGRADED",
        "orchestrator": "ACTIVE",
        "tool_registry_available": "HEALTHY" if registry_size > 0 else "UNHEALTHY",
        "policy_active": True,
        "max_concurrency_limit": execution_policy.max_parallel_steps,
        "registered_subprocesses": len(resource_manager._active_subprocesses)
    }
    return ApiResponse(success=True, message="Orchestrator health check verified", data=data)

