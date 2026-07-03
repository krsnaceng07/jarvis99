"""JARVIS OS - Plan Version Manager.

Tracks execution plan historical iterations, rollbacks, state snapshots, and structural diffs.
"""

from typing import Any, Dict

from core.reasoning.engine_dto import ExecutionPlan


class PlanVersionManager:
    """Manages sequential execution plan revisions, diffing, and rollbacks."""

    def __init__(self) -> None:
        """Initialize PlanVersionManager."""
        self.versions: Dict[int, Dict[str, Any]] = {}
        self.latest_version: int = 0

    def create_version(self, plan: ExecutionPlan) -> int:
        """Snapshot and log the execution plan state under a new version sequence.

        Args:
            plan: The active ExecutionPlan to snapshot.

        Returns:
            The created version sequence integer.
        """
        version = plan.plan_version
        self.versions[version] = self.snapshot(plan)
        if version > self.latest_version:
            self.latest_version = version
        return version

    def snapshot(self, plan: ExecutionPlan) -> Dict[str, Any]:
        """Convert the ExecutionPlan DTO to a serializable dictionary format.

        Args:
            plan: ExecutionPlan DTO.

        Returns:
            Dictionary payload representation.
        """
        return plan.model_dump()

    def rollback(self, version: int) -> ExecutionPlan:
        """Restore the ExecutionPlan state from historical snapshot registries.

        Args:
            version: Target version key to roll back to.

        Returns:
            ExecutionPlan DTO.
        """
        if version not in self.versions:
            raise KeyError(f"Plan version {version} not found in version registry.")

        data = self.versions[version]
        return ExecutionPlan.model_validate(data)

    def diff(self, old_plan: ExecutionPlan, new_plan: ExecutionPlan) -> Dict[str, Any]:
        """Generate a structural diff log comparing two execution plan version states.

        Args:
            old_plan: Base historical plan version.
            new_plan: Target newly updated plan version.

        Returns:
            Dictionary listing structural changes (added, modified, or deleted tasks).
        """
        diff_report: Dict[str, Any] = {
            "old_version": old_plan.plan_version,
            "new_version": new_plan.plan_version,
            "added_tasks": [],
            "removed_tasks": [],
            "modified_tasks": [],
        }

        # Index tasks by ID
        old_tasks = {}
        for wave in old_plan.waves:
            for task in wave.tasks:
                old_tasks[task.task_id] = task

        new_tasks = {}
        for wave in new_plan.waves:
            for task in wave.tasks:
                new_tasks[task.task_id] = task

        # Find added and modified
        for tid, task in new_tasks.items():
            if tid not in old_tasks:
                diff_report["added_tasks"].append(
                    {"task_id": str(tid), "tool_name": task.tool_name}
                )
            else:
                old_t = old_tasks[tid]
                if (
                    old_t.arguments != task.arguments
                    or old_t.tool_name != task.tool_name
                ):
                    diff_report["modified_tasks"].append(
                        {
                            "task_id": str(tid),
                            "changes": {
                                "old_tool": old_t.tool_name,
                                "new_tool": task.tool_name,
                                "old_args": old_t.arguments,
                                "new_args": task.arguments,
                            },
                        }
                    )

        # Find removed
        for tid, task in old_tasks.items():
            if tid not in new_tasks:
                diff_report["removed_tasks"].append(
                    {"task_id": str(tid), "tool_name": task.tool_name}
                )

        return diff_report

    def current_version(self) -> int:
        """Fetch the sequence sequence integer of the latest plan version.

        Returns:
            The latest logged plan version sequence key.
        """
        return self.latest_version
