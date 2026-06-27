# 72_RECOVERY_MODE.md

## Purpose
This document defines the Recovery Mode specifications for JARVIS OS. It establishes the restore protocols, backup locations, automated Git rollback commands, database imports, and system verification checks.

## Scope
Applies to the System Supervisor, recovery manager scripts, database backup tools, and the Debugger Agent.

## Recovery Mode Workflow
When the system supervisor triggers Recovery Mode (due to boot validation failures, cascading loops, or database index corruption), the recovery process must execute:

```
Trigger Recovery Mode
        ↓
Stage 1: Load last verified configuration profile (Safe settings)
        ↓
Stage 2: Stop active task queues & lock API gateway
        ↓
Stage 3: Restore source files to last stable Git tag (git reset --hard)
        ↓
Stage 4: Drop corrupted database tables
        ↓
Stage 5: Import last daily PostgreSQL dump (pg_restore)
        ↓
Stage 6: Clear and rebuild Redis session and working memory cache
        ↓
Stage 7: Execute the system Boot validation test suite
    ├─ [TESTS FAIL] → Lock System in Emergency Stop & alert human admin
    └─ [TESTS PASS] → Reboot FastAPI gateway in Safe Mode
```

### Restore Policies
1. **Backup Verification:** Database backup files must be verified as uncorrupted before import. The system validates the backup file size and checksum.
2. **Git Rollover Checkpoint:** Git rollback actions must point to official release tags (e.g. `v1.2.0`) rather than arbitrary development commits.

## Responsibilities
- **System Supervisor:** Triggers Recovery Mode and executes the restoration commands.
- **Human Administrator:** Manages backup storage keys and resolves Emergency Stop blocks.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 3, Rule 4, and Rule 5).

## Interfaces
- Shell APIs: `git reset --hard` and `pg_restore -d [DB_NAME] [BACKUP_PATH]`.

## Examples
- **Correct Recovery:** A bad migration script breaks database tables. Supervisor triggers Recovery Mode, restores DB to yesterday's snapshot, resets git to tag `v1.0.1`, runs tests, and boots.
- **Incorrect Recovery:** Running manual SQL delete scripts on live databases to patch errors without taking backups or resetting code. (Violates restore loop and safety rules).

## Failure Cases
- **No Valid Backup File:** The daily backup dump is empty or corrupted. *Mitigation:* The system writes daily backups to two isolated locations (local disk and an offline cloud vault). If the local file is invalid, it attempts retrieval from the cloud location.

## Security Considerations
- Restoring databases requires decryption keys. Decryption must occur in memory using variables fetched securely from the vault.

## Future Extension
- Transitioning to automated hot-standby replication failovers is managed under database standards.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [35_DATABASE_STANDARD.md](file:///e:/jarvis/docs/35_DATABASE_STANDARD.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
- [70_BOOT_SEQUENCE.md](file:///e:/jarvis/docs/70_BOOT_SEQUENCE.md)
