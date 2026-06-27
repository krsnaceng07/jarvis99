# 32_NAMING_STANDARD.md

## Purpose
This document defines the Naming Standard for JARVIS OS. It establishes naming conventions for files, variables, functions, database tables, and API endpoints to ensure system consistency.

## Scope
Applies to all code repositories, database DDLs, and OpenAPI schemas inside the JARVIS OS workspace.

## Naming Conventions & Standards

### 1. Source Code Files & Directories
- **Python:** Snake case (e.g. `postgres_client.py`).
- **React / TypeScript:** Pascal case for components (e.g. `BrowserViewport.tsx`), camel case for hooks and helpers (e.g. `useAuth.ts`).
- **Directories:** Snake case (e.g. `core/memory/`).

### 2. Variables, Functions, & Classes
- **Variables & Functions:** Snake case in Python (e.g. `get_session_id`), camel case in JavaScript (e.g. `getSessionId`).
- **Classes:** Pascal case in all environments (e.g. `MemoryManager`, `BrowserAdapter`).
- **Constants:** Upper snake case (e.g. `MAX_SUBAGENTS_LIMIT`).

### 3. Database Schemas
- **Tables & Columns:** Snake case, lowercase, plural nouns for tables (e.g. `users`, `active_tasks`).
- **Foreign Keys:** Target table singular + `_id` (e.g. `user_id`).

### 4. API Endpoints
- **REST Paths:** Lowercase, hyphenated (kebab-case), plural resources (e.g. `/api/v1/agent-sessions`).

## Responsibilities
- **Developer Agent:** Applies these naming conventions during code creation.
- **Reviewer Agent:** Rejects pull requests containing non-compliant variable, file, or table names.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 7 and Rule 11).

## Interfaces
- Local lint checks (e.g. Flake8, ESLint) initialized to block non-compliant naming patterns.

## Examples
- **Correct Naming:** Function `def store_embedding()`, table `memory_nodes`, route `/api/v1/tools/execute`.
- **Incorrect Naming:** Function `def StoreEmbedding()`, table `MemoryNodesTable`, route `/api/v1/toolExecute`. (Violates Python, DB, and API Naming rules).

## Failure Cases
- **Name Collisions:** An agent creates a duplicate class helper with a slightly different case structure (e.g. `Memorymanager`). *Mitigation:* Linter configurations enforce case-sensitive checks and block compilation if collisions are possible.

## Security Considerations
- API endpoint naming must not expose database column structure directly to prevent attackers from mapping injection targets.

## Future Extension
- Modifying naming guidelines requires updating this document via approved reviews.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [26_NAMING_STANDARD.md](file:///e:/jarvis/docs/26_NAMING_STANDARD.md)
- [33_CODE_STANDARD.md](file:///e:/jarvis/docs/33_CODE_STANDARD.md)
