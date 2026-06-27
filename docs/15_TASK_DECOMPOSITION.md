# 15_TASK_DECOMPOSITION.md

## Purpose
This document defines the Task Decomposition policy for JARVIS OS. It governs how the Planner Agent decomposes complex goals into parallel-optimized execution wave plans and checklists.

## Scope
Applies to the Planner Agent, Swarm Orchestrator, and task template generators inside the Brain Core.

## Task Decomposition & Planning Policies
1. **Goal-Tree Decomposition:** Every high-level goal must be decomposed into a Goal-Tree before any execution starts.
2. **Parallel-Optimized Wave Structure:**
   - Tasks must be grouped into sequential **Execution Waves** (e.g. Wave 1, Wave 2, Wave 3).
   - Tasks in the same Wave must be completely independent and must not modify the same files.
   - Tasks in later Waves can depend on tasks completed in earlier Waves.
3. **Task Atomicity Guidelines:**
   - Each Wave contains a maximum of 3 tasks.
   - No single task can modify more than 5 files.
   - If a task crosses subsystem boundaries (e.g. database schema change AND frontend UI update), it must be split into two separate tasks.

## Responsibilities
- **Planner Agent:** Creates the goal-tree, defines execution waves, maps dependencies, and populates task templates.
- **Swarm Orchestrator:** Instantiates the waves and tracks completion status.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 1, Rule 8, and Rule 11).

## Interfaces
- Input: Goal specs parsed by the reasoning core.
- Output: Task checklist files (`task.md`) and execution configurations loaded into Redis.

## Examples
- **Correct Decomposition:**
  - Goal: Create User Profile system.
  - Wave 1: Database Migration (`[NEW] schema.sql`).
  - Wave 2: Backend API Route (`[NEW] api/profile.py`).
  - Wave 3: Frontend Component (`[NEW] components/Profile.tsx`).
- **Incorrect Decomposition:**
  - Goal: Create User Profile system.
  - Wave 1: Create database schema, write APIs, write frontend code, build project, and deploy. (Violates atomicity and layer isolation).

## Failure Cases
- **Circular Task Dependency:** Task A depends on Task B, which depends on Task A. *Mitigation:* The Planner runs a directed acyclic graph (DAG) cycle-detector on the goal-tree before launching the execution waves. If a cycle is detected, planning halts and requests self-healing.

## Security Considerations
- Tasks must have strictly defined scopes. Tasks that request shell commands or direct file system access are flagged for Security Agent validation.

## Future Extension
- Modifications to planning criteria or wave size rules are managed via ADR revisions.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [11_REASONING_POLICY.md](file:///e:/jarvis/docs/11_REASONING_POLICY.md)
- [52_TASK_TEMPLATE.md](file:///e:/jarvis/docs/52_TASK_TEMPLATE.md)
- [69_SYSTEM_DEPENDENCY_GRAPH.md](file:///e:/jarvis/docs/69_SYSTEM_DEPENDENCY_GRAPH.md)
