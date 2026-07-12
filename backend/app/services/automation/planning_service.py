import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.core.config import settings
from app.core.ai_config import ai_config
from app.models.automation import Plan, PlanStep, TaskStatus
from app.repositories.plan_repository import PlanRepository
from app.repositories.task_repository import TaskRepository
from app.services.automation.task_service import TaskService
from app.tools.registry import tool_registry
from app.tools.factory import ToolFactory
from app.schemas.automation import PlanCreate, PlannerMetrics, PlannerAuditLog
from app.services.automation.prompt_templates import PLANNER_SYSTEM_INSTRUCTION
from app.services.automation.exceptions import (
    TaskNotFoundError,
    InvalidStateTransitionError,
    PlannerLLMError,
    PlannerTimeoutError,
    PlannerValidationError,
    PlannerRetryExceeded,
    PlannerDependencyError,
)

logger = logging.getLogger(__name__)


class PlanningService:
    """
    Manages the creation, generation, validation, and optimization of task execution plans.
    Integrates Gemini structured JSON output and checks tool input parameter constraints.
    """

    def __init__(self):
        self.plan_repo = PlanRepository()
        self.task_repo = TaskRepository()
        self.task_service = TaskService()

    async def generate_plan_from_goal(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int
    ) -> Plan:
        """
        Main entry point. Orchestrates context collection, prompt building, LLM execution,
        retries, validations, optimizations, and writes to database.
        """
        task = await self.task_repo.get_by_id(db, task_id, user_id)
        if not task:
            raise TaskNotFoundError("Task not found or access denied.")

        current_status = TaskStatus(task.status)
        if current_status not in [TaskStatus.CREATED, TaskStatus.VALIDATING, TaskStatus.GOAL_ANALYSIS, TaskStatus.PLANNING, TaskStatus.PLAN_READY]:
            raise InvalidStateTransitionError(f"Task status '{task.status}' is not eligible for planning.")

        # Transition task state: Current -> VALIDATING -> GOAL_ANALYSIS -> PLANNING
        if current_status == TaskStatus.CREATED:
            await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.VALIDATING)
            current_status = TaskStatus.VALIDATING
            
        if current_status == TaskStatus.VALIDATING:
            await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.GOAL_ANALYSIS)
            current_status = TaskStatus.GOAL_ANALYSIS
            
        if current_status == TaskStatus.GOAL_ANALYSIS:
            await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.PLANNING)
        elif current_status == TaskStatus.PLAN_READY:
            # If regenerating an already ready plan, move back to PLANNING
            await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.PLANNING)

        start_time = datetime.now(timezone.utc)
        audit_steps = ["GOAL_ANALYSIS started", "CONTEXT_COLLECTION started", "TOOL_DISCOVERY started"]

        # Collect tools definitions
        tool_definitions = self._build_tool_definitions()
        planning_context = f"Task Goal: {task.goal}\nUser ID: {user_id}"

        audit_steps.extend(["PROMPT_BUILD completed", "LLM_GENERATING started"])

        retries = 0
        max_retries = 3
        validation_errors_log = []
        plan_dict = None

        while retries < max_retries:
            prompt = self._build_prompt(task.goal, tool_definitions, planning_context, validation_errors_log)
            
            try:
                # Call Gemini structured content response
                json_str = await self._call_gemini_api(prompt)
                plan_dict = json.loads(json_str)
            except json.JSONDecodeError as je:
                validation_errors_log.append(f"Invalid JSON returned by LLM: {str(je)}")
                retries += 1
                audit_steps.append(f"JSON_VALIDATION failed (attempt {retries})")
                continue
            except Exception as e:
                audit_steps.append(f"LLM_GENERATING failed: {str(e)}")
                raise PlannerLLMError(f"Gemini planner failure: {str(e)}")

            # Layered Plan Validation
            audit_steps.append(f"PLAN_VALIDATION started (attempt {retries + 1})")
            try:
                # Pydantic schema validation
                PlanCreate(**plan_dict)

                # Validate registered tool existence and argument schemas
                for step in plan_dict.get("steps", []):
                    tool_name = step["tool_name"]
                    if not tool_registry.exists(tool_name):
                        raise PlannerValidationError(f"Tool '{tool_name}' is not registered in the system.")
                    
                    # Instantiate and validate parameter inputs
                    tool_instance = ToolFactory.create(tool_name)
                    try:
                        tool_instance.validate_input(step["input_arguments"])
                    except Exception as ie:
                        raise PlannerValidationError(f"Input schema validation failed for tool '{tool_name}': {str(ie)}")

                # Validate dependencies circular checks
                self._validate_plan_dependencies(plan_dict.get("steps", []))

                # Validation Passed!
                audit_steps.append("PLAN_VALIDATION passed")
                break

            except (PlannerValidationError, PlannerDependencyError) as ve:
                validation_errors_log.append(str(ve))
                retries += 1
                audit_steps.append(f"PLAN_VALIDATION failed (attempt {retries}): {str(ve)}")

        if plan_dict is None or retries >= max_retries:
            await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.FAILED)
            raise PlannerRetryExceeded(f"Failed to generate a valid plan after {max_retries} attempts. Errors: {validation_errors_log}")

        # Optimize plan steps (dead step removal, duplicate checks)
        audit_steps.append("PLAN_OPTIMIZATION started")
        optimized_steps = self._optimize_plan_steps(plan_dict.get("steps", []))
        audit_steps.append("PLAN_OPTIMIZATION completed")

        # Save Plan to Database
        # Find latest plan to link parent_plan_id
        parent_plan = await self._get_latest_plan(db, task_id)
        parent_plan_id = parent_plan.id if parent_plan else None

        plan = await self.plan_repo.create_plan_and_steps(
            db=db,
            task_id=task_id,
            summary=plan_dict.get("summary", "Automation execution plan"),
            steps_list=optimized_steps,
            parent_plan_id=parent_plan_id
        )

        await db.commit()
        audit_steps.append("PLAN_READY reached")

        # Log audit details
        finished_time = datetime.now(timezone.utc)
        latency_ms = int((finished_time - start_time).total_seconds() * 1000)
        logger.info(
            f"Planner Audit: task={task_id}, plan={plan.id}, latency={latency_ms}ms, "
            f"status=SUCCESS, steps={audit_steps}"
        )

        # Transition task to PLAN_READY
        await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.PLAN_READY)
        return plan

    async def validate_plan_from_goal_dry_run(
        self,
        task_id: uuid.UUID,
        goal: str
    ) -> dict:
        """
        Runs the full planning validation pipeline without writing to the database.
        Returns the structured plan if successful, or raises PlannerValidationError.
        """
        tool_definitions = self._build_tool_definitions()
        planning_context = f"Dry Run Goal: {goal}"

        prompt = self._build_prompt(goal, tool_definitions, planning_context, [])
        json_str = await self._call_gemini_api(prompt)
        plan_dict = json.loads(json_str)

        # Validate structured JSON
        PlanCreate(**plan_dict)

        for step in plan_dict.get("steps", []):
            tool_name = step["tool_name"]
            if not tool_registry.exists(tool_name):
                raise PlannerValidationError(f"Tool '{tool_name}' is not registered.")
            
            tool_instance = ToolFactory.create(tool_name)
            tool_instance.validate_input(step["input_arguments"])

        self._validate_plan_dependencies(plan_dict.get("steps", []))
        optimized_steps = self._optimize_plan_steps(plan_dict.get("steps", []))
        plan_dict["steps"] = optimized_steps

        return plan_dict

    async def create_plan(
        self,
        db: AsyncSession,
        task_id: uuid.UUID,
        user_id: int,
        summary: Optional[str],
        steps_data: List[Dict[str, Any]],
        estimated_cost: float = 0.0,
        estimated_duration_sec: int = 0
    ) -> Plan:
        """Backward-compatible plan creation method for manual plan inserts."""
        steps_list = []
        for idx, step in enumerate(steps_data):
            steps_list.append({
                "step_id": uuid.uuid4(),
                "step_number": idx + 1,
                "tool_name": step["tool_name"],
                "input_arguments": step.get("arguments") or step.get("input_arguments") or {},
                "approval_required": step.get("approval_required", False),
                "depends_on": []
            })
            
        task = await self.task_repo.get_by_id(db, task_id, user_id)
        if not task:
            raise TaskNotFoundError("Task not found.")
            
        current_status = TaskStatus(task.status)
        if current_status != TaskStatus.PLANNING:
            if current_status == TaskStatus.CREATED:
                await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.VALIDATING)
                current_status = TaskStatus.VALIDATING
            if current_status == TaskStatus.VALIDATING:
                await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.GOAL_ANALYSIS)
                current_status = TaskStatus.GOAL_ANALYSIS
            if current_status == TaskStatus.GOAL_ANALYSIS:
                await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.PLANNING)

        plan = await self.plan_repo.create_plan_and_steps(
            db=db,
            task_id=task_id,
            summary=summary,
            steps_list=steps_list,
            estimated_cost=estimated_cost,
            estimated_duration_sec=estimated_duration_sec
        )
        
        await self.task_service.transition_task_status(db, task_id, user_id, TaskStatus.PLAN_READY)
        return plan

    async def get_plan(
        self,
        db: AsyncSession,
        plan_id: uuid.UUID
    ) -> Optional[Plan]:
        return await self.plan_repo.get_by_id(db, plan_id)

    # ─── Internal Helpers ─────────────────────────────────────────────────────

    def _build_tool_definitions(self) -> str:
        """Serializes all tool schemas registered in the registry."""
        definitions = []
        for tool in tool_registry.list():
            meta = tool.metadata
            caps = [c if isinstance(c, str) else c.value for c in meta.capabilities]
            perms = [p if isinstance(p, str) else p.value for p in meta.permissions]
            definitions.append(
                f"- Tool: '{meta.name}' v{meta.version}\n"
                f"  Description: {meta.description}\n"
                f"  Capabilities: {caps}\n"
                f"  Permissions: {perms}\n"
            )
        return "\n".join(definitions)

    def _build_prompt(self, goal: str, tool_definitions: str, context: str, errors: List[str]) -> str:
        """Constructs prompt using system instruction and error correction logs."""
        prompt = PLANNER_SYSTEM_INSTRUCTION.format(
            tool_definitions=tool_definitions,
            planning_context=context
        )
        prompt += f"\nUser Goal: {goal}\n"

        if errors:
            prompt += (
                f"\nIMPORTANT: Your previous output failed validations with these errors:\n"
                + "\n".join(f"- {e}" for e in errors)
                + "\nPlease correct your formatting and argument constraints and try again.\n"
            )
        return prompt

    async def _call_gemini_api(self, prompt: str) -> str:
        """Synchronous wrapper executing client models generate content in loop executor."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GOOGLE_API_KEY or "MOCK_KEY")
        loop = asyncio.get_running_loop()

        try:
            # Enforce JSON output format via response_mime_type setting parameter
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=ai_config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
            )
            return response.text or "{}"
        except Exception as e:
            logger.error(f"Gemini API generation failed: {e}")
            raise PlannerLLMError(f"Gemini API generation failed: {e}")

    def _validate_plan_dependencies(self, steps: List[dict]) -> None:
        """Performs circular dependency verification on step sequences."""
        adj = {s["step_number"]: s.get("depends_on") or [] for s in steps}

        # Check for invalid dependencies referencing future or non-existent steps
        for step_num, deps in adj.items():
            for dep in deps:
                if dep not in adj:
                    raise PlannerDependencyError(f"Step {step_num} depends on non-existent step {dep}.")
                if dep >= step_num:
                    raise PlannerDependencyError(f"Step {step_num} cannot depend on future step {dep}.")

        # Detect circular dependencies using DFS
        visited = {}

        def has_cycle(u):
            visited[u] = 1  # visiting
            for v in adj[u]:
                if visited.get(v, 0) == 1:
                    return True
                if visited.get(v, 0) == 0:
                    if has_cycle(v):
                        return True
            visited[u] = 2  # visited
            return False

        for node in adj:
            if visited.get(node, 0) == 0:
                if has_cycle(node):
                    raise PlannerDependencyError("Circular dependencies detected in plan steps graph.")

    def _optimize_plan_steps(self, steps: List[dict]) -> List[dict]:
        """Performs dead step removal and duplicate tool calls stripping."""
        optimized = []
        for step in steps:
            # Dead step removal: skip consecutive identical operations
            if optimized:
                prev = optimized[-1]
                if prev["tool_name"] == step["tool_name"] and prev["input_arguments"] == step["input_arguments"]:
                    logger.info(f"Stripping duplicate consecutive dead step for tool: {step['tool_name']}")
                    continue
            optimized.append(step)

        # Re-index step numbers sequentially
        for idx, step in enumerate(optimized):
            step["step_number"] = idx + 1
        return optimized

    async def _get_latest_plan(self, db: AsyncSession, task_id: uuid.UUID) -> Optional[Plan]:
        """Helper to find the previous latest plan for versioning link."""
        stmt = select(Plan).where(Plan.task_id == task_id, Plan.is_latest == True)
        res = await db.execute(stmt)
        return res.scalars().first()
