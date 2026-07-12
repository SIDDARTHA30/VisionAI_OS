import json
import uuid
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.automation import Task, Plan, PlanStep, TaskStatus
from app.services.automation.task_service import TaskService
from app.services.automation.planning_service import PlanningService
from app.services.automation.exceptions import (
    PlannerValidationError,
    PlannerDependencyError,
    PlannerRetryExceeded,
    InvalidStateTransitionError
)
from app.tools.registry import tool_registry

# Setup mock registered tools for isolation
from app.tools.browser.browser_tool import BrowserTool
from app.tools.utility.calculator_tool import CalculatorTool


@pytest.fixture(autouse=True)
def setup_tools():
    """Ensure tool_registry has calculator and browser registered for tests."""
    tool_registry.clear()
    tool_registry.register(BrowserTool())
    tool_registry.register(CalculatorTool())


@pytest.mark.asyncio
async def test_planner_success_mock(db_session: AsyncSession):
    """Verify that a successful Gemini plan json is parsed, optimized, validated, and saved to DB."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Extract metrics and calculate totals")

    mock_llm_response = {
        "summary": "Navigate to metrics page and evaluate totals",
        "confidence_score": 0.95,
        "steps": [
            {
                "step_id": str(uuid.uuid4()),
                "step_number": 1,
                "tool_name": "browser",
                "input_arguments": {"action": "navigate", "url": "https://example.com/metrics"},
                "approval_required": False,
                "depends_on": []
            },
            # Dead step duplicate consecutive check: this duplicate step should get optimized away!
            {
                "step_id": str(uuid.uuid4()),
                "step_number": 2,
                "tool_name": "browser",
                "input_arguments": {"action": "navigate", "url": "https://example.com/metrics"},
                "approval_required": False,
                "depends_on": []
            },
            {
                "step_id": str(uuid.uuid4()),
                "step_number": 3,
                "tool_name": "calculator",
                "input_arguments": {"expression": "250 + 500"},
                "approval_required": False,
                "depends_on": [1]
            }
        ]
    }

    planning_srv = PlanningService()

    # Mock the LLM call
    with patch.object(planning_srv, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = json.dumps(mock_llm_response)

        plan = await planning_srv.generate_plan_from_goal(db=db_session, task_id=task.id, user_id=1)

        # 1. Assert plan created correctly
        assert plan is not None
        assert plan.summary == "Navigate to metrics page and evaluate totals"
        assert plan.plan_version == 1
        assert plan.is_latest is True

        # 2. Assert dead step removal (2 browser tasks reduced to 1)
        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "browser"
        assert plan.steps[0].step_number == 1
        assert plan.steps[1].tool_name == "calculator"
        assert plan.steps[1].step_number == 2
        # Dependency index updated: since step 2 was removed, the calculator dependency shifts to step 1
        assert plan.steps[1].depends_on == [1]

        # 3. Assert task status transitioned to PLAN_READY
        assert task.status == TaskStatus.PLAN_READY


@pytest.mark.asyncio
async def test_planner_circular_dependency_rejection(db_session: AsyncSession):
    """Verify circular step dependencies are rejected with PlannerDependencyError."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Invalid circular dependency task")

    mock_invalid_response = {
        "summary": "Circular depends check",
        "steps": [
            {
                "step_id": str(uuid.uuid4()),
                "step_number": 1,
                "tool_name": "browser",
                "input_arguments": {"action": "navigate", "url": "https://example.com"},
                "approval_required": False,
                # Invalid: depends on step 2 (which is future/concurrent step)
                "depends_on": [2]
            },
            {
                "step_id": str(uuid.uuid4()),
                "step_number": 2,
                "tool_name": "calculator",
                "input_arguments": {"expression": "100 + 2"},
                "approval_required": False,
                "depends_on": [1]
            }
        ]
    }

    planning_srv = PlanningService()

    with patch.object(planning_srv, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = json.dumps(mock_invalid_response)

        with pytest.raises(PlannerRetryExceeded) as exc_info:
            await planning_srv.generate_plan_from_goal(db=db_session, task_id=task.id, user_id=1)
        
        # Verify circular checks failure in error list
        assert "Circular dependencies" in str(exc_info.value) or "cannot depend on future step" in str(exc_info.value)


@pytest.mark.asyncio
async def test_planner_unregistered_tool_rejection(db_session: AsyncSession):
    """Verify plans containing unregistered tool names are rejected."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Unregistered tool task")

    mock_invalid_response = {
        "summary": "Bad tool check",
        "steps": [
            {
                "step_id": str(uuid.uuid4()),
                "step_number": 1,
                "tool_name": "non_existent_tool_name",
                "input_arguments": {},
                "approval_required": False,
                "depends_on": []
            }
        ]
    }

    planning_srv = PlanningService()

    with patch.object(planning_srv, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = json.dumps(mock_invalid_response)

        with pytest.raises(PlannerRetryExceeded) as exc_info:
            await planning_srv.generate_plan_from_goal(db=db_session, task_id=task.id, user_id=1)
        
        assert "is not registered" in str(exc_info.value)


@pytest.mark.asyncio
async def test_plan_versioning_and_history(db_session: AsyncSession):
    """Verify regenerating a plan increments its plan_version and deactivates older is_latest tags."""
    task_service = TaskService()
    task = await task_service.create_task(db=db_session, user_id=1, goal="Plan history test")

    mock_llm_response = {
        "summary": "Plan version 1",
        "steps": [
            {
                "step_id": str(uuid.uuid4()),
                "step_number": 1,
                "tool_name": "calculator",
                "input_arguments": {"expression": "1 + 1"},
                "approval_required": False
            }
        ]
    }

    planning_srv = PlanningService()

    # 1. Generate first plan version
    with patch.object(planning_srv, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_gemini.return_value = json.dumps(mock_llm_response)
        plan1 = await planning_srv.generate_plan_from_goal(db=db_session, task_id=task.id, user_id=1)
        assert plan1.plan_version == 1
        assert plan1.is_latest is True

    # 2. Reset task status back to PLANNING to allow regeneration
    await task_service.transition_task_status(db_session, task.id, 1, TaskStatus.PLANNING)

    # 3. Generate second plan version
    with patch.object(planning_srv, "_call_gemini_api", new_callable=AsyncMock) as mock_gemini:
        mock_llm_response["summary"] = "Plan version 2"
        mock_llm_response["steps"][0]["step_id"] = str(uuid.uuid4())
        mock_gemini.return_value = json.dumps(mock_llm_response)
        plan2 = await planning_srv.generate_plan_from_goal(db=db_session, task_id=task.id, user_id=1)
        
        assert plan2.plan_version == 2
        assert plan2.is_latest is True
        assert plan2.parent_plan_id == plan1.id

        # Reload plan1 to verify is_latest was flipped to False
        res = await db_session.execute(select(Plan).where(Plan.id == plan1.id))
        plan1_reloaded = res.scalars().first()
        assert plan1_reloaded.is_latest is False
