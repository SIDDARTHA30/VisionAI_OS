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


class PlannerLLMError(AutomationError):
    """Raised when the LLM provider fails to generate a response."""
    pass


class PlannerTimeoutError(PlannerLLMError):
    """Raised when plan generation fails to complete within limits."""
    pass


class PlannerValidationError(AutomationError):
    """Raised when the generated plan violates schemas or validation rules."""
    pass


class PlannerRetryExceeded(PlannerValidationError):
    """Raised when prompt correction retry attempts are exhausted."""
    pass


class PlannerDependencyError(PlannerValidationError):
    """Raised when plan steps have invalid or circular dependencies."""
    pass


class PlannerContextError(AutomationError):
    """Raised when conversation history or context fails to build."""
    pass


class PlannerPromptError(AutomationError):
    """Raised when prompt formatting template injection crashes."""
    pass
