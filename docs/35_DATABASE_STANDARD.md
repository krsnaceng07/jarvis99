# 35_DATABASE_STANDARD.md

## Purpose
This document defines the Database Standard for JARVIS OS. It establishes DDL policies, indexing strategies, primary key requirements, and schema migration rules for relational and vector databases.

## Scope
Applies to all SQL schemas, database migration files (Alembic), query builders, and database models.

## Database Standards & DDL Policies
1. **Unified Migration Standard:** Schema changes must never be applied manually to the production database. All modifications must use **Alembic migration scripts** checked into the repository under `/alembic/versions/`.
2. **Primary Key Standard:** Every database table must use a **UUIDv4** primary key named `id` to ensure unique mapping across distributed agents and systems.
3. **Strict Indexing Policy:**
   - Every foreign key constraint must have a matching index to prevent slow sequential scans.
   - Vector search columns in `pgvector` must be indexed using HNSW (Hierarchical Navigable Small World) with cosine distance parameters.
4. **Data Constraint Rules:** Every table must enforce strict column types, not-null constraints where applicable, and foreign key cascades to ensure data integrity.

## Responsibilities
- **Database Administrator:** Reviews migration scripts, monitors query execution times, and optimizes index configurations.
- **Developer Agent:** Creates Alembic scripts when database models are modified.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4, Rule 5, and Rule 13).

## Interfaces
- Local SQL Client: `jarvis.core.database.session`.
- Migration Tool: Alembic.

## Examples
- **Correct DDL Script:** An Alembic migration file `3a8f_add_agent_status.py` adding a column to `agent_sessions` and indexing it.
- **Incorrect DDL Script:** Executing `ALTER TABLE agent_sessions ADD COLUMN status VARCHAR` directly inside a developer shell. (Violates Unified Migration rule).

## Failure Cases
- **Migration Drift:** The production database schema differs from the Alembic migration history. *Mitigation:* The boot sequence validates schema version status and halts execution if the database requires outstanding migrations (see `70_BOOT_SEQUENCE.md`).

## Security Considerations
- Database users must operate under low-privilege roles. The core application profile must not have table drop or database creation privileges.

## Future Extension
- Database engine migrations must be documented inside ADR records and approved by the user.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [12_MEMORY_ARCHITECTURE.md](file:///e:/jarvis/docs/12_MEMORY_ARCHITECTURE.md)
- [30_DATABASE_STANDARD.md](file:///e:/jarvis/docs/30_DATABASE_STANDARD.md)
- [70_BOOT_SEQUENCE.md](file:///e:/jarvis/docs/70_BOOT_SEQUENCE.md)
