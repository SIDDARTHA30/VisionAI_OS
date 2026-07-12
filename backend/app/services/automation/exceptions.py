class AutomationError(Exception):
    """Base class for all automation engine errors."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InvalidStateTransitionError(AutomationError):
    """Raised when a status transition violates the state machine map."""
    pass


class ConcurrencyConflictError(AutomationError):
    """Raised when an optimistic locking check fails."""
    pass


class ApprovalRequiredError(AutomationError):
    """Raised when executing a step that has not been approved."""
    pass


class ExecutionNotFoundError(AutomationError):
    """Raised when an execution context cannot be found."""
    pass


class TaskNotFoundError(AutomationError):
    """Raised when a task is missing or access is denied."""
    pass
