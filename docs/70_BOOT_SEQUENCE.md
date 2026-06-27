# 70_BOOT_SEQUENCE.md

## Purpose
This document defines the Boot Sequence for JARVIS OS. It establishes the strict startup stages, component verification checks, secrets decryption, and database connection loops required to initialize the system.

## Scope
Applies to the FastAPI server boot manager, supervisor daemons, and system CLI startup hooks.

## Boot Sequence Stages
The system must initialize sequentially, verifying each stage before starting the next:

```
[Start CLI / Shell Trigger]
        ↓
Stage 1: Verify Python & Node Environments
        ↓
Stage 2: Load & Validate Pydantic Configurations (.env / config.yaml)
        ↓
Stage 3: Fetch & Decrypt Master Key from Vault (Secrets Vault check)
        ↓
Stage 4: Connect Database Pool (PostgreSQL & pgvector check)
        ↓
Stage 5: Verify Schema Version (Alembic Status Check)
        ↓
Stage 6: Connect Session Cache (Redis PubSub stream check)
        ↓
Stage 7: Initialize Model Router & verify API connections
        ↓
Stage 8: Start Sandbox Engine (Docker Daemon status check)
        ↓
Stage 9: Load & Verify Registered Skills & Tools Signatures
        ↓
Stage 10: Start API Gateway & WebSockets server
        ↓
[System State: READY]
```

### Boot Validation Policy
1. **Critical Failure halts:** If any check in Stage 1 through Stage 9 fails, the boot sequence halts immediately. The supervisor writes a FATAL log entry and halts the server.
2. **Schema Verification:** In Stage 5, if the database schema version does not match the repository Alembic version, the system blocks boot and requests migration.

## Responsibilities
- **System Supervisor:** Manages boot execution, triggers stage validation tasks, and logs startup telemetry.
- **Human Administrator:** Starts the CLI launcher, and inputs vault password.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 2 and Rule 13).

## Interfaces
- Input: Startup flags from CLI parameters.
- Output: Standard output logs and Redis stream entries (`system.boot.status`).

## Examples
- **Correct Startup:** Supervisor executes checks -> Docker daemon is active -> vaults decrypt -> database connects in 40ms -> FastAPI server boots cleanly.
- **Incorrect Startup:** Starting the API server and accepting user tasks when the database pool is offline or when the Docker daemon is inactive. (Violates Stage validation rules).

## Failure Cases
- **Docker Daemon Offline:** Stage 8 fails because Docker is not running on the host. *Mitigation:* The boot manager catches the connection failure, logs a warning requesting the user start Docker, halts the boot sequence, and exits with code 1.

## Security Considerations
- The decryption key for the vault must only exist in memory and must never be written to temporary cache files or console outputs.

## Future Extension
- Modifications to boot stages require ADR updates.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [04_TECHNICAL_REQUIREMENTS.md](file:///e:/jarvis/docs/04_TECHNICAL_REQUIREMENTS.md)
- [29_SECRET_MANAGEMENT.md](file:///e:/jarvis/docs/29_SECRET_MANAGEMENT.md)
- [30_CONFIGURATION_STANDARD.md](file:///e:/jarvis/docs/30_CONFIGURATION_STANDARD.md)
- [35_DATABASE_STANDARD.md](file:///e:/jarvis/docs/35_DATABASE_STANDARD.md)
- [71_SHUTDOWN_SEQUENCE.md](file:///e:/jarvis/docs/71_SHUTDOWN_SEQUENCE.md)
