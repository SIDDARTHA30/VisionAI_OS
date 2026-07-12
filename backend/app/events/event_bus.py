from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List
import logging
from app.events.event_models import AutomationEvent

logger = logging.getLogger("app.events.event_bus")


class IEventBus(ABC):
    """Abstract interface defining the Event Bus contract."""

    @abstractmethod
    def subscribe(self, event_type: str, handler: Callable[[AutomationEvent], Any]) -> None:
        """Subscribes a handler to a specific event type."""
        pass

    @abstractmethod
    def publish(self, event: AutomationEvent) -> None:
        """Publishes an event to all registered handlers for its type."""
        pass


class InMemoryEventBus(IEventBus):
    """InMemory implementation of the interface-based IEventBus."""

    def __init__(self):
        self._listeners: Dict[str, List[Callable[[AutomationEvent], Any]]] = {}

    def subscribe(self, event_type: str, handler: Callable[[AutomationEvent], Any]) -> None:
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(handler)
        logger.info(f"Subscribed handler to event: {event_type}")

    def publish(self, event: AutomationEvent) -> None:
        logger.info(f"Publishing event {event.event_type} for task {event.task_id}")
        listeners = self._listeners.get(event.event_type, [])
        for listener in listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"Error executing event listener for {event.event_type}: {e}")


# Singleton instance matching interface
event_bus: IEventBus = InMemoryEventBus()
