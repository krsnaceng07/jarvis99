"""JARVIS OS - Agent Runtime State Machine.

Defines enums and transition validation rules for agent lifecycles and loop states.
"""

from enum import Enum
from typing import Dict, Set

from core.exceptions import JarvisAgentError


class SubagentState(str, Enum):
    """Enums representing the overall instance lifecycle states of a subagent."""

    CREATE = "CREATE"
    INITIALIZE = "INITIALIZE"
    READY = "READY"
    WORKING = "WORKING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    DESTROYED = "DESTROYED"


class AgentExecutionState(str, Enum):
    """Enums representing the generic execution loop steps within the WORKING state."""

    IDLE = "IDLE"
    LOAD = "LOAD"
    DISPATCH = "DISPATCH"
    WAIT = "WAIT"
    VERIFY = "VERIFY"
    PERSIST = "PERSIST"
    SLEEP = "SLEEP"


class AgentStateTransitionManager:
    """Enforces state loop sequences and transition path validation rules."""

    _SUBAGENT_TRANSITIONS: Dict[SubagentState, Set[SubagentState]] = {
        SubagentState.CREATE: {SubagentState.INITIALIZE, SubagentState.DESTROYED},
        SubagentState.INITIALIZE: {SubagentState.READY, SubagentState.DESTROYED},
        SubagentState.READY: {SubagentState.WORKING, SubagentState.DESTROYED},
        SubagentState.WORKING: {
            SubagentState.WAITING,
            SubagentState.COMPLETED,
            SubagentState.DESTROYED,
        },
        SubagentState.WAITING: {SubagentState.WORKING, SubagentState.DESTROYED},
        SubagentState.COMPLETED: {SubagentState.ARCHIVED, SubagentState.DESTROYED},
        SubagentState.ARCHIVED: {SubagentState.DESTROYED},
        SubagentState.DESTROYED: {SubagentState.DESTROYED},
    }

    _EXECUTION_TRANSITIONS: Dict[AgentExecutionState, Set[AgentExecutionState]] = {
        AgentExecutionState.IDLE: {AgentExecutionState.LOAD},
        AgentExecutionState.LOAD: {
            AgentExecutionState.DISPATCH,
            AgentExecutionState.PERSIST,
        },
        AgentExecutionState.DISPATCH: {
            AgentExecutionState.WAIT,
            AgentExecutionState.PERSIST,
        },
        AgentExecutionState.WAIT: {
            AgentExecutionState.VERIFY,
            AgentExecutionState.PERSIST,
        },
        AgentExecutionState.VERIFY: {AgentExecutionState.PERSIST},
        AgentExecutionState.PERSIST: {AgentExecutionState.SLEEP},
        AgentExecutionState.SLEEP: {AgentExecutionState.IDLE},
    }

    @classmethod
    def validate_subagent_transition(
        cls, current: SubagentState, target: SubagentState
    ) -> None:
        """Validate if a subagent instance state transition is allowed.

        Args:
            current: Current SubagentState.
            target: Intended target SubagentState.

        Raises:
            JarvisAgentError: If the transition path is invalid.
        """
        allowed = cls._SUBAGENT_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise JarvisAgentError(
                code="AGENT_001",
                message=f"Invalid subagent transition path: {current} -> {target}",
            )

    @classmethod
    def validate_execution_transition(
        cls, current: AgentExecutionState, target: AgentExecutionState
    ) -> None:
        """Validate if an agent execution loop state transition is allowed.

        Args:
            current: Current AgentExecutionState.
            target: Intended target AgentExecutionState.

        Raises:
            JarvisAgentError: If the transition path is invalid.
        """
        allowed = cls._EXECUTION_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise JarvisAgentError(
                code="AGENT_001",
                message=f"Invalid execution loop transition path: {current} -> {target}",
            )
