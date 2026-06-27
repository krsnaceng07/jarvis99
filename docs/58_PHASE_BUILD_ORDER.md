# 58_PHASE_BUILD_ORDER.md

## Purpose
This document defines the Phase Build Order for JARVIS OS. It establishes the strict sequencing, dependency flow, and vertical slice guidelines for all development tasks.

## Scope
Applies to all code, task, and project schedules inside the repository.

## Phase Build Order Sequence
To prevent circular dependencies and design blocks, modules must be built in this strict sequencing pattern:

```
[Phase 0: Master Foundation (frozen)]
        ↓
[Phase 1: Config, Secrets, Loggers, Exceptions]
        ↓
[Phase 2: Database Pools, Redis, PgVector Schemas]
        ↓
[Phase 3: Docker Sandbox Engine, Tool Exec API]
        ↓
[Phase 4: Electron Web Dashboard Gateway]
        ↓
[Phase 5: Playwright CDP custom browser client]
        ↓
[Phase 6: PyAutoGUI coordinate controllers]
        ↓
[Phase 7: Multi-Agent event routing streams]
        ↓
[Phase 8: Scrapers, Summarizers, Graph indexers]
        ↓
[Phase 9: Key encryption, Security audits signatures]
        ↓
[Phase 10: Staging Compose builds]
```

### Build Sequencing Policies
1. **Foundation First:** Core exceptions, config loaders, and database pools must be completed and tested before any agent logic is written.
2. **Sandbox before Execution:** Docker container sandboxes must be fully functional before PC control or browser code is executed on the system.
3. **No Skip Rule:** Developers cannot begin work on later phases until all tasks in the current phase pass the Quality Gates.

## Responsibilities
- **Planner Agent:** Enforces these build sequence bounds during task creation.
- **Reviewer Agent:** Blocks PR merges that attempt to introduce code from later phases prematurely.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 2, Rule 5, and Rule 8).

## Interfaces
- Input: Active phase task lists.
- Output: Build logs.

## Examples
- **Correct Build Order:** Writing the Pydantic Settings loaders in Phase 1, database schemas in Phase 2, and vector search functions in Phase 3.
- **Incorrect Build Order:** Implementing the Knowledge Graph scraping engine before the database connection pool is functional. (Violates Foundation First rule).

## Failure Cases
- **Circular Imports across Phases:** An agent imports a Phase 3 database module into a Phase 1 exceptions class. *Mitigation:* The Quality Gates check import hierarchies and raise compilation errors if import paths point to unbuilt phases.

## Security Considerations
- Sandboxing policies (Phase 3) must be frozen and audited before PC GUI automation controllers (Phase 6) are active.

## Future Extension
- Changes to the build sequence require ADR updates and user approval.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [42_BUILD_ORDER.md](file:///e:/jarvis/docs/42_BUILD_ORDER.md)
- [57_IMPLEMENTATION_ROADMAP.md](file:///e:/jarvis/docs/57_IMPLEMENTATION_ROADMAP.md)
- [69_SYSTEM_DEPENDENCY_GRAPH.md](file:///e:/jarvis/docs/69_SYSTEM_DEPENDENCY_GRAPH.md)
