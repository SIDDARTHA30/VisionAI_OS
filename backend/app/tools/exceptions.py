class ToolException(Exception):
    """Base exception for all plugin tool errors."""
    pass


class ToolExecutionException(ToolException):
    """Raised when execution of tool fails."""
    pass


class ToolValidationException(ToolException):
    """Raised when validation of arguments fails."""
    pass
