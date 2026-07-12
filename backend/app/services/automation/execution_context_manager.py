import logging
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Any
from app.services.automation.execution_context import ExecutionContext
from app.services.automation.resource_manager import resource_manager

logger = logging.getLogger(__name__)


class ExecutionContextManager:
    """Manages setup and tear-down operations for active execution environments."""

    def __init__(self):
        self._temp_root = Path(tempfile.gettempdir()) / "visionai_exec"
        self._temp_root.mkdir(parents=True, exist_ok=True)

    def create_context(
        self,
        task_id: uuid.UUID,
        plan_id: uuid.UUID,
        execution_id: uuid.UUID,
        user_id: int,
        initial_vars: Dict[str, Any] = None
    ) -> ExecutionContext:
        """Provisions sandbox directories and initializes context."""
        exec_root = self._temp_root / str(execution_id)
        workspace = exec_root / "workspace"
        temp_dir = exec_root / "temp"

        # Create folders
        workspace.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Register directories for auto-cleanup
        resource_manager.register_workspace(exec_root)

        logger.info(f"Initialized sandbox workspaces for execution {execution_id}.")

        return ExecutionContext(
            request_id=uuid.uuid4(),
            task_id=task_id,
            plan_id=plan_id,
            execution_id=execution_id,
            user_id=user_id,
            workspace=workspace,
            temp_dir=temp_dir,
            variables=initial_vars or {}
        )

    def dispose_context(self, context: ExecutionContext) -> None:
        """Cleans up active resources and deletes sandbox files."""
        # Find temp root folder for this execution ID
        exec_root = self._temp_root / str(context.execution_id)
        resource_manager.clean_workspace(exec_root)
        logger.info(f"Disposed execution environment context: {context.execution_id}")
