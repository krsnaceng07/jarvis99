# 00_PROJECT_CONSTITUTION.md

## Purpose
This document establishes the immutable, highest-priority rules governing all coding, modifying, and architectural steps for JARVIS OS. It serves as the legal and developmental anchor that no agent, subagent, or human developer may violate.

## Scope
Applies to all source code development, directory modifications, database schema designs, API contracts, deployment configurations, and documentation updates throughout the entire lifecycle of JARVIS OS.

## Core Rules (The 15 Pillars)
- **Rule 1:** Never generate code before understanding the entire project context and directory structure.
- **Rule 2:** Always execute the context loading sequence: **Project Constitution** → **System Architecture** → **Current Task** → **Dependencies** → **Existing Code** before making modifications.
- **Rule 3:** Never overwrite working production or test code unless explicitly requested or verified as part of refactoring.
- **Rule 4:** Never delete any code, file, or setting without a documented, valid technical reason.
- **Rule 5:** Never break architectural boundaries or patterns established in Phase 0.
- **Rule 6:** No shortcuts. Follow all quality gates and tests.
- **Rule 7:** Never duplicate code. Extract shared logic into utility modules or custom tools.
- **Rule 8:** Keep everything strictly modular.
- **Rule 9:** Make everything testable with automated unit and integration tests.
- **Rule 10:** Document everything. Every new file, feature, and endpoint must be documented immediately.
- **Rule 11:** Enforce one responsibility per module (Single Responsibility Principle).
- **Rule 12:** No temporary hacks or "TODO" items in code. All implementations must be production-ready.
- **Rule 13:** No hardcoded values. Utilize configurations, environment variables, or secrets vaults.
- **Rule 14:** No hidden dependencies. All external packages must be declared in dependency manifests.
- **Rule 15:** Always think long-term when designing schemas, APIs, and file layouts.

## Responsibilities
- **Agents (AI Developers/Reviewers):** Must parse and validate compliance with this Constitution at the start of every session.
- **Human Developers:** Must audit and enforce compliance during manual code reviews and validation checkpoints.

## Dependencies
- Zero external dependencies. This file is the root-level dependency of all other documents and system code.

## Interfaces
- Read access interface for all active agents. Passed as a system prompt inject or primary context window load.

## Examples
- **Correct Behavior:** An AI developer is asked to add a user registration API. Before writing any endpoint code, the agent reads `00_PROJECT_CONSTITUTION.md`, then `05_SYSTEM_ARCHITECTURE.md`, checks if a helper database module already exists, and designs a clean schema model in a modular folder.
- **Incorrect Behavior:** An AI developer directly writes a 100-line route function containing database queries, hardcoded connection strings, and no unit tests. (Violates Rules 1, 7, 8, 9, 11, and 13).

## Failure Cases
- **Prompt Drift:** Agents ignore this document due to context pressure. *Mitigation:* Layered context loading (see `10_CONTEXT_LOADING_RULES.md`) strictly limits files loaded at any time to prevent overflow.
- **Spec Contradiction:** A feature specification contradicts a Constitutional rule. *Mitigation:* The Constitution wins. Specifications must be altered or an ADR must be created to resolve conflicts.

## Security Considerations
- The Constitution forbids hardcoding secrets (Rule 13). All credentials must go through the Secret Management policy (`29_SECRET_MANAGEMENT.md`).

## Future Extension
- Modifying this Constitution requires an explicit Architecture Decision Record (ADR) update and human-in-the-loop approval.

## Related Documents
- [01_PROJECT_CHARTER.md](file:///e:/jarvis/docs/01_PROJECT_CHARTER.md)
- [05_SYSTEM_ARCHITECTURE.md](file:///e:/jarvis/docs/05_SYSTEM_ARCHITECTURE.md)
- [09_PROMPT_CONSTITUTION.md](file:///e:/jarvis/docs/09_PROMPT_CONSTITUTION.md)
- [10_CONTEXT_LOADING_RULES.md](file:///e:/jarvis/docs/10_CONTEXT_LOADING_RULES.md)
