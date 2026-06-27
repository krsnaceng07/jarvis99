# 27_PERMISSION_SYSTEM.md

## Purpose
This document defines the Permission System of JARVIS OS. It details the permission levels, authorization checkpoints, human confirmation interfaces, and execution block rules.

## Scope
Applies to all tool calls, workspace file edits, browser script executions, and OS system automation processes.

## Permission Levels & Human Approval Protocol
JARVIS OS operates under a strict four-tier permission model to ensure safety during autonomous operation:

| Level | Name | Description | Human Approval Required? |
| --- | --- | --- | --- |
| **L0** | Read-Only | Reading workspace files, querying databases, checking logs. | **Never** (Fully autonomous) |
| **L1** | Safe Write | Writing code files, compiling tests inside Docker, caching memory. | **Never** (Fully autonomous) |
| **L2** | High-Risk Write | Modifying production database schemas, writing configurations outside sandbox. | **Condition-Based** (Requires human approval unless run in Dev-Staging) |
| **L3** | Destructive / Execution | spawner CLI commands on host, browser payment execution, system file deletion. | **Always** (Requires explicit human approval click/override) |

### Human Confirmation Interface Standard
When an execution requests an L3 or gated L2 action, the system must trigger the confirmation protocol:
1. **Pause active queues:** Pause execution waves and hold agent states in `Awaiting Approval` mode.
2. **Present detailed prompt:** Display the target command, file diff, sandbox results, security risk score, and potential rollback path.
3. **Wait for input:** Block execution until a manual human click (Approve/Reject) or typed confirmation command is received.

## Responsibilities
- **Permission Gatekeeper Daemon:** Inspects requested action levels, validates credentials, and manages the dashboard prompt loops.
- **Human Owner:** Audits the execution details and issues Approve or Reject decisions.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4 and Rule 13).

## Interfaces
- Input: API requests containing task target contexts.
- UI: Interactive dashboard popups and CLI prompt options (`[y/N]`).

## Examples
- **Correct Gate Action:** Developer agent attempts to delete a file. Gatekeeper maps the action as L3, pauses queue, shows file deletion diff to user, and awaits confirmation.
- **Incorrect Gate Action:** Developer agent deletes a user database table silently because a debug flag was enabled. (Violates L2/L3 approval rules).

## Failure Cases
- **UI Prompt Hang:** The human user is offline, leaving the queue suspended indefinitely. *Mitigation:* The Permission Gatekeeper implements a configurable timeout (default: 30 minutes). If no input is received, the task is marked as REJECTED/TIMEOUT, and the system rolls back to the last stable git commit.

## Security Considerations
- High-level permission configurations are hardcoded inside the database schema and cannot be altered by agent-generated scripts.

## Future Extension
- Modifying level mappings or timeout thresholds must be documented in ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [26_SECURITY_CONSTITUTION.md](file:///e:/jarvis/docs/26_SECURITY_CONSTITUTION.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
