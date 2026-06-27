# 23_SELF_HEALING_POLICY.md

## Purpose
This document defines the Self-Healing Policy of JARVIS OS. It details how the system detects runtime crashes, analyzes stack traces, isolates bugs, generates temporary patches, and executes safe rollbacks to maintain system availability.

## Scope
Applies to the Debugger Agent, monitoring daemons, and supervisor state managers in the execution engine.

## Self-Healing Loop & Policy
When a system component, subagent, or active skill experiences a crash (runtime exception, segmentation fault, or API timeout), the system must launch the self-healing loop:

```
Runtime Exception / Crash Detected
        ↓
Supervisor intercepts state & captures Stack Trace
        ↓
Isolate Exception Context & Trace Logs (Debugger Agent)
        ↓
Run RCA (Root Cause Analysis)
        ↓
Generate Temporary Sandbox Patch
        ↓
Execute Target Test Suite
    ├─ [TESTS FAIL] → Log Error & Trigger Rollback
    └─ [TESTS PASS] → Apply Hot-Patch & Request Log Sync
        ↓
Perform Safety Check: Does crash persist?
    ├─ [YES] → Escalate to Safe Mode & Alert Human User
    └─ [NO]  → Queue Permanent Code Review Request
```

### Self-Healing Restrictions
1. **Max Attempt Limit:** The system is limited to a maximum of **3 self-healing patch attempts** for a single component within a 1-hour window. If the component crashes a 4th time, it is deactivated and escalated to human support.
2. **State Conservation:** If a patch fails validation, the system must restore the database transactions and file paths to their exact states prior to the crash.

## Responsibilities
- **Debugger Agent:** Scans crash dumps, runs RCA, and writes bug-fix code.
- **System Supervisor:** Intercepts runtime errors, isolates failing threads, and manages backup states.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 3, Rule 4, and Rule 12).

## Interfaces
- Input: Exception logs sent from the Logging Engine.
- Output: Healing patch scripts, log reports, and recovery status messages.

## Examples
- **Correct Healing:** Database query fails due to a missing table index. Debugger identifies index mismatch, creates index schema update, tests in sandbox, runs migration, and resolves error.
- **Incorrect Healing:** Core memory engine experiences a memory leak. Debugger repeatedly attempts to reboot the database pool without identifying the leaks, running in an infinite reboot loop. (Violates Max Attempt Limit).

## Failure Cases
- **Cascading Failure:** Healing a bug in Component A breaks dependent Component B. *Mitigation:* The system supervisor runs the full regression test suite (not just the local component test suite) before committing any hot-patch.

## Security Considerations
- Automated self-healing must never modify security configuration files, secrets encryption keys, or permission settings. These items are strictly read-only.

## Future Extension
- Modifications to supervisor rules or state restore frameworks are logged in ADR files.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [22_SELF_IMPROVEMENT_POLICY.md](file:///e:/jarvis/docs/22_SELF_IMPROVEMENT_POLICY.md)
- [38_ERROR_HANDLING_STANDARD.md](file:///e:/jarvis/docs/38_ERROR_HANDLING_STANDARD.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
