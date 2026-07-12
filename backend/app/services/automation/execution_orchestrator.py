import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import AsyncSessionLocal
from app.models.automation import TaskStatus, Plan, PlanStep, Execution, TaskEvent
from app.repositories.execution_repository import ExecutionRepository
from app.repositories.plan_repository import PlanRepository
from app.repositories.task_repository import TaskRepository
from app.services.automation.task_service import TaskService
from app.tools.manager import ToolManager
from app.tools.factory import ToolFactory
from app.tools.context import ToolContext
from app.services.automation.exceptions import TaskNotFoundError
from app.services.automation.execution_lock import execution_locks
from app.services.automation.execution_events import execution_events, ExecutionStarted, StepStarted, StepFinished, StepFailed, TaskCompleted, TaskCancelled
from app.services.automation.execution_graph import ExecutionGraph
from app.services.automation.execution_queue import AsyncExecutionQueue
from app.services.automation.step_scheduler import StepScheduler
from app.services.automation.execution_context import ExecutionContext
from app.services.automation.execution_context_manager import ExecutionContextManager
from app.services.automation.execution_policy import execution_policy
from app.services.automation.retry_engine import RetryEngine
from app.services.automation.execution_error import RetryableError, PermanentError, ToolExecutionError, TimeoutError, CancellationError
from app.services.automation.step_result_cache import step_result_cache
from app.services.automation.resource_manager import resource_manager

logger = logging.getLogger(__name__)


class SessionWrapper:
    """Context manager that wraps database session lifetimes safely under test contexts."""
    def __init__(self, session_maker, override: Optional[AsyncSession], lock: asyncio.Lock):
        self.session_maker = session_maker
        self.override = override
        self.session = None
        self.is_owner = False
        self.lock = lock
        self.lock_acquired = False

    async def __aenter__(self) -> AsyncSession:
        if self.override is not None:
            await self.lock.acquire()
            self.lock_acquired = True
            self.session = self.override
            self.is_owner = False
        else:
            self.session = self.session_maker()
            self.is_owner = True
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.is_owner and self.session is not None:
                await self.session.close()
        finally:
            if self.lock_acquired:
                self.lock.release()


