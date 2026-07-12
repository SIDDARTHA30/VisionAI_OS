import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.automation import Approval, PlanStep, Task, TaskStatus, TaskEvent
from app.repositories.approval_repository import ApprovalRepository
from app.repositories.plan_repository import PlanRepository
from app.repositories.task_repository import TaskRepository
from app.services.automation.task_service import TaskService
from app.services.automation.exceptions import (
    TaskNotFoundError,
    ExecutionNotFoundError,
    InvalidStateTransitionError
)

logger = logging.getLogger("app.services.automation.approval_service")


class ApprovalService:
    """Manages the creation, validation, and fulfillment of execution approvals."""

    def __init__(self):
        self.approval_repo = ApprovalRepository()
        self.plan_repo = PlanRepository()
        self.task_repo = TaskRepository()
        self.task_service = TaskService()

    async def request_approval(
        self,
        db: AsyncSession,
        step_id: uuid.UUID,
        requested_by_user_id: int
    ) -> Approval:
        # Check step
        from app.models.automation import PlanStep
        res = await db.execute(select(PlanStep).where(PlanStep.id == step_id))
        step = res.scalars().first()
        if not step:
            raise ExecutionNotFoundError("Plan step not found.")

        # Check plan & task ownership
        plan = await self.plan_repo.get_by_id(db, step.plan_id)
        if not plan:
            raise ExecutionNotFoundError("Plan context not found.")
            
        task = await self.task_repo.get_by_id(db, plan.task_id, requested_by_user_id)
        if not task:
            raise TaskNotFoundError("Task access denied.")

        # Transition task to WAITING_APPROVAL (via TaskService)
        current_status = TaskStatus(task.status)
        if current_status != TaskStatus.WAITING_APPROVAL:
            await self.task_service.transition_task_status(db, plan.task_id, requested_by_user_id, TaskStatus.WAITING_APPROVAL)

        try:
            # Update step status to WAITING_APPROVAL
            step.status = "WAITING_APPROVAL"
            db.add(step)

            # Create approval
            approval = await self.approval_repo.create(db, step_id, requested_by_user_id)

            # Log event
            event_app = TaskEvent(
                task_id=task.id,
                event_type="ApprovalRequested",
                payload={"approval_id": str(approval.id), "step_id": str(step_id)}
            )
            db.add(event_app)

            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to request approval, rolling back. Error: {e}")
            raise e

        await db.refresh(approval)
        return approval

    async def respond_to_approval(
        self,
        db: AsyncSession,
        approval_id: uuid.UUID,
        approver_user_id: int,
        status: str,  # APPROVED or REJECTED
        rejection_reason: Optional[str] = None
    ) -> Approval:
        approval = await self.approval_repo.get_by_id(db, approval_id)
        if not approval:
            raise ExecutionNotFoundError("Approval request not found.")

        if approval.status != "PENDING":
            raise InvalidStateTransitionError(f"Approval request is already in status '{approval.status}'.")

        if status not in ["APPROVED", "REJECTED"]:
            raise ValueError("Approval response status must be either APPROVED or REJECTED.")

        # Update approval record
        approval = await self.approval_repo.update_status(
            db=db,
            approval_id=approval_id,
            status=status,
            approved_by=approver_user_id,
            expected_version=approval.version,
            rejection_reason=rejection_reason
        )

        # Get step & task context
        from app.models.automation import PlanStep
        res = await db.execute(select(PlanStep).where(PlanStep.id == approval.step_id))
        step = res.scalars().first()
        if step:
            plan = await self.plan_repo.get_by_id(db, step.plan_id)
            if plan:
                task = await self.task_repo.get_by_id(db, plan.task_id, approval.requested_by or approver_user_id)
                if task:
                    event_type = "ApprovalGranted" if status == "APPROVED" else "ApprovalRejected"
                    event = TaskEvent(
                        task_id=task.id,
                        event_type=event_type,
                        payload={"approval_id": str(approval.id), "step_id": str(step.id)}
                    )
                    db.add(event)

                    if status == "APPROVED":
                        # Transition task back to EXECUTING (via TaskService)
                        await self.task_service.transition_task_status(db, task.id, task.user_id, TaskStatus.EXECUTING)
                        
                        # Step status transitions back to EXECUTING
                        step.status = "EXECUTING"
                        db.add(step)
                    else:
                        # Rejection transitions task to FAILED (via TaskService)
                        await self.task_service.transition_task_status(db, task.id, task.user_id, TaskStatus.FAILED)

                        # Step status transitions to FAILED
                        step.status = "FAILED"
                        step.error_message = rejection_reason or "Execution rejected by user."
                        step.completed_at = datetime.now(timezone.utc)
                        db.add(step)

        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to respond to approval, rolling back. Error: {e}")
            raise e

        await db.refresh(approval)
        return approval
