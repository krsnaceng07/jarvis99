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

    _EXECUTOR_MAP = {
        "llm": (ExecutorType.LLM, TaskType.SYSTEM),
        "python": (ExecutorType.PYTHON, TaskType.CODE),
        "shell": (ExecutorType.SHELL, TaskType.COMMAND),
        "browser": (ExecutorType.BROWSER, TaskType.SEARCH),
        "api": (ExecutorType.API, TaskType.API),
        "file": (ExecutorType.FILE, TaskType.FILE_OP),
        "memory": (ExecutorType.MEMORY, TaskType.MEMORY),
        "human": (ExecutorType.HUMAN, TaskType.HUMAN),
    }

    def __init__(self, llm_runtime: Any = None) -> None:
        self._llm_runtime = llm_runtime

    async def decompose_with_llm(
        self, analysis: GoalAnalysis, goal_text: str
    ) -> List[Task]:
        """LLM-driven decomposition with regex fallback."""
        if self._llm_runtime is not None:
            tasks = await self._llm_decompose(analysis, goal_text)
            if tasks:
                return tasks

        return self.decompose(analysis, goal_text)

    async def _llm_decompose(
        self, analysis: GoalAnalysis, goal_text: str
    ) -> List[Task]:
        """Use LLM to decompose goal into typed Task objects."""
        import json as _json
        import logging as _logging

        from core.tools.llm_runtime import LlmRequest

        _logger = _logging.getLogger(__name__)

        prompt = (
            "Decompose the following goal into 2-6 discrete, actionable tasks.\n\n"
            "Each task must specify:\n"
            '- "description": what to do (specific and actionable)\n'
            '- "executor": one of "llm", "python", "shell", "browser", '
            '"api", "file", "memory", "human"\n'
            '- "estimated_cost": estimated USD cost (float)\n'
            '- "estimated_tokens": estimated token count (int)\n\n'
            "Return ONLY a valid JSON array. No explanation, no markdown fences.\n\n"
            f"Goal: {goal_text}"
        )

        for attempt in range(2):
            try:
                request = LlmRequest(
                    prompt=prompt,
                    system_prompt=(
                        "You are a precise task decomposition engine. "
                        "Output ONLY valid JSON. No markdown, no commentary."
                    ),
                    category="planning",
                    max_tokens=800,
                    temperature=0.0,
                )
                response = await self._llm_runtime.generate(request)
                if response.error:
                    _logger.warning(
                        "TaskGenerator LLM attempt %d error: %s", attempt, response.error
                    )
                    continue

                tasks = self._parse_llm_tasks(response.text, analysis)
                if tasks:
                    return tasks

                prompt = (
                    "Your previous response was not valid JSON. "
                    "Return ONLY a JSON array for this goal:\n"
                    f"{goal_text}\n\n"
                    "Example:\n"
                    '[{"description": "Research the topic", '
                    '"executor": "llm", "estimated_cost": 0.02, '
                    '"estimated_tokens": 200}]'
                )
            except Exception as e:
                _logger.warning("TaskGenerator LLM attempt %d exception: %s", attempt, e)

        return []

    def _parse_llm_tasks(
        self, text: str, analysis: GoalAnalysis
    ) -> List[Task]:
        """Parse LLM output into Task objects."""
        import json as _json

        try:
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            parsed = _json.loads(cleaned)
            if isinstance(parsed, dict) and "tasks" in parsed:
                parsed = parsed["tasks"]
            if not isinstance(parsed, list) or len(parsed) == 0:
                return []

            tasks: List[Task] = []
            for item in parsed:
                executor_key = item.get("executor", "llm").lower()
                executor_type, task_type = self._EXECUTOR_MAP.get(
                    executor_key, (ExecutorType.LLM, TaskType.SYSTEM)
                )
                payload: Dict[str, Any] = {}
                desc = item.get("description", "")
                if executor_type == ExecutorType.LLM:
                    payload["instruction"] = desc
                elif executor_type == ExecutorType.SHELL:
                    payload["command"] = item.get("command", desc)
                elif executor_type == ExecutorType.PYTHON:
                    payload["code"] = item.get("code", desc)
                elif executor_type in (ExecutorType.FILE,):
                    payload["file_path"] = item.get("file_path", desc)
                elif executor_type == ExecutorType.MEMORY:
                    payload["query"] = item.get("query", desc)
                elif executor_type == ExecutorType.API:
                    payload["endpoint"] = item.get("endpoint", desc)
                elif executor_type == ExecutorType.BROWSER:
                    payload["url"] = item.get("url", desc)
                else:
                    payload["instruction"] = desc

                tasks.append(
                    Task(
                        goal_id=analysis.goal_id,
                        executor=executor_type,
                        task_type=task_type,
                        payload=payload,
                        estimated_cost=float(item.get("estimated_cost", 0.05)),
                        estimated_tokens=int(item.get("estimated_tokens", 500)),
                    )
                )

            for idx in range(1, len(tasks)):
                tasks[idx].dependencies.add(tasks[idx - 1].id)

            return tasks
        except Exception:
            return []

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
