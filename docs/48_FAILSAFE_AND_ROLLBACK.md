# 48_FAILSAFE_AND_ROLLBACK.md

## Purpose
This document defines the Failsafe and Rollback Policy for JARVIS OS. It establishes target recovery states, automated Git rollback commands, database transaction rollbacks, and human override checkpoints.

## Scope
Applies to the System Supervisor, Debugger Agent, and active deployment managers.

## Recovery States & Rollback Policies
The system operates under four security and availability states:

```
[Normal Mode] ──(Crash/Exception)──> [Safe Mode] ──(Loop/Memory Leak)──> [Recovery Mode]
       ▲                                                                       │ (Fatal Failure)
       └──────(Apply Rollback / Hot-Patch & Verify)────────────────────────── [Emergency Stop]
```

### 1. Normal Mode
- Fully autonomous operation. Active queues are running, and skills are executing inside standard Docker sandboxes.

### 2. Safe Mode
- Activated when a single component crashes (see `23_SELF_HEALING_POLICY.md`). Sandbox operations continue, but outbound API calls are throttled, and the supervisor launches the Debugger Agent.

### 3. Recovery Mode
- Activated when multiple components fail or when a self-healing patch fails to resolve the issue. Outbound tool calls are disabled. The system rolls back the repository to the last stable Git tag (e.g. `v1.2.0`) and restores the database using the latest daily backup file.

### 4. Emergency Stop
- Activated when a security boundary escape is detected (e.g. dynamic code executing outside sandbox) or when LLM costs exceed daily budgets. The supervisor immediately kills all active Docker containers, flushes active Redis task queues, logs a fatal error, and shuts down the API server. **Requires manual human system administrator login to reboot.**

## Responsibilities
- **System Supervisor:** Monitors active daemon heartbeats and flags transition changes.
- **Human Admin:** Reviews Emergency Stop logs and manually reboots the system.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4, Rule 5, and Rule 13).

## Interfaces
- Local system command calls: `git reset --hard [LAST_STABLE_COMMIT]` and `pg_restore`.

## Examples
- **Correct Rollback Flow:** System fails to boot after a self-improvement code patch. Supervisor intercepts the failure, executes a hard git reset to the pre-patch commit, restores the Postgres database state, and successfully reboots the service.
- **Incorrect Rollback Flow:** System crashes and the supervisor continues booting, writing corrupted logs over database states. (Violates Recovery Mode rules).

## Failure Cases
- **Git Repository Corruption:** The local `.git` folder is corrupted, preventing automated resets. *Mitigation:* The system maintains a secondary read-only backup directory containing tarball packages of stable versions. If Git fails, the supervisor extracts the last stable tarball over the active workspace.

## Security Considerations
- Emergency Stop is the primary defensive safety net for the host system. It cannot be bypassed, overridden, or delayed by any active agent thread.

## Future Extension
- Modifications to recovery triggers or backup schedules are managed under the database and observability standards.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [23_SELF_HEALING_POLICY.md](file:///e:/jarvis/docs/23_SELF_HEALING_POLICY.md)
- [35_DATABASE_STANDARD.md](file:///e:/jarvis/docs/35_DATABASE_STANDARD.md)
- [72_RECOVERY_MODE.md](file:///e:/jarvis/docs/72_RECOVERY_MODE.md)
