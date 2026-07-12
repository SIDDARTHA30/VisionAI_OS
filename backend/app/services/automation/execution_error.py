from app.services.automation.exceptions import AutomationError


class BaseExecutionError(AutomationError):
    """Base exception class for execution engine operations."""
    pass


class RetryableError(BaseExecutionError):
    """Errors that can be retried (e.g. rate limit blocks, transient network errors)."""
    pass


class PermanentError(BaseExecutionError):
    """Unrecoverable failures where retrying will not change the outcome (e.g. invalid arguments)."""
    pass


class ToolExecutionError(BaseExecutionError):
    """Raised when tool execution crashes or yields failing returns."""
    pass


class DependencyError(BaseExecutionError):
    """Raised when dependent step runs crash or cannot be resolved."""
    pass


class CancellationError(BaseExecutionError):
    """Raised when step run gets cancelled gracefully by user request."""
    pass


class TimeoutError(BaseExecutionError):
    """Raised when step run exceeds timeout parameters."""
    pass
