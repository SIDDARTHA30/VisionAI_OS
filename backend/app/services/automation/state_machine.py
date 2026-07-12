from typing import Dict, List
from app.models.automation import TaskStatus, VALID_TRANSITIONS


class TaskStateMachine:
    """Handles and validates state transitions for automation tasks."""

    @staticmethod
    def validate_transition(current_status: TaskStatus, target_status: TaskStatus) -> bool:
        """
        Check if a transition from current_status to target_status is valid.
        Returns True if valid, False otherwise.
        """
        # A status can transition to itself (e.g. no-op update)
        if current_status == target_status:
            return True
            
        allowed = VALID_TRANSITIONS.get(current_status, [])
        return target_status in allowed

    @classmethod
    def transition(cls, current_status: TaskStatus, target_status: TaskStatus) -> TaskStatus:
        """
        Transition task state. Raises ValueError if the transition is illegal.
        """
        if not cls.validate_transition(current_status, target_status):
            raise ValueError(
                f"Illegal state transition: Cannot change status from '{current_status.value}' to '{target_status.value}'."
            )
        return target_status
