"""
PHASE: 21
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 21 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Literal, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.reasoning.goal import GoalAnalysis


class TaskStatus(str, Enum):
    """Execution status states for planning tasks."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Categorized domain types for tasks."""

    CODE = "code"
    COMMAND = "command"
    SEARCH = "search"
    FILE_OP = "file_op"
    API = "api"
    MEMORY = "memory"
    HUMAN = "human"
    SYSTEM = "system"


class ExecutorType(str, Enum):
    """Target execution runtime systems."""

    LLM = "llm"
    PYTHON = "python"
    SHELL = "shell"
    BROWSER = "browser"
    API = "api"
    MEMORY = "memory"
    HUMAN = "human"
    FILE = "file"


class AgentTerminationReason(str, Enum):
    """Enumeration of reasons an Agent Loop may terminate."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    ITERATION_LIMIT = "ITERATION_LIMIT"
    HUMAN_ABORT = "HUMAN_ABORT"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"


class Task(BaseModel):
    """Granular unit of work representing a single step of the plan."""

    id: UUID = Field(default_factory=uuid4)
    goal_id: UUID
    executor: ExecutorType
    task_type: TaskType
    payload: Dict[str, Any] = Field(default_factory=dict)
    dependencies: Set[UUID] = Field(default_factory=set)
    constraints: List[str] = Field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_tokens: int = 0
    timeout: float = 300.0
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    schema_version: Literal["1.0"] = "1.0"


class TaskGenerator:
    """Task Decomposer. Converts analysed goal targets to structured Tasks."""

    def decompose(self, analysis: GoalAnalysis, goal_text: str) -> List[Task]:
        tasks: List[Task] = []
        text = goal_text.lower()

        # Rule-based heuristics to extract actions
        # 1. Search actions
        search_terms = re.findall(r"search\s+for\s+([^,.\n#]+)", text)
        for term in search_terms:
            tasks.append(
                Task(
                    goal_id=analysis.goal_id,
                    executor=ExecutorType.MEMORY,
                    task_type=TaskType.SEARCH,
                    payload={"query": term.strip()},
                    estimated_cost=0.01,
                    estimated_tokens=100,
                )
            )

        # 2. File actions
        file_matches = re.findall(
            r"(?:read|write|edit)\s+file\s+([a-zA-Z0-9_/.\\]+)", text
        )
        for filename in file_matches:
            tasks.append(
                Task(
                    goal_id=analysis.goal_id,
                    executor=ExecutorType.PYTHON,
                    task_type=TaskType.FILE_OP,
                    payload={"file_path": filename.strip()},
                    estimated_cost=0.02,
                    estimated_tokens=200,
                )
            )

        # 3. Command execution actions
        cmd_matches = re.findall(r"run\s+command\s*:\s*([^#\n]+)", text)
        for cmd in cmd_matches:
            tasks.append(
                Task(
                    goal_id=analysis.goal_id,
                    executor=ExecutorType.SHELL,
                    task_type=TaskType.COMMAND,
                    payload={"command": cmd.strip()},
                    estimated_cost=0.05,
                    estimated_tokens=500,
                )
            )

        # Fallback: if no specific subtasks are matched, create a generic LLM plan task
        if not tasks:
            tasks.append(
                Task(
                    goal_id=analysis.goal_id,
                    executor=ExecutorType.LLM,
                    task_type=TaskType.SYSTEM,
                    payload={"instruction": goal_text},
                    estimated_cost=0.10,
                    estimated_tokens=1000,
                )
            )

        # Assign basic dependency chain if multiple tasks are generated
        # Task 2 depends on Task 1, Task 3 on Task 2, etc.
        for idx in range(1, len(tasks)):
            tasks[idx].dependencies.add(tasks[idx - 1].id)

        return tasks
