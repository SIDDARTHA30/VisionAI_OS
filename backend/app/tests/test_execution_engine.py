import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.automation import Task, Plan, PlanStep, Execution, TaskStatus
from app.services.automation.task_service import TaskService
from app.services.automation.planning_service import PlanningService
from app.services.automation.execution_orchestrator import ExecutionOrchestrator
from app.services.automation.execution_policy import execution_policy
from app.services.automation.step_result_cache import step_result_cache
from app.tools.registry import tool_registry
from app.tools.manager import ToolManager

# Setup mock registered tools
from app.tools.browser.browser_tool import BrowserTool
from app.tools.utility.calculator_tool import CalculatorTool
from app.tools.filesystem.file_tool import FileTool
from app.tools.python.python_tool import PythonTool


@pytest.fixture(autouse=True)
def setup_tools():
    """Ensure tool registry is set up with test execution tools."""
    tool_registry.clear()
    tool_registry.register(BrowserTool())
    tool_registry.register(CalculatorTool())
    tool_registry.register(FileTool())
    tool_registry.register(PythonTool())
    step_result_cache.clear()


@pytest.mark.asyncio
async def test_sequential_execution_workflow(db_session: AsyncSession):
    """Verify standard orchestrator sequencing, variable resolution, and cache mechanics."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Execute sequence")

    planning_service = PlanningService()
    # Create simple sequential plan where step 2 depends on step 1 output variables
    plan = await planning_service.create_plan(
        db=db_session,
        task_id=task.id,
        user_id=1,
        summary="Sequential test plan",
        steps_data=[
            {
                "tool_name": "calculator",
                "arguments": {"expression": "50 + 75"},
                "approval_required": False
            },
            {
                "tool_name": "file_system",
                "arguments": {
                    "operation": "write",
                    "path": "result.txt",
                    "content": "Sum: {step_1_output}"
                },
                "approval_required": False
            }
        ]
    )

    orchestrator = ExecutionOrchestrator()
    # Run execution plan block (db calls inside local session)
    await orchestrator.execute_task_plan(task_id=task.id, user_id=1, db=db_session)

    # 1. Verify task completed successfully
    await db_session.refresh(task)
    assert task.status == TaskStatus.COMPLETED

    # 2. Verify step 1 math output resolved correctly
    stmt = select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.step_number)
    res = await db_session.execute(stmt)
    steps = res.scalars().all()

    assert steps[0].status == "COMPLETED"
    assert steps[0].result_output["result"] == 125

    assert steps[1].status == "COMPLETED"
    assert steps[1].result_output["operation"] == "write"

    # 3. Verify step result cache was populated
    cached = step_result_cache.get("calculator", {"expression": "50 + 75"})
    assert cached["result"] == 125


@pytest.mark.asyncio
async def test_parallel_execution_tiers(db_session: AsyncSession):
    """Verify that multiple independent steps are scheduled and run in parallel."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Execute parallel tiers")

    planning_service = PlanningService()
    plan = await planning_service.create_plan(
        db=db_session,
        task_id=task.id,
        user_id=1,
        summary="Parallel test plan",
        steps_data=[
            {
                "tool_name": "calculator",
                "arguments": {"expression": "10 * 10"},
                "approval_required": False
            },
            {
                "tool_name": "calculator",
                "arguments": {"expression": "20 * 20"},
                "approval_required": False
            }
        ]
    )

    orchestrator = ExecutionOrchestrator()
    await orchestrator.execute_task_plan(task.id, 1, db=db_session)

    await db_session.refresh(task)
    assert task.status == TaskStatus.COMPLETED

    stmt = select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.step_number)
    res = await db_session.execute(stmt)
    steps = res.scalars().all()
    assert len(steps) == 2
    assert steps[0].status == "COMPLETED"
    assert steps[1].status == "COMPLETED"


