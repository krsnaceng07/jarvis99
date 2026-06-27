# 28_SANDBOX_POLICY.md

## Purpose
This document defines the Sandbox Policy of JARVIS OS. It details how Docker containers are configured, structured, and monitored to isolate dynamic skill executions, code compilations, and browser automation tasks.

## Scope
Applies to all Docker container profiles, task execution environments, and volume mounts.

## Sandbox Configuration Standards
1. **Docker Isolation Model:** Every execution thread that processes untrusted code, executes user scripts, or compiles dynamic skills must run inside a dedicated, isolated Docker container.
2. **Container Constraints & Resource Quotas:**
   - **RAM Allocation:** Maximum of 512MB RAM per container.
   - **CPU Core Limits:** Maximum of 0.5 CPU shares.
   - **Storage Disk Quotas:** Maximum of 1GB temporary disk space.
   - **Process Limits (PID Limit):** Maximum of 30 active processes inside the container to prevent fork-bomb crashes.
3. **Network Isolation Policies:**
   - Default state: Network interfaces are disabled (`--network none`) for raw code execution.
   - For browser automation and API scrapers, outbound traffic is limited to HTTP/HTTPS ports (80, 443) via a secure local proxy. All local subnet traffic (e.g. accessing host-side databases directly) is blocked.
4. **FileSystem Mount Rules:**
   - Host volumes mounted inside containers must be **read-only** by default.
   - Dynamic code modifications must occur inside transient directories that are destroyed immediately when the container exits.

## Responsibilities
- **Resource Manager:** Launches, configures, and cleans up Docker container tasks.
- **Security Agent:** Audits container config arguments to check that privilege escalation parameters (e.g. `--privileged`) are never enabled.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Docker Socket Interface: `/var/run/docker.sock` accessed via Docker Python SDK.

## Examples
- **Correct Sandbox Execution:** Agent compiles a new skill. The file is copied to a temp directory, mounted as read-write to a sandbox container, compiled, tested, and retrieved. The container is destroyed.
- **Incorrect Sandbox Execution:** Agent directly executes code on the host using Python `subprocess.run()` without Docker container wrappers. (Violates Core Isolation rules).

## Failure Cases
- **Container Escape Attempt:** Executing code attempts to exploit Docker vulnerabilities to gain host root access. *Mitigation:* Docker containers run under low-privilege User IDs (UIDs). System tools enforce kernel security layers (e.g. AppArmor or seccomp profiles) to block unauthorized syscalls.

## Security Considerations
- The Docker socket file `/var/run/docker.sock` must never be mounted inside a sandbox container, as this allows containers to spawn host-level processes.

## Future Extension
- Upgrades to microVM architectures (e.g. Firecracker) require new ADR logs and full integration testing.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [04_TECHNICAL_REQUIREMENTS.md](file:///e:/jarvis/docs/04_TECHNICAL_REQUIREMENTS.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [26_SECURITY_CONSTITUTION.md](file:///e:/jarvis/docs/26_SECURITY_CONSTITUTION.md)
- [64_RESOURCE_MANAGER.md](file:///e:/jarvis/docs/64_RESOURCE_MANAGER.md)
