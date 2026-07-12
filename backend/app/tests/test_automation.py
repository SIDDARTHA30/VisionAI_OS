import pytest
import pytest_asyncio
import uuid
from typing import Any, Dict
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.automation import (
    Task,
    Plan,
    PlanStep,
    Execution,
    TaskEvent,
    ToolCall,
    Approval,
    WorkflowTemplate,
    TaskStatus,
)
from app.services.automation.state_machine import TaskStateMachine
from app.services.automation.task_service import TaskService
from app.services.automation.planning_service import PlanningService
from app.services.automation.execution_service import ExecutionService
from app.services.automation.approval_service import ApprovalService
from app.services.automation.exceptions import (
    AutomationError,
    InvalidStateTransitionError,
    ConcurrencyConflictError,
    TaskNotFoundError
)


# ─── 1. State Machine Unit Tests ──────────────────────────────────────────────

class TestStateMachine:
    """Verifies that the task state machine enforces transitions correctly."""

    def test_valid_transitions(self):
        # Valid moves
        assert TaskStateMachine.validate_transition(TaskStatus.CREATED, TaskStatus.VALIDATING) is True
        assert TaskStateMachine.validate_transition(TaskStatus.VALIDATING, TaskStatus.GOAL_ANALYSIS) is True
        assert TaskStateMachine.validate_transition(TaskStatus.GOAL_ANALYSIS, TaskStatus.PLANNING) is True
        assert TaskStateMachine.validate_transition(TaskStatus.PLANNING, TaskStatus.PLAN_READY) is True
        assert TaskStateMachine.validate_transition(TaskStatus.PLAN_READY, TaskStatus.QUEUED) is True
        assert TaskStateMachine.validate_transition(TaskStatus.QUEUED, TaskStatus.EXECUTING) is True
        assert TaskStateMachine.validate_transition(TaskStatus.EXECUTING, TaskStatus.COMPLETED) is True
        
        # Branch transitions
        assert TaskStateMachine.validate_transition(TaskStatus.EXECUTING, TaskStatus.WAITING_APPROVAL) is True
        assert TaskStateMachine.validate_transition(TaskStatus.WAITING_APPROVAL, TaskStatus.EXECUTING) is True
        assert TaskStateMachine.validate_transition(TaskStatus.EXECUTING, TaskStatus.FAILED) is True
        assert TaskStateMachine.validate_transition(TaskStatus.FAILED, TaskStatus.RETRYING) is True
        assert TaskStateMachine.validate_transition(TaskStatus.FAILED, TaskStatus.CANCELLED) is True
        
        # Self transitions
        assert TaskStateMachine.validate_transition(TaskStatus.CREATED, TaskStatus.CREATED) is True

    def test_invalid_transitions(self):
        # Completed/Cancelled cannot change state
        assert TaskStateMachine.validate_transition(TaskStatus.COMPLETED, TaskStatus.EXECUTING) is False
        assert TaskStateMachine.validate_transition(TaskStatus.CANCELLED, TaskStatus.CREATED) is False
        
        # Skip steps
        assert TaskStateMachine.validate_transition(TaskStatus.CREATED, TaskStatus.EXECUTING) is False
        assert TaskStateMachine.validate_transition(TaskStatus.PLAN_READY, TaskStatus.COMPLETED) is False

    def test_transition_exception_raise(self):
        with pytest.raises(ValueError) as exc:
            TaskStateMachine.transition(TaskStatus.COMPLETED, TaskStatus.EXECUTING)
        assert "Illegal state transition" in str(exc.value)


# ─── 2. Services Integration Tests (Using real db_session) ───────────────────

