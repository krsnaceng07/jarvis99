# 64_RESOURCE_MANAGER.md

## Purpose
This document defines the Resource Manager specifications for JARVIS OS. It establishes runtime constraints for CPU usage, memory boundaries, disk allocations, and active process bounds across all subagent containers.

## Scope
Applies to the Docker Sandbox wrapper, container monitoring scripts, and supervisor processes.

## Sandbox Resource Limits & Allocation Policy
All dynamically spawned containers and subagents must operate under strict, hardcoded limits:

| Resource | Sandbox Limit | Host Alert Threshold | Action on Violation |
| --- | --- | --- | --- |
| **RAM** | 512 MB | 450 MB | Kill container & raise OOM error |
| **CPU** | 0.5 shares | 80% utilization | Throttle container execution |
| **Disk** | 1 GB | 900 MB | Halt writes & raise DiskQuota error |
| **Processes** | 30 active PIDs | 25 PIDs | Block new thread spawns |
| **Timeout** | 15 minutes | 14 minutes | Terminate container |

### Out-of-Memory (OOM) Handling Policy
- If a sandbox container consumes more than 512MB RAM, the Docker engine triggers a SIGKILL. The Resource Manager catches the container exit code, logs an `OOMKilled` event, marks the task state as FAILED, and triggers self-healing.

## Responsibilities
- **Resource Manager Service:** Launches containers with CPU/RAM parameters, monitors metrics, and terminates loops.
- **System Supervisor:** Monitors host-side resources (CPU/RAM) to prevent system hangs.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4 and Rule 14).

## Interfaces
- Docker Engine SDK: Container configuration limits (`mem_limit="512m"`, `nano_cpus=500000000`).

## Examples
- **Correct Resource Management:** Developer agent attempts to compile a library -> script compiles inside container matching the CPU/RAM limits -> exits cleanly.
- **Incorrect Resource Management:** A subagent is spawned without memory or CPU bounds, consuming all available host cores and freezing the OS. (Violates core sandboxing rules).

## Failure Cases
- ** runaway process loop:** A script spawns a thread fork-bomb, hanging the container. *Mitigation:* The PID limit (max 30) prevents fork-bomb execution from exhausting host resources.

## Security Considerations
- Resource Manager policies prevent malicious scripts from launching Denial-of-Service attacks against host infrastructure.

## Future Extension
- Transitioning to VM configurations (e.g. Firecracker limits) is managed under ADR logs.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [14_SUBAGENT_ORCHESTRATION.md](file:///e:/jarvis/docs/14_SUBAGENT_ORCHESTRATION.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
- [65_COST_GOVERNOR.md](file:///e:/jarvis/docs/65_COST_GOVERNOR.md)
