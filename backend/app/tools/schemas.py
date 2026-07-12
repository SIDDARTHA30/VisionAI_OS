from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Schema defining a tool for model discovery."""
    name: str
    description: str
    input_schema: dict
    output_schema: dict
