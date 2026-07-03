"""JARVIS OS - Wave Result Aggregator.

Consolidates outputs, errors, durations, status codes, and output artifacts
from multiple parallel/sequential tool runs in a wave.
"""

from typing import Any, Dict, List
from uuid import UUID

from core.tools.dto import AggregatedWaveResult, ToolExecutionResult


class WaveResultAggregator:
    """Aggregator merging stdout/stderr, durations, and output artifacts of WaveTasks."""

    def aggregate_results(
        self, wave_id: UUID, results: Dict[UUID, ToolExecutionResult]
    ) -> AggregatedWaveResult:
        """Combine all individual task outcomes in a wave into a unified DTO.

        Args:
            wave_id: Target wave identifier.
            results: Dictionary mapping task_id to ToolExecutionResult.

        Returns:
            Consolidated AggregatedWaveResult DTO.
        """
        if not results:
            return AggregatedWaveResult(
                wave_id=wave_id,
                status="SUCCESS",
                tasks_completed=[],
                tasks_failed=[],
                combined_stdout="",
                combined_stderr="",
                total_duration=0.0,
                artifacts={},
            )

        tasks_completed: List[UUID] = []
        tasks_failed: List[UUID] = []
        combined_stdouts: List[str] = []
        combined_stderrs: List[str] = []
        total_duration = 0.0
        combined_artifacts: Dict[str, Any] = {}

        for task_id, res in results.items():
            total_duration += res.duration

            # Merge artifacts
            if res.artifacts:
                for k, v in res.artifacts.items():
                    # Prefix artifact key with task_id to prevent collision
                    combined_artifacts[f"{task_id}_{k}"] = v

            # Append outputs
            if res.stdout:
                combined_stdouts.append(f"--- Task {task_id} Output ---\n{res.stdout}")
            if res.stderr:
                combined_stderrs.append(f"--- Task {task_id} Error ---\n{res.stderr}")

            # Segregate success vs failure/error
            if res.status == "SUCCESS":
                tasks_completed.append(task_id)
            else:
                tasks_failed.append(task_id)

        # Determine status
        if len(tasks_failed) == 0:
            final_status = "SUCCESS"
        elif len(tasks_completed) == 0:
            final_status = "FAILURE"
        else:
            final_status = "PARTIAL_FAILURE"

        return AggregatedWaveResult(
            wave_id=wave_id,
            status=final_status,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            combined_stdout="\n\n".join(combined_stdouts),
            combined_stderr="\n\n".join(combined_stderrs),
            total_duration=total_duration,
            artifacts=combined_artifacts,
        )
