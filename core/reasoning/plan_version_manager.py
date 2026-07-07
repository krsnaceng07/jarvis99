"""JARVIS OS - Plan Version Manager.

Tracks execution plan historical iterations, rollbacks, state snapshots, and structural diffs.
"""

from enum import Enum
from typing import Any, Dict

from core.reasoning.engine_dto import ExecutionPlan


class PlanVersionManager:
    """Manages sequential execution plan revisions, diffing, and rollbacks."""

    def __init__(self) -> None:
        """Initialize PlanVersionManager."""
        self.versions: Dict[int, Dict[str, Any]] = {}
        self.latest_version: int = 0
        self.plan_types: Dict[int, Any] = {}

    def create_version(self, plan: Any) -> int:
        """Snapshot and log the execution plan state under a new version sequence.

        Args:
            plan: The active ExecutionPlan to snapshot.

        Returns:
            The created version sequence integer.
        """
        version = getattr(plan, "plan_version", None)
        if version is None:
            metadata = getattr(plan, "metadata", {})
            version = metadata.get("plan_version", 1)
        self.versions[version] = self.snapshot(plan)
        self.plan_types[version] = type(plan)
        if version > self.latest_version:
            self.latest_version = version
        return version

    def snapshot(self, plan: Any) -> Dict[str, Any]:
        """Convert the ExecutionPlan DTO to a serializable dictionary format.

        Args:
            plan: ExecutionPlan DTO.

        Returns:
            Dictionary payload representation.
        """
        return plan.model_dump()

    def rollback(self, version: int) -> Any:
        """Restore the ExecutionPlan state from historical snapshot registries.

        Args:
            version: Target version key to roll back to.

        Returns:
            ExecutionPlan DTO.
        """
        if version not in self.versions:
            raise KeyError(f"Plan version {version} not found in version registry.")

        data = self.versions[version]
        plan_cls = self.plan_types.get(version, ExecutionPlan)
        return plan_cls.model_validate(data)

    def diff(self, old_plan: Any, new_plan: Any) -> Dict[str, Any]:
        """Generate a structural diff log comparing two execution plan version states.

        Args:
            old_plan: Base historical plan version.
            new_plan: Target newly updated plan version.

        Returns:
            Dictionary listing structural changes (added, modified, or deleted tasks).
        """
        old_v = getattr(old_plan, "plan_version", None)
        if old_v is None:
            metadata = getattr(old_plan, "metadata", {})
            old_v = metadata.get("plan_version", 1)

        new_v = getattr(new_plan, "plan_version", None)
        if new_v is None:
            metadata = getattr(new_plan, "metadata", {})
            new_v = metadata.get("plan_version", 1)

        diff_report: Dict[str, Any] = {
            "old_version": old_v,
            "new_version": new_v,
            "added_tasks": [],
            "removed_tasks": [],
            "modified_tasks": [],
        }

        # Index tasks by ID
        old_tasks = {}
        if hasattr(old_plan, "tasks") and isinstance(old_plan.tasks, list):
            for task in old_plan.tasks:
                tid = getattr(task, "id", getattr(task, "task_id", None))
                old_tasks[tid] = task
        else:
            for wave in old_plan.waves:
                for task in wave.tasks:
                    old_tasks[task.task_id] = task

        new_tasks = {}
        if hasattr(new_plan, "tasks") and isinstance(new_plan.tasks, list):
            for task in new_plan.tasks:
                tid = getattr(task, "id", getattr(task, "task_id", None))
                new_tasks[tid] = task
        else:
            for wave in new_plan.waves:
                for task in wave.tasks:
                    new_tasks[task.task_id] = task

        # Find added and modified
        for tid, task in new_tasks.items():
            tool_name = getattr(task, "tool_name", getattr(task, "task_type", None))
            if isinstance(tool_name, Enum):
                tool_name = tool_name.value
            arguments = getattr(task, "arguments", getattr(task, "payload", {}))

            if tid not in old_tasks:
                diff_report["added_tasks"].append(
                    {"task_id": str(tid), "tool_name": tool_name}
                )
            else:
                old_t = old_tasks[tid]
                old_tool = getattr(old_t, "tool_name", getattr(old_t, "task_type", None))
                if isinstance(old_tool, Enum):
                    old_tool = old_tool.value
                old_args = getattr(old_t, "arguments", getattr(old_t, "payload", {}))

                if old_args != arguments or old_tool != tool_name:
                    diff_report["modified_tasks"].append(
                        {
                            "task_id": str(tid),
                            "changes": {
                                "old_tool": old_tool,
                                "new_tool": tool_name,
                                "old_args": old_args,
                                "new_args": arguments,
                            },
                        }
                    )

        # Find removed
        for tid, task in old_tasks.items():
            if tid not in new_tasks:
                tool_name = getattr(task, "tool_name", getattr(task, "task_type", None))
                if isinstance(tool_name, Enum):
                    tool_name = tool_name.value
                diff_report["removed_tasks"].append(
                    {"task_id": str(tid), "tool_name": tool_name}
                )

        return diff_report

    def current_version(self) -> int:
        """Fetch the sequence sequence integer of the latest plan version.

        Returns:
            The latest logged plan version sequence key.
        """
        return self.latest_version
