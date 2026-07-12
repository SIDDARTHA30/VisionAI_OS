import logging
from app.events.event_models import AutomationEvent
from app.events.event_bus import event_bus

logger = logging.getLogger("app.events.event_dispatcher")


class EventDispatcher:
    """Architectural placeholder for dispatching automation tasks audit logs."""

    @staticmethod
    def dispatch(task_id: str, event_type: str, payload: dict) -> None:
        import uuid
        try:
            event = AutomationEvent(
                task_id=uuid.UUID(str(task_id)),
                event_type=event_type,
                payload=payload
            )
            event_bus.publish(event)
        except Exception as e:
            logger.error(f"Failed to dispatch event {event_type}: {e}")
