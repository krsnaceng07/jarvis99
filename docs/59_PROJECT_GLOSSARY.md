# 59_PROJECT_GLOSSARY.md

## Purpose
This document defines the Project Glossary for JARVIS OS. It establishes the standard definitions, terminology, and abbreviations used across all design specs, API routes, and code comments.

## Scope
Applies to all documentation, codebase comments, variable names, and database schemas.

## Project Glossary & Definitions
- **Agent:** An autonomous LLM-driven execution thread running under a specific system instruction profile (e.g. Planner, Developer).
- **Subagent:** A transient child agent spawned by a parent agent to complete a specific subtask within a restricted container sandbox.
- **Skill:** A dynamically compiled, signed, and registered code plugin (Python/JS) that extends the capabilities of system agents.
- **Tool:** A built-in, static execution driver (e.g. `file_write`, `http_request`) exposed to agents via the Tool Layer.
- **Working Memory:** Fast-decaying cache stored in Redis containing active task variables and short conversation contexts.
- **Session Memory:** Relational database entries in PostgreSQL tracking active agent sessions and task trees.
- **Long-Term Memory:** Summarized semantic memory nodes and embeddings stored in Postgres and PgVector.
- **Knowledge Graph:** A relational triplestore database of entities and connections representing absorbed user knowledge.
- **Reflection:** An automated verification step where an agent evaluates its own output against requirements before completing a task.
- **Sandbox:** An isolated Docker container with strict CPU, RAM, and network quotas where dynamic code is executed.
- **Failsafe:** Automated recovery states (Safe, Recovery, Emergency) triggered during critical system failures.
- **Audit Log:** Cryptographically signed, read-only transaction log records of all system calls and tool executions.

## Responsibilities
- **Developer Agent:** Uses these terms consistently in file names, comments, and variable definitions.
- **Documentation Agent:** Resolves glossary conflicts and updates entries.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Conceptual definitions dictionary.

## Examples
- **Correct Usage:** Referring to a dynamically loaded plugin as a "Skill" and a built-in function as a "Tool" in API endpoints.
- **Incorrect Usage:** Mixing terms randomly, e.g. calling a static helper function a "dynamic subagent skill" inside logs. (Creates semantic confusion).

## Failure Cases
- **Terminology Drift:** Developers or agents invent new terms for existing concepts, creating database schema confusion. *Mitigation:* The reviewer agent checks that database table names and API routes map strictly to glossary terms.

## Security Considerations
- Shared definitions prevent misunderstanding of security rules (e.g. distinguishing a sandboxed "Skill" from a host-level "Tool").

## Future Extension
- Adding new terms to the glossary requires updating this document via approved reviews.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [50_PROJECT_GLOSSARY.md](file:///e:/jarvis/docs/50_PROJECT_GLOSSARY.md)