@pytest.mark.asyncio
class TestAutomationServices:
    """Verifies Task, Planning, Execution, and Approval services using actual DB sessions."""

    async def test_create_task_creates_event(self, db_session: AsyncSession):
        task_service = TaskService()
        
        # Create a real task in DB
        task = await task_service.create_task(db=db_session, user_id=1, goal="Execute scraping task")
        
        assert task.goal == "Execute scraping task"
        assert task.status == TaskStatus.CREATED
        
        # Verify GoalCreated event was written to DB
        stmt = select(TaskEvent).where(TaskEvent.task_id == task.id)
        res = await db_session.execute(stmt)
        events = res.scalars().all()
        assert len(events) == 1
        assert events[0].event_type == "GoalCreated"

    async def test_planning_service_plan_ready(self, db_session: AsyncSession):
        task_service = TaskService()
        planning_service = PlanningService()
        
        task = await task_service.create_task(db=db_session, user_id=1, goal="Analyze charts")
        
        # Manually transition task status through validation to goal analysis so it's ready for planning
        await task_service.transition_task_status(db=db_session, task_id=task.id, user_id=1, target_status=TaskStatus.VALIDATING)
        await task_service.transition_task_status(db=db_session, task_id=task.id, user_id=1, target_status=TaskStatus.GOAL_ANALYSIS)

        steps = [
            {"tool_name": "browser", "arguments": {"url": "https://example.com"}},
            {"tool_name": "vision", "arguments": {"action": "caption"}}
        ]
        plan = await planning_service.create_plan(
            db=db_session,
            task_id=task.id,
            user_id=1,
            summary="Plan 1",
            steps_data=steps
        )

        assert plan.summary == "Plan 1"
        assert len(plan.steps) == 2
        
        # Verify Task transitioned to PLAN_READY
        db_task = await task_service.get_task(db_session, task.id, 1)
        assert db_task.status == TaskStatus.PLAN_READY

    async def test_execution_service_start_logs(self, db_session: AsyncSession):
        task_service = TaskService()
        planning_service = PlanningService()
        exec_service = ExecutionService()

        task = await task_service.create_task(db=db_session, user_id=1, goal="Task 1")
        await task_service.transition_task_status(db=db_session, task_id=task.id, user_id=1, target_status=TaskStatus.VALIDATING)
        await task_service.transition_task_status(db=db_session, task_id=task.id, user_id=1, target_status=TaskStatus.GOAL_ANALYSIS)

        plan = await planning_service.create_plan(
            db=db_session,
            task_id=task.id,
            user_id=1,
            summary="Plan 1",
            steps_data=[{"tool_name": "browser", "arguments": {"url": "https://example.com"}}]
        )

        execution = await exec_service.start_execution(db=db_session, plan_id=plan.id, user_id=1)
        
        db_task = await task_service.get_task(db_session, task.id, 1)
        assert db_task.status == TaskStatus.EXECUTING
        assert execution.status == "EXECUTING"
        assert "Execution started" in execution.logs

    async def test_approval_service_transitions(self, db_session: AsyncSession):
        task_service = TaskService()
        planning_service = PlanningService()
        exec_service = ExecutionService()
        app_service = ApprovalService()

        task = await task_service.create_task(db=db_session, user_id=1, goal="System test")
        await task_service.transition_task_status(db=db_session, task_id=task.id, user_id=1, target_status=TaskStatus.VALIDATING)
        await task_service.transition_task_status(db=db_session, task_id=task.id, user_id=1, target_status=TaskStatus.GOAL_ANALYSIS)

        plan = await planning_service.create_plan(
            db=db_session,
            task_id=task.id,
            user_id=1,
            summary="Plan 1",
            steps_data=[{"tool_name": "browser", "arguments": {"url": "https://example.com"}, "approval_required": True}]
        )
        
        await exec_service.start_execution(db=db_session, plan_id=plan.id, user_id=1)
        
        step_id = plan.steps[0].id
        approval = await app_service.request_approval(db=db_session, step_id=step_id, requested_by_user_id=1)
        
        db_task = await task_service.get_task(db_session, task.id, 1)
        assert db_task.status == TaskStatus.WAITING_APPROVAL
        assert plan.steps[0].status == "WAITING_APPROVAL"
        assert approval.status == "PENDING"


# ─── 3. API Integration Tests ─────────────────────────────────────────────────

