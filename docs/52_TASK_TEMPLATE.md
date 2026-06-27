# 52_TASK_TEMPLATE.md

## Purpose
This document defines the Task Template for JARVIS OS. It establishes the mandatory checklist layout that the Planner Agent must use to format individual tasks inside `task.md`.

## Scope
Applies to all files representing checklist task trees generated during Phase 0 and subsequent development phases.

## Task Template Layout
Every task block in the checklist must follow the exact structure defined below:

```markdown
### [Task ID]: [Task Name]
- **Target Files:** List of exact files to be created or modified (no vague wildcards).
- **Category:** `auto` (independent execution) or `checkpoint` (requires human validation/action).
- **Execution Actions:**
  - Action 1: Specific step-by-step instructions.
  - Action 2: What to avoid and WHY.
- **Verification Commands:**
  - Command 1: Exact test command or shell trigger.
- **Measurable Acceptance Criteria (DoD):**
  - Criteria 1: The verified state representing task completion.
```

## Responsibilities
- **Planner Agent:** Creates task lists using this exact template.
- **Developer Agent:** Reads task blocks to execute actions and run verification checks.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 2, Rule 6, and Rule 10).

## Interfaces
- Input: Goal trees parsed from user inputs.
- Output: Task list blocks inserted into `task.md`.

## Examples
- **Correct Task Specification:** A task listing `docs/00_PROJECT_CONSTITUTION.md` as target, with actions, validation command (`pytest tests/`), and measurable DoD criteria.
- **Incorrect Task Specification:** "Task: Fix the database. Target files: some db files. Verification: see if it runs." (Violates specific file paths and validation command rules).

## Failure Cases
- **Vague Action Commands:** The agent writes "Implement auth" as the action step. *Mitigation:* The Planner uses strict system instructions to enforce that all execution actions contain specific methods (e.g. "Use bcrypt.hashpw to hash inputs").

## Security Considerations
- High-risk task categories (L2/L3) must contain a mandatory human confirmation checkpoint step inside the verification section.

## Future Extension
- Template updates require ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [15_TASK_DECOMPOSITION.md](file:///e:/jarvis/docs/15_TASK_DECOMPOSITION.md)
- [56_DEFINITION_OF_DONE.md](file:///e:/jarvis/docs/56_DEFINITION_OF_DONE.md)
