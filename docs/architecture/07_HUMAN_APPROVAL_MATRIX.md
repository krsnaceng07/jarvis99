# 07_HUMAN_APPROVAL_MATRIX.md

## Purpose
This document freeze-locks the Human Approval Matrix for JARVIS OS. It establishes the action safety levels, permission tiers, and manual override constraints.

## Scope
Applies to all tool calls, workspace file modifications, outbound API connections, and OS terminal commands.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## Human Approval Lookup Matrix (Frozen)

| Level | Tool Category | Examples | Authorization Policy |
| --- | --- | --- | --- |
| **L0** | Read-Only | Reading files in workspace, listing directories, reading DB keys. | **Allowed** (Fully autonomous) |
| **L1** | Sandbox Write | Writing test code inside Docker, running compilers, caching memory. | **Allowed** (Fully autonomous) |
| **L2** | High-Risk Write | Modifying production database models, editing `.env` configs, web POST calls. | **Confirm-Based** (Requires human approval unless run in dev stage) |
| **L3** | Destructive / OS | Terminal shell execution on host, browser payment routing, deleting files. | **Always Confirm** (Requires explicit human approval override click) |
| **L4** | Prohibited | Deleting kernel system files, direct admin shell calls, disabling sandbox. | **Prohibited** (System blocks execution immediately) |

### Gated Approval Rules
1. **Interactive Prompt:** Level 3 and gated Level 2 actions must trigger a frontend dashboard popup or CLI prompt showing:
   - Tool name & calling agent correlation ID.
   - Command details or file diff content.
   - Associated risk parameters.
2. **Auto-Timeout Fail:** If the user does not respond within 30 minutes, the task is marked as REJECTED, and the system rolls back (see `48_FAILSAFE_AND_ROLLBACK.md`).

## Responsibilities
- **Permission Gatekeeper:** Intercepts tool payloads, maps safety levels, manages prompt logs, and halts execution loops.
- **Human User:** Audits risk metrics and issues Approve/Reject commands.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4 and Rule 13).

## Interfaces
- REST Gateway: `/api/v1/permissions/approve`.
- UI: Dashboard popup prompts.

## Examples
- **Correct Execution:** Agent attempts to run a Python package installer on the host -> system identifies L3, halts, prompts user, and waits for a manual click.
- **Incorrect Execution:** Agent runs database migration scripts silently during production execution without approval check. (Violates Level 2 and Level 3 rules).

## Failure Cases
- **Prompt Swarm:** Agent requests 10 approvals in 10 seconds. *Mitigation:* The gatekeeper blocks consecutive L2/L3 requests and merges them into a single wave list requiring one bulk approval.

## Security Considerations
- Security logs preserve a signed audit record of every human approval event to prevent post-incident logging manipulation.

## Future Extension
- Level mapping modifications must be approved via ADR revisions.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [27_PERMISSION_SYSTEM.md](file:///e:/jarvis/docs/27_PERMISSION_SYSTEM.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
