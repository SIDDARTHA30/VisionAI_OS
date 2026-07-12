class ToolError(Exception):
    """Base exception for all tool related failures."""
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ToolValidationError(ToolError):
    """Raised when parameters or constraints fail validations."""
    pass


class ToolPermissionError(ToolError):
    """Raised when access rules or security allowlists block tool runs."""
    pass


class ToolTimeoutError(ToolError):
    """Raised when tool execution exceeds time limits."""
    pass


class ToolExecutionError(ToolError):
    """Raised when underlying tool code crashes."""
    pass


class ToolCleanupError(ToolError):
    """Raised when resources or workspaces fail to get cleaned up."""
    pass


class ToolRegistryError(ToolError):
    """Raised when registrations or lookups fail."""
    pass