class ExecutionOrchestrator:
    """
    Core executor engine. Coordinates asynchronous queue worker tasks,
    optimistic state changes, event dispatching, retries, and sandboxing.
    """

    def __init__(self):
        self.exec_repo = ExecutionRepository()
        self.plan_repo = PlanRepository()
        self.task_repo = TaskRepository()
        self.task_service = TaskService()
        self.tool_manager = ToolManager()
        self.context_manager = ExecutionContextManager()
        self.retry_engine = RetryEngine()
        
        # Lock to synchronize database operations on shared sessions
        self._db_lock = asyncio.Lock()
        
        # In-memory tracking of active execution contexts for cancellations
        self._active_contexts: Dict[uuid.UUID, ExecutionContext] = {}

    def _get_db_session(self, db_override: Optional[AsyncSession]) -> SessionWrapper:
        return SessionWrapper(AsyncSessionLocal, db_override, self._db_lock)

    async def execute_task_plan(
        self,
        task_id: uuid.UUID,
        user_id: int,
        db: Optional[AsyncSession] = None
    ) -> None:
        """Runs the orchestrator loops as a background execution job."""
        if not await execution_locks.acquire_lock(task_id):
            logger.warning(f"Task {task_id} is already executing. Duplicate run request ignored.")
            return

        execution_id = uuid.uuid4()
        queue = AsyncExecutionQueue(maxsize=execution_policy.queue_size)
        scheduler = StepScheduler(queue)
        graph = ExecutionGraph(plan_id=uuid.uuid4())

        try:
            async with self._get_db_session(db) as session:
                task = await self.task_repo.get_by_id(session, task_id, user_id)
                if not task:
                    raise TaskNotFoundError("Task not found.")

                # Retrieve latest plan
                stmt = select(Plan).where(Plan.task_id == task_id, Plan.is_latest == True).options(selectinload(Plan.steps))
                res = await session.execute(stmt)
                plan = res.scalars().first()
                if not plan or not plan.steps:
                    logger.error(f"Cannot execute task {task_id}: no active plan generated.")
                    await self.task_service.transition_task_status(session, task_id, user_id, TaskStatus.FAILED)
                    return

                # Hydrate plan graph
                graph.plan_id = plan.id
                graph.build_from_steps(plan.steps)

                # Initialize sandbox environment
                context = self.context_manager.create_context(
                    task_id=task_id,
                    plan_id=plan.id,
                    execution_id=execution_id,
                    user_id=user_id
                )
                self._active_contexts[task_id] = context

                # Log database execution record
                execution = await self.exec_repo.create(session, plan.id)
                execution.id = execution_id
                execution.status = "EXECUTING"
                execution.started_at = datetime.now(timezone.utc)
                execution.logs = f"[{datetime.now(timezone.utc)}] Execution orchestrator started plan {plan.id}.\n"
                session.add(execution)

                # central transition: QUEUED -> STARTING -> EXECUTING
                await self.task_service.transition_task_status(session, task_id, user_id, TaskStatus.QUEUED)
                await self.task_service.transition_task_status(session, task_id, user_id, TaskStatus.EXECUTING)

                event_started = TaskEvent(
                    task_id=task_id,
                    event_type="ExecutionStarted",
                    payload={"execution_id": str(execution_id), "plan_id": str(plan.id)}
                )
                session.add(event_started)
                await session.commit()

            # Emit event
            await execution_events.emit(ExecutionStarted(
                task_id=task_id,
                plan_id=plan.id,
                execution_id=execution_id
            ))

            # Start worker consumer loop
            worker_task = asyncio.create_task(self._worker_loop(task_id, execution_id, queue, graph, context, db))
            
            # Queue Tier 1 steps
            await scheduler.schedule_ready_steps(graph)
            
            # Wait for worker loop
            await worker_task

            # Finalize task execution status
            async with self._get_db_session(db) as session:
                execution_record = await self.exec_repo.get_by_id(session, execution_id)
                
                if context.is_cancelled:
                    execution_record.status = "CANCELLED"
                    target_task_status = TaskStatus.CANCELLED
                    await execution_events.emit(TaskCancelled(task_id=task_id, execution_id=execution_id))
                elif graph.has_failures():
                    execution_record.status = "FAILED"
                    target_task_status = TaskStatus.FAILED
                else:
                    execution_record.status = "COMPLETED"
                    target_task_status = TaskStatus.COMPLETED
                    await execution_events.emit(TaskCompleted(task_id=task_id, execution_id=execution_id))

                current_time = datetime.now(timezone.utc)
                execution_record.completed_at = current_time
                if execution_record.started_at:
                    execution_record.duration_sec = int((current_time - execution_record.started_at).total_seconds())
                
                execution_record.logs = (execution_record.logs or "") + f"[{current_time}] Execution finished with status {execution_record.status}.\n"
                session.add(execution_record)

                await self.task_service.transition_task_status(session, task_id, user_id, target_task_status)
                
                event_finished = TaskEvent(
                    task_id=task_id,
                    event_type="ExecutionFinished",
                    payload={"execution_id": str(execution_id), "status": execution_record.status}
                )
                session.add(event_finished)
                await session.commit()

        except Exception as e:
            logger.error(f"Execution error in orchestrator: {e}")
            async with self._get_db_session(db) as session:
                await self.task_service.transition_task_status(session, task_id, user_id, TaskStatus.FAILED)
                await session.commit()
        finally:
            if task_id in self._active_contexts:
                self.context_manager.dispose_context(self._active_contexts[task_id])
                del self._active_contexts[task_id]
            resource_manager.cleanup_all()
            await execution_locks.release_lock(task_id)

    async def cancel_task(self, task_id: uuid.UUID, user_id: int) -> None:
        """Flags the active context as cancelled, triggering graceful terminations."""
        if task_id in self._active_contexts:
            context = self._active_contexts[task_id]
            context.is_cancelled = True
            logger.warning(f"Graceful cancellation requested for task execution {context.execution_id}.")
            resource_manager.cleanup_all()

    # ─── Worker Loop & Step Executions ────────────────────────────────────────

    async def _worker_loop(
        self,
        task_id: uuid.UUID,
        execution_id: uuid.UUID,
        queue: AsyncExecutionQueue,
        graph: ExecutionGraph,
        context: ExecutionContext,
        db: Optional[AsyncSession]
    ) -> None:
        """Processes enqueued step jobs in parallel up to configured concurrency limits."""
        semaphore = asyncio.Semaphore(execution_policy.max_parallel_steps)
        scheduler = StepScheduler(queue)
        active_step_tasks = []

        async def run_step_with_sem(step_num: int):
            async with semaphore:
                await self._execute_step(task_id, execution_id, step_num, graph, context, db)
                await scheduler.schedule_ready_steps(graph)

        while not context.is_cancelled:
            if graph.is_fully_completed() or graph.has_failures():
                break

            if queue.size() == 0 and len(active_step_tasks) == 0:
                break

            try:
                step_number = await asyncio.wait_for(queue.dequeue(), timeout=0.5)
                task = asyncio.create_task(run_step_with_sem(step_number))
                active_step_tasks.append(task)
                queue.task_done()
            except asyncio.TimeoutError:
                pass

            active_step_tasks = [t for t in active_step_tasks if not t.done()]

        if active_step_tasks:
            await asyncio.gather(*active_step_tasks, return_exceptions=True)

    async def _execute_step(
        self,
        task_id: uuid.UUID,
        execution_id: uuid.UUID,
        step_number: int,
        graph: ExecutionGraph,
        context: ExecutionContext,
        db: Optional[AsyncSession]
    ) -> None:
        """Executes a single step, resolving parameters, caches, and handling retries."""
        if context.is_cancelled:
            graph.mark_finished(step_number, success=False)
            return

        async with self._get_db_session(db) as session:
            res = await session.execute(
                select(PlanStep).where(PlanStep.plan_id == graph.plan_id, PlanStep.step_number == step_number)
            )
            step = res.scalars().first()
            if not step:
                logger.error(f"Plan step {step_number} record missing in DB.")
                graph.mark_finished(step_number, success=False)
                return

            step.status = "EXECUTING"
            step.started_at = datetime.now(timezone.utc)
            await session.commit()

        # Emit StepStarted event
        await execution_events.emit(StepStarted(
            task_id=task_id,
            plan_id=graph.plan_id,
            execution_id=execution_id,
            step_id=step.id,
            step_number=step_number,
            tool_name=step.tool_name
        ))

        # Substitute variable arguments from context parameters
        resolved_args = self._resolve_arguments(step.input_arguments, context.variables)

        # Evaluate Cache lookups
        cached_result = step_result_cache.get(step.tool_name, resolved_args)
        if cached_result:
            await self._finalize_step_success(db, task_id, execution_id, step.id, step_number, cached_result, graph, context)
            return

        # Prepare execution closure for retry engine
        async def run_tool():
            if context.is_cancelled:
                raise CancellationError("Execution cancelled by user.")
            
            tool = ToolFactory.create(step.tool_name)
            
            tool_context = ToolContext(
                request_id=context.request_id,
                trace_id=context.request_id,
                session_id=context.execution_id,
                user_id=context.user_id,
                correlation_id=context.execution_id,
                logger=logging.getLogger(f"app.tools.run.{step.tool_name}"),
                workspace=context.workspace,
                temp_dir=context.temp_dir,
                config={}
            )

            # Route through ToolManager coordinator
            res_output = await self.tool_manager.execute_tool(tool, resolved_args, tool_context)

            if not res_output.success:
                raise ToolExecutionError(res_output.error or f"Tool {step.tool_name} returned failure status.")

            return res_output.structured_output

        try:
            result_output = await self.retry_engine.execute_with_retry(
                operation=run_tool,
                max_retries=execution_policy.max_retries,
                initial_delay=0.1,  # Short initial delay under tests
                backoff_factor=execution_policy.backoff_factor
            )
            step_result_cache.set(step.tool_name, resolved_args, result_output)
            await self._finalize_step_success(db, task_id, execution_id, step.id, step_number, result_output, graph, context)

        except Exception as err:
            await self._finalize_step_failure(db, task_id, execution_id, step.id, step_number, str(err), graph, context)

    # ─── Success & Failure Markers ───────────────────────────────────────────

    async def _finalize_step_success(
        self,
        db: Optional[AsyncSession],
        task_id: uuid.UUID,
        execution_id: uuid.UUID,
        step_id: uuid.UUID,
        step_number: int,
        output: Dict[str, Any],
        graph: ExecutionGraph,
        context: ExecutionContext
    ) -> None:
        """Persists step completion success results to DB, logging parameters, and updating graphs."""
        graph.mark_finished(step_number, success=True)
        
        context.variables[f"step_{step_number}_output"] = output
        if isinstance(output, dict):
            for k, v in output.items():
                context.variables[f"step_{step_number}_{k}"] = v

        async with self._get_db_session(db) as session:
            res = await session.execute(select(PlanStep).where(PlanStep.id == step_id))
            step = res.scalars().first()
            if step:
                step.status = "COMPLETED"
                step.result_output = output
                step.completed_at = datetime.now(timezone.utc)
                session.add(step)

                execution = await self.exec_repo.get_by_id(session, execution_id)
                if execution:
                    log_entry = f"[{datetime.now(timezone.utc)}] Step {step_number} COMPLETED successfully. Output: {output}"
                    execution.logs = (execution.logs or "") + log_entry + "\n"
                    session.add(execution)
                await session.commit()

        await execution_events.emit(StepFinished(
            task_id=task_id,
            plan_id=graph.plan_id,
            execution_id=execution_id,
            step_id=step_id,
            step_number=step_number,
            tool_name=graph.nodes[step_number].tool_name,
            output=output
        ))

    async def _finalize_step_failure(
        self,
        db: Optional[AsyncSession],
        task_id: uuid.UUID,
        execution_id: uuid.UUID,
        step_id: uuid.UUID,
        step_number: int,
        error_msg: str,
        graph: ExecutionGraph,
        context: ExecutionContext
    ) -> None:
        """Persists failures, marking graph node status, logging, and updating event paths."""
        graph.mark_finished(step_number, success=False)

        async with self._get_db_session(db) as session:
            res = await session.execute(select(PlanStep).where(PlanStep.id == step_id))
            step = res.scalars().first()
            if step:
                step.status = "FAILED"
                step.error_message = error_msg
                step.completed_at = datetime.now(timezone.utc)
                session.add(step)

                execution = await self.exec_repo.get_by_id(session, execution_id)
                if execution:
                    log_entry = f"[{datetime.now(timezone.utc)}] Step {step_number} FAILED. Error: {error_msg}"
                    execution.logs = (execution.logs or "") + log_entry + "\n"
                    session.add(execution)
                await session.commit()

        await execution_events.emit(StepFailed(
            task_id=task_id,
            plan_id=graph.plan_id,
            execution_id=execution_id,
            step_id=step_id,
            step_number=step_number,
            tool_name=graph.nodes[step_number].tool_name,
            error=error_msg,
            retry_count=execution_policy.max_retries
        ))

    def _resolve_arguments(self, arguments: Dict[str, Any], variables: Dict[str, Any]) -> Dict[str, Any]:
        """Resolves output parameter variables inside string arguments dynamically."""
        resolved = {}
        for k, v in arguments.items():
            if isinstance(v, str):
                resolved_val = v
                for var_k, var_v in variables.items():
                    placeholder = f"{{{var_k}}}"
                    if placeholder in resolved_val:
                        resolved_val = resolved_val.replace(placeholder, str(var_v))
                resolved[k] = resolved_val
            elif isinstance(v, dict):
                resolved[k] = self._resolve_arguments(v, variables)
            else:
                resolved[k] = v
        return resolved
