"""
PHASE: 27
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/89_PHASE_27_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Prometheus metrics formatting helper.

Architect constraints incorporated:
- C5: Returns Prometheus text exposition format directly.
"""

from __future__ import annotations

from typing import Any, Dict


class PrometheusMetricsFormatter:
    """Formats raw system and application metrics into Prometheus text exposition format."""

    @staticmethod
    def format_metrics(metrics: Dict[str, Any]) -> str:
        """Format metrics dictionary to Prometheus exposition format string.

        Each metric can have a name, type, help text, and value.
        """
        lines = []
        for name, data in metrics.items():
            val = data.get("value", 0)
            mtype = data.get("type", "gauge")
            mhelp = data.get("help", "")

            if mhelp:
                lines.append(f"# HELP {name} {mhelp}")
            lines.append(f"# TYPE {name} {mtype}")

            # Format value: boolean as 1 or 0, float/int as standard numbers
            if isinstance(val, bool):
                val_str = "1" if val else "0"
            elif isinstance(val, (int, float)):
                val_str = str(val)
            else:
                val_str = "0"

            lines.append(f"{name} {val_str}")

        # Prometheus format requires a trailing newline
        return "\n".join(lines) + "\n"