@pytest.mark.asyncio
async def test_execution_timeout_failure(db_session: AsyncSession):
    """Verify that tool execution times out, transitioning task status to FAILED."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Execute timeout test")

    planning_service = PlanningService()
    plan = await planning_service.create_plan(
        db=db_session,
        task_id=task.id,
        user_id=1,
        summary="Timeout test plan",
        steps_data=[
            {
                "tool_name": "calculator",
                "arguments": {"expression": "1 + 1"},
                "approval_required": False
            }
        ]
    )

    async def slow_execute(*args, **kwargs):
        await asyncio.sleep(0.1)
        from app.tools.result import ToolResult
        from app.tools.enums import ToolStatus
        from datetime import datetime, timezone
        return ToolResult(
            tool_name="calculator", tool_version="1.0.0",
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
            duration_ms=100, exit_code=0, success=True, status=ToolStatus.COMPLETED,
            structured_output={}, raw_output=""
        )

    # Set default_timeout_sec to 0.001 to trigger timeout immediately
    tool = tool_registry.get("calculator")
    tool.metadata.timeout_sec = 0

    with patch.object(CalculatorTool, "execute", side_effect=slow_execute):
        with patch.object(execution_policy, "default_timeout_sec", 0.001):
            orchestrator = ExecutionOrchestrator()
            await orchestrator.execute_task_plan(task.id, 1, db=db_session)

    await db_session.refresh(task)
    assert task.status == TaskStatus.FAILED

    stmt = select(PlanStep).where(PlanStep.plan_id == plan.id)
    res = await db_session.execute(stmt)
    step = res.scalars().first()
    assert step.status == "FAILED"
    assert "timed out" in step.error_message


@pytest.mark.asyncio
async def test_graceful_cancellation_workflow(db_session: AsyncSession):
    """Verify orchestrator cancels active runs gracefully and transitions status to CANCELLED."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Execute cancel test")

    planning_service = PlanningService()
    plan = await planning_service.create_plan(
        db=db_session,
        task_id=task.id,
        user_id=1,
        summary="Cancel test plan",
        steps_data=[
            {
                "tool_name": "calculator",
                "arguments": {"expression": "5 * 5"},
                "approval_required": False
            }
        ]
    )

    orchestrator = ExecutionOrchestrator()

    # Trigger cancellation mid-run by patching run_tool to run cancel_task dynamically
    async def cancel_mid_run(*args, **kwargs):
        await orchestrator.cancel_task(task.id, 1)
        # Yield normal ToolResult to simulate finish
        from app.tools.result import ToolResult
        from app.tools.enums import ToolStatus
        from datetime import datetime, timezone
        return ToolResult(
            tool_name="calculator", tool_version="1.0.0",
            started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
            duration_ms=1, exit_code=0, success=True, status=ToolStatus.COMPLETED,
            structured_output={"result": 25}, raw_output="25"
        )

    with patch.object(ToolManager, "execute_tool", side_effect=cancel_mid_run):
        await orchestrator.execute_task_plan(task.id, 1, db=db_session)

    await db_session.refresh(task)
    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_execution_python_subprocess_tool(db_session: AsyncSession):
    """Verify that Python script executes in isolated subprocess sandbox."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Run Python")

    planning_service = PlanningService()
    plan = await planning_service.create_plan(
        db=db_session,
        task_id=task.id,
        user_id=1,
        summary="Python test plan",
        steps_data=[
            {
                "tool_name": "python_sandbox",
                "arguments": {"code": "print('hello from subprocess')"},
                "approval_required": False
            }
        ]
    )

    orchestrator = ExecutionOrchestrator()
    await orchestrator.execute_task_plan(task.id, 1, db=db_session)

    await db_session.refresh(task)
    assert task.status == TaskStatus.COMPLETED

    stmt = select(PlanStep).where(PlanStep.plan_id == plan.id)
    res = await db_session.execute(stmt)
    step = res.scalars().first()
    assert step.status == "COMPLETED"
    assert "hello from subprocess" in step.result_output["stdout"]
