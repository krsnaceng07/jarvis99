"""JARVIS OS - Persistent Execution Journal.

Subclass of ExecutionJournal that fires events for DB persistence on each cycle.
"""

import asyncio
from typing import Optional
from uuid import UUID

from core.interfaces import EventBusInterface, InterAgentMessage
from core.reasoning.journal import ExecutionJournal


class PersistentExecutionJournal(ExecutionJournal):
    """Subclass of ExecutionJournal that automatically broadcasts records for durability."""

    def __init__(self, session_id: UUID, event_bus: EventBusInterface) -> None:
        """Initialize PersistentExecutionJournal.

        Args:
            session_id: Target reasoning session run UUID.
            event_bus: EventBus connection.
        """
        super().__init__()
        self.session_id = session_id
        self.event_bus = event_bus

    def record_iteration(
        self,
        *,
        iteration: int,
        goal_description: str = "",
        chosen_executor: str = "",
        reasoning: str = "",
        output_summary: str = "",
        reflection_category: Optional[str] = None,
        next_action: str = "CONTINUE",
    ) -> None:
        """Record an iteration and fire a telemetry update event."""
        super().record_iteration(
            iteration=iteration,
            goal_description=goal_description,
            chosen_executor=chosen_executor,
            reasoning=reasoning,
            output_summary=output_summary,
            reflection_category=reflection_category,
            next_action=next_action,
        )

        # Retrieve last record
        record = self._records[-1]

        # Broadcast event
        msg = InterAgentMessage(
            sender="PersistentExecutionJournal",
            receiver="PersistenceService",
            action="journal.iteration.recorded",
            correlation_id=self.session_id,
            body=record.model_dump(mode="json"),
        )
        asyncio.create_task(self.event_bus.publish("journal.iteration.recorded", msg))
