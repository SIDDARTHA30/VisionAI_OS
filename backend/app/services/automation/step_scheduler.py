import logging
from typing import List
from app.services.automation.execution_graph import ExecutionGraph, StepNode
from app.services.automation.execution_queue import BaseExecutionQueue

logger = logging.getLogger(__name__)


class StepScheduler:
    """Discovers executable tasks and queues ready steps based on dependency graphs."""

    def __init__(self, queue: BaseExecutionQueue):
        self._queue = queue

    async def schedule_ready_steps(self, graph: ExecutionGraph) -> List[int]:
        """Looks up pending steps with completed dependencies and schedules them."""
        ready_nodes = graph.get_ready_steps()
        scheduled_step_nums = []
        for node in ready_nodes:
            # Mark step as RUNNING immediately in the graph to avoid duplicate schedulings
            graph.mark_running(node.step_number)
            
            logger.info(f"Scheduling step {node.step_number} ({node.tool_name}) for execution.")
            await self._queue.enqueue(node.step_number)
            scheduled_step_nums.append(node.step_number)
            
        return scheduled_step_nums
