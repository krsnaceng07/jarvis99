"""JARVIS OS - Agent Context and Budget Manager.

Encapsulates active session metadata and enforces execution budget constraints (tokens, cost, time, memory).
"""

import time
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from core.exceptions import JarvisAgentError
from core.runtime.dto import ExecutionBudget


class AgentContextManager:
    """Manages sandboxed task variables and verifies real-time usage budgets."""

    def __init__(
        self,
        budget: Optional[ExecutionBudget] = None,
        session_id: Optional[UUID] = None,
    ) -> None:
        """Initialize AgentContextManager.

        Args:
            budget: Target constraints. Defaults to standard ExecutionBudget.
            session_id: Optional existing session UUID.
        """
        self.session_id = session_id or uuid4()
        self.budget = budget or ExecutionBudget()
        self.variables: Dict[str, Any] = {}

        # Usage tracking state
        self.accumulated_tokens: int = 0
        self.accumulated_cost: float = 0.0
        self.current_memory_mb: int = 0
        self.start_time: float = time.time()

    def update_token_usage(self, count: int) -> None:
        """Accumulate token consumption and verify budget boundaries.

        Args:
            count: Additional tokens consumed.

        Raises:
            JarvisAgentError: If the token limit has been breached.
        """
        self.accumulated_tokens += count
        if self.accumulated_tokens > self.budget.max_tokens:
            raise JarvisAgentError(
                code="AGENT_003",
                message=(
                    f"Token budget exceeded. Consumed {self.accumulated_tokens} "
                    f"tokens, limit is {self.budget.max_tokens}."
                ),
            )

    def update_cost(self, usd: float) -> None:
        """Accumulate API cost and verify budget boundaries.

        Args:
            usd: Additional USD cost incurred.

        Raises:
            JarvisAgentError: If the financial limit has been breached.
        """
        self.accumulated_cost += usd
        if self.accumulated_cost > self.budget.max_cost:
            raise JarvisAgentError(
                code="AGENT_003",
                message=(
                    f"Financial budget exceeded. Incurred ${self.accumulated_cost:.4f} "
                    f"USD, limit is ${self.budget.max_cost:.4f} USD."
                ),
            )

    def update_memory_usage(self, memory_mb: int) -> None:
        """Update active memory footprint and verify RAM limits.

        Args:
            memory_mb: Active memory in megabytes.

        Raises:
            JarvisAgentError: If the memory allocation limit has been breached.
        """
        self.current_memory_mb = memory_mb
        if (
            self.budget.max_memory_mb
            and self.current_memory_mb > self.budget.max_memory_mb
        ):
            raise JarvisAgentError(
                code="AGENT_003",
                message=(
                    f"Memory budget exceeded. Consuming {self.current_memory_mb} MB, "
                    f"limit is {self.budget.max_memory_mb} MB."
                ),
            )

    def check_duration(self) -> None:
        """Compute execution duration and verify time limits.

        Raises:
            JarvisAgentError: If the execution time limit has been breached.
        """
        elapsed = time.time() - self.start_time
        if elapsed > self.budget.max_duration:
            raise JarvisAgentError(
                code="AGENT_003",
                message=(
                    f"Duration limit exceeded. Running for {elapsed:.1f}s, "
                    f"limit is {self.budget.max_duration}s."
                ),
            )

    def check_all_budgets(self) -> None:
        """Perform validation check across all tracked resource metrics.

        Raises:
            JarvisAgentError: If any resource constraint has been violated.
        """
        self.check_duration()
        self.update_token_usage(0)
        self.update_cost(0.0)
        self.update_memory_usage(self.current_memory_mb)

    def set_variable(self, key: str, value: Any) -> None:
        """Set a value in the sandboxed variables context.

        Args:
            key: Variable configuration name.
            value: Variable contents.
        """
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a value from the sandboxed variables context.

        Args:
            key: Variable configuration name.
            default: Fallback value if name is not found.

        Returns:
            The variable contents or default fallback.
        """
        return self.variables.get(key, default)
