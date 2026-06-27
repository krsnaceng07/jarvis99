# 18_TOOL_EXECUTION_POLICY.md

## Purpose
This document defines the Tool Execution Policy of JARVIS OS. It establishes the rules, formatting, logging hooks, and security checks that govern how agents call system tools and external APIs.

## Scope
Applies to all tool modules, custom skills, CLI executors, and scraper modules running inside the JARVIS OS execution engine.

## Tool Call Execution Framework
All system tool executions must follow a unified API loop and pass through a security validation gate before running:

```
Tool Call Request (JSON Payload)
        ↓
Audit & Parameter Scan (Security Agent)
        ↓
Permission Level check (Permission System)
        ↓
Needs Human Approval?
    ├─ [YES] → Pause Queue & Await User confirmation
    └─ [NO]  → Continue
        ↓
Instantiate Sandbox Environment (Docker)
        ↓
Execute Tool & Write Telemetry Log (Redis / Postgres)
        ↓
Clean Sandbox & Return Result Envelope
```

### Execution Policies
1. **Unregistered Tools Prohibited:** Agents can only execute tools that are registered in the active Database.
2. **Explicit Parameter Validation:** Raw shell strings or database commands must be parameterized. Dynamic string evaluation (e.g. Python `eval()` or SQL injections) is strictly forbidden.
3. **Structured Telemetry Logging:** Every execution must log the calling agent ID, execution start/end timestamps, CLI/HTTP payloads, output byte size, and resource usage metrics.

## Responsibilities
- **Security Agent:** Scans execution payloads and blocks unsafe system commands.
- **Tool Engine:** Manages execution routing and sandbox mounting.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Tool interface: REST Endpoint `/api/v1/tools/execute`.

## Examples
- **Correct Execution:** Agent requests `file_write` for a config file. Parameter scan validates destination path is inside sandbox scope, permission checks confirm authorization, and execution completes.
- **Incorrect Execution:** Agent requests `cmd_run` with argument `"rm -rf /"`. Parameter scan flags system destruction risk, and execution is blocked immediately. (Violates core security rules).

## Failure Cases
- **Sandbox Leak:** Tool execution process escapes sandbox limits. *Mitigation:* Sandbox network interfaces are strictly monitored. If an unexpected host-side process spawn is detected, the container engine kills the process group immediately.

## Security Considerations
- Tools must never execute with host-level root permissions. A designated low-privilege system user is required inside all containers.

## Future Extension
- Modifying security risk levels or adding new tool wrappers must be approved via ADR revisions.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [16_SKILL_SYSTEM.md](file:///e:/jarvis/docs/16_SKILL_SYSTEM.md)
- [27_PERMISSION_SYSTEM.md](file:///e:/jarvis/docs/27_PERMISSION_SYSTEM.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
