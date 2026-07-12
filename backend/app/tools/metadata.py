from typing import List
from pydantic import BaseModel, ConfigDict
from app.tools.enums import ToolCategory, ToolCapability, PermissionLevel


class ToolMetadata(BaseModel):
    name: str
    version: str
    author: str
    category: ToolCategory
    capabilities: List[ToolCapability]
    description: str
    permissions: List[PermissionLevel]
    timeout_sec: int
    tags: List[str] = []
    supported_platforms: List[str] = ["linux", "darwin", "win32"]

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True
    )
