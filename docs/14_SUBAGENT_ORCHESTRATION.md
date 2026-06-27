# 14_SUBAGENT_ORCHESTRATION.md

## Purpose
This document defines the Subagent Orchestration policy for JARVIS OS. It details the rules for spawning, monitoring, sandboxing, and terminating child agents during complex task execution.

## Scope
Applies to the Swarm Orchestrator, Planner Agent spawning loops, and docker isolation controllers.

## Spawning & Lifecycles Policies
1. **Instantiation Rule:** Subagents must only be spawned when a parent task is decomposed and explicitly requires parallel execution (e.g. separate front-end and back-end tasks).
2. **Lifecycle States:** Subagents transition strictly through: `Spawning` → `Running` → `Verifying` → `Completed` → `Terminated`.
3. **Resource & Spawning Limits:**
   - Maximum active concurrent subagents allowed: **5** (to prevent resource exhaustion).
   - Maximum execution lifespan per subagent: **15 minutes** (to prevent runaway loops).
   - CPU/RAM limits: Each subagent container is capped at 0.5 CPU and 512MB RAM.

## Responsibilities
- **Swarm Orchestrator:** Instantiates containers, configures environments, monitors heartbeat signals, and destroys containers when finished.
- **Resource Manager:** Allocates execution limits and monitors container metrics (see `64_RESOURCE_MANAGER.md`).

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Docker API: Spawns container instances using the official Python Docker SDK.
- Telemetry API: Subagents write logs to Redis streams which are broadcast to the main dashboard.

## Examples
- **Correct Execution:** PM agent spawns Developer subagent inside a container to write tests. The subagent finishes in 3 minutes, saves results, and the PM agent terminates the container.
- **Incorrect Execution:** PM agent spawns 50 Developer agents on the host hardware without Docker container wrappers. (Violates both Sandboxing and Spawning Limit rules).

## Failure Cases
- **Runaway Agent Loop:** A subagent encounters an infinite loop and runs indefinitely. *Mitigation:* The orchestrator triggers an automatic timeout termination when execution reaches 15 minutes, marks the subagent state as FAILED, and alerts the Planner.

## Security Considerations
- Subagent containers must run with read-only root filesystems and have no raw write access to the parent workspace, except for a designated transient directories.

## Future Extension
- Modifying resource limits or execution timeouts requires updating this document via ADR approval.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [08_AI_AGENT_CONSTITUTION.md](file:///e:/jarvis/docs/08_AI_AGENT_CONSTITUTION.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
- [64_RESOURCE_MANAGER.md](file:///e:/jarvis/docs/64_RESOURCE_MANAGER.md)