from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_automation_api_endpoints(db_session: AsyncSession):
    """Integration test verification for all REST foundation routes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Sign up and login a test user
        signup_payload = {
            "name": "Automation Tester",
            "email": "auto_tester@example.com",
            "password": "securepassword123",
            "role": "user"
        }
        await ac.post("/api/v1/auth/signup", json=signup_payload)
        
        login_data = {
            "username": "auto_tester@example.com",
            "password": "securepassword123"
        }
        login_res = await ac.post("/api/v1/auth/login", data=login_data)
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. POST /tasks (create task)
        task_payload = {
            "goal": "Extract list of tech news articles from news.ycombinator.com"
        }
        create_res = await ac.post("/api/v1/automation/tasks", json=task_payload, headers=headers)
        assert create_res.status_code == 201
        task_data = create_res.json()
        assert task_data["success"] is True
        assert task_data["data"]["goal"] == task_payload["goal"]
        assert task_data["data"]["status"] == "CREATED"
        task_id = task_data["data"]["id"]

        # 3. GET /tasks (list tasks)
        list_res = await ac.get("/api/v1/automation/tasks", headers=headers)
        assert list_res.status_code == 200
        assert list_res.json()["success"] is True
        assert len(list_res.json()["data"]) >= 1

        # 4. GET /tasks/{id} (get specific task details)
        get_res = await ac.get(f"/api/v1/automation/tasks/{task_id}", headers=headers)
        assert get_res.status_code == 200
        assert get_res.json()["success"] is True
        assert get_res.json()["data"]["id"] == task_id

        # 5. POST /tasks/{id}/cancel (cancel task)
        cancel_res = await ac.post(f"/api/v1/automation/tasks/{task_id}/cancel", headers=headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["success"] is True
        assert cancel_res.json()["data"]["status"] == "CANCELLED"

        # 6. Test Retry Flow on a FAILED task
        # Create second task
        create_res2 = await ac.post("/api/v1/automation/tasks", json={"goal": "Task to fail and retry"}, headers=headers)
        task2_id = create_res2.json()["data"]["id"]

        # Force transition status to FAILED in the test DB directly
        task_service = TaskService()
        from app.models.automation import Task
        res = await db_session.execute(select(Task).where(Task.id == uuid.UUID(task2_id)))
        db_task = res.scalars().first()
        assert db_task is not None
        
        # Created -> Validating -> Failed
        await task_service.transition_task_status(db_session, db_task.id, db_task.user_id, TaskStatus.VALIDATING)
        await task_service.transition_task_status(db_session, db_task.id, db_task.user_id, TaskStatus.FAILED)
        await db_session.commit()

        # Call POST /tasks/{id}/retry
        retry_res = await ac.post(f"/api/v1/automation/tasks/{task2_id}/retry", headers=headers)
        assert retry_res.status_code == 200
        assert retry_res.json()["success"] is True
        assert retry_res.json()["data"]["status"] == "RETRYING"


# ─── 4. Tool Registry Unit Tests ─────────────────────────────────────────────

from app.tools.base_tool import BaseTool
from app.tools.registry import tool_registry
from pydantic import BaseModel

class DummyInput(BaseModel):
    arg1: str

class DummyOutput(BaseModel):
    result: str

class MockBrowserTool(BaseTool):
    @property
    def name(self) -> str:
        return "BrowserTool"
    @property
    def description(self) -> str:
        return "Simulated browser tool"
    @property
    def version(self) -> str:
        return "1.0.0"
    @property
    def input_schema(self) -> BaseModel:
        return DummyInput
    @property
    def output_schema(self) -> BaseModel:
        return DummyOutput
    def validate(self, arguments: dict) -> bool:
        return "arg1" in arguments
    async def execute(self, arguments: dict) -> dict:
        return {"result": "success"}
    async def cleanup(self) -> None:
        pass
    async def health_check(self) -> bool:
        return True

    def test_register_and_retrieve_extensible_tools(self):
        tool = MockBrowserTool()
        tool_registry.register(tool)
        
        retrieved = tool_registry.get("BrowserTool")
        assert retrieved.name == "BrowserTool"
        assert retrieved.validate({"arg1": "test"}) is True
        assert "browsertool" in tool_registry.list_tools()


# ─── 5. Refactoring & Stabilization Verification Tests ─────────────────────

@pytest.mark.asyncio
class TestStabilizationAndRefactoring:
    """Verifies state enforcement, optimistic locking concurrency, and tool lifecycles."""

    async def test_invalid_state_transition_raises_error(self, db_session: AsyncSession):
        task_service = TaskService()
        task = await task_service.create_task(db=db_session, user_id=1, goal="Validation transitions test")
        
        # Transition from CREATED to COMPLETED directly (illegal transition)
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            await task_service.transition_task_status(db=db_session, task_id=task.id, user_id=1, target_status=TaskStatus.COMPLETED)
        
        assert "Illegal state transition" in str(exc_info.value)

    async def test_optimistic_locking_conflict_on_simultaneous_updates(self, db_session: AsyncSession):
        task_service = TaskService()
        task = await task_service.create_task(db=db_session, user_id=1, goal="Optimistic lock test")
        
        # Simulate two concurrent status updates using old expected version (version = 1)
        expected_ver = task.version
        
        # First transition succeeds: CREATED -> VALIDATING
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.VALIDATING)
        
        # Since the database record's version has incremented, task_repo.update_status will return None (raising ConcurrencyConflictError when run in service)
        # Here we verify the service raises it when concurrency collision happens:
        # To simulate, we trigger update_status directly which returns None on stale version
        res_update = await task_service.task_repo.update_status(
            db=db_session,
            task_id=task.id,
            user_id=1,
            status=TaskStatus.CANCELLED,
            expected_version=expected_ver
        )
        assert res_update is None
        
    async def test_tool_session_lifecycle(self, db_session: AsyncSession):
        from app.tools.manager import ToolManager
        from app.tools.base_tool import BaseTool
        
        # Create a mock tool that tracks cleanup
        class StatefulTool(BaseTool):
            cleanup_called = False
            @property
            def name(self) -> str: return "StatefulTool"
            @property
            def description(self) -> str: return "Stateful"
            @property
            def version(self) -> str: return "1.0.0"
            @property
            def input_schema(self): return DummyInput
            @property
            def output_schema(self): return DummyOutput
            def validate(self, arguments: dict): return True
            async def execute(self, arguments: dict): return {"result": "ok"}
            async def cleanup(self): self.cleanup_called = True
            async def health_check(self): return True
            
        tool = StatefulTool()
        tool_registry.register(tool)
        
        manager = ToolManager()
        # Execute tool should NOT call cleanup immediately!
        res = await manager.execute_tool("StatefulTool", {"arg1": "test"})
        assert res["result"] == "ok"
        assert tool.cleanup_called is False
        
        # Explicit cleanup should set state to True
        await manager.cleanup_tool("StatefulTool")
        assert tool.cleanup_called is True

    async def test_retry_during_execution_raises_error(self, db_session: AsyncSession):
        task_service = TaskService()
        task = await task_service.create_task(db=db_session, user_id=1, goal="Retry flow validation")
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.VALIDATING)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.GOAL_ANALYSIS)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.PLANNING)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.PLAN_READY)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.QUEUED)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.EXECUTING)
        
        # Transition EXECUTING -> RETRYING is illegal!
        with pytest.raises(InvalidStateTransitionError):
            await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.RETRYING)

    async def test_cancel_during_approval(self, db_session: AsyncSession):
        task_service = TaskService()
        task = await task_service.create_task(db=db_session, user_id=1, goal="Cancel flow validation")
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.VALIDATING)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.GOAL_ANALYSIS)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.PLANNING)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.PLAN_READY)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.QUEUED)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.EXECUTING)
        await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.WAITING_APPROVAL)
        
        # Transition WAITING_APPROVAL -> CANCELLED is allowed
        cancelled_task = await task_service.cancel_task(db_session, task.id, 1)
        assert cancelled_task.status == TaskStatus.CANCELLED

    async def test_api_validation_error_envelope(self, db_session: AsyncSession):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. Sign up and login a test user
            signup_payload = {
                "name": "Validation Envelope Tester",
                "email": "val_tester@example.com",
                "password": "securepassword123",
                "role": "user"
            }
            await ac.post("/api/v1/auth/signup", json=signup_payload)
            login_data = {"username": "val_tester@example.com", "password": "securepassword123"}
            login_res = await ac.post("/api/v1/auth/login", data=login_data)
            token = login_res.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # 2. Trigger request validation failure (missing goal payload)
            res = await ac.post("/api/v1/automation/tasks", json={}, headers=headers)
            assert res.status_code == 422
            json_res = res.json()
            assert json_res["success"] is False
            assert "Validation failed" in json_res["message"]
            assert json_res["data"] is None
