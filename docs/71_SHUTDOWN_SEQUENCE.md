# 71_SHUTDOWN_SEQUENCE.md

## Purpose
This document defines the Shutdown Sequence for JARVIS OS. It establishes the process termination order, active task cancellation rules, database session synchronization, browser closures, log flushing, and backups to prevent state corruption.

## Scope
Applies to the FastAPI server lifecycle hooks, active supervisor daemons, and system container managers.

## Shutdown Sequence Stages
When a shutdown signal (SIGTERM, SIGINT, or CLI halt) is received, the supervisor must execute the following sequence:

```
[Shutdown Signal Received]
        ↓
Stage 1: Pause goal queues & block incoming REST/WebSocket requests
        ↓
Stage 2: Cancel active subagent tasks & send cancel signal to Docker
        ↓
Stage 3: Close active Jarvis Browser instances and Playwright sessions
        ↓
Stage 4: Flush working memory (Redis) variables to PostgreSQL
        ↓
Stage 5: Commit outstanding database transactions & close Postgres pool
        ↓
Stage 6: Flush logging buffers to log files
        ↓
Stage 7: Execute daily backup compilation (save DB schema and logs)
        ↓
Stage 8: Destroy temporary Docker container sandboxes
        ↓
Stage 9: Release secrets variables from memory
        ↓
Stage 10: Halt API server & exit supervisor process
        ↓
[System State: OFFLINE]
```

### Shutdown Policies
1. **Graceful Timeout:** The system is allocated a **30-second window** to complete Stage 1 through Stage 9. If the graceful shutdown hangs, the supervisor forces process termination (SIGKILL) to prevent server hangs.
2. **Database Clean Shutdown:** Database pools must never be closed while active transactions are running. Transactions must be aborted or completed.

## Responsibilities
- **System Supervisor:** Intercepts system signals, coordinates shutdown stages, and manages timeouts.
- **Database pool manager:** Safely closes connections.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Input: POSIX signals (SIGTERM, SIGINT) and REST API `/api/v1/system/shutdown`.
- Output: Shutdown logs printed to console and written to file.

## Examples
- **Correct Shutdown:** Administrator hits Ctrl+C -> supervisor pauses queue -> docker containers destroy -> postgres closes -> server exits cleanly in 4 seconds.
- **Incorrect Shutdown:** Instantly pulling the power plug or killing the database container while active writes are running, leading to database index corruption. (Violates clean shutdown rules).

## Failure Cases
- **Hung Container Shutdown:** A docker container hangs during Stage 2 and ignores the SIGTERM signal. *Mitigation:* The supervisor sends a SIGKILL command directly to the Docker engine if the container does not exit within 5 seconds.

## Security Considerations
- Memory keys and decrypted credentials must be wiped from active RAM variables before Stage 10 terminates.

## Future Extension
- Enhancing process shutdown hooks to support dynamic cluster terminations is managed via ADR logs.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [35_DATABASE_STANDARD.md](file:///e:/jarvis/docs/35_DATABASE_STANDARD.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
- [70_BOOT_SEQUENCE.md](file:///e:/jarvis/docs/70_BOOT_SEQUENCE.md)
