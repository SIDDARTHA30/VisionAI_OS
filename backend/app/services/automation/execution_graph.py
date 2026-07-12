import time
import uuid
from typing import Dict, List, Optional, Any
from pydantic import BaseModel


class StepNode(BaseModel):
    step_id: uuid.UUID
    step_number: int
    tool_name: str
    depends_on: List[int] = []
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration_ms: Optional[int] = None


class ExecutionGraph(BaseModel):
    """Execution step graph tracking dependencies and execution states."""
    plan_id: uuid.UUID
    nodes: Dict[int, StepNode] = {}

    def build_from_steps(self, steps: List[Any]) -> None:
        """Hydrate graph structures from PlanStep records."""
        for step in steps:
            self.nodes[step.step_number] = StepNode(
                step_id=step.id,
                step_number=step.step_number,
                tool_name=step.tool_name,
                depends_on=step.depends_on or [],
                status=step.status
            )

    def mark_running(self, step_number: int) -> None:
        if step_number in self.nodes:
            node = self.nodes[step_number]
            node.status = "RUNNING"
            node.start_time = time.time()

    def mark_finished(self, step_number: int, success: bool) -> None:
        if step_number in self.nodes:
            node = self.nodes[step_number]
            node.status = "COMPLETED" if success else "FAILED"
            node.end_time = time.time()
            if node.start_time:
                node.duration_ms = int((node.end_time - node.start_time) * 1000)

    def get_ready_steps(self) -> List[StepNode]:
        """Exposes list of steps whose dependencies are completed successfully."""
        ready = []
        completed_step_nums = {num for num, node in self.nodes.items() if node.status == "COMPLETED"}
        for num, node in self.nodes.items():
            if node.status == "PENDING":
                # Check if all dependencies are in completed list
                if all(dep in completed_step_nums for dep in node.depends_on):
                    ready.append(node)
        return ready

    def is_fully_completed(self) -> bool:
        return all(node.status == "COMPLETED" for node in self.nodes.values())

    def has_failures(self) -> bool:
        return any(node.status == "FAILED" for node in self.nodes.values())
