# 05_AGENT_RESPONSIBILITY_FREEZE.md

## Purpose
This document freeze-locks the prompt configurations, system instructions, execution constraints, and state transition authorizations for all internal agents in JARVIS OS.

## Scope
Applies to all agent definition classes, model routing templates, and swarm orchestrators.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## Agent Responsibilities & Rules (Frozen)

### 1. Planner Agent
- **System Prompt Header:** Enforces task tree decomposition and priority queue planning.
- **Forbidden Operations:** **Never writes source code.** Never issues tool calls or shell commands.
- **Authorized Transitions:** `Observe` → `Understand` → `Plan` → `Sleep`.

### 2. Developer Agent
- **System Prompt Header:** Generates Python/TS code matching PEP 8 / Prettier formatting.
- **Forbidden Operations:** **Never executes code** or compiles libraries on the host. Cannot run tests.
- **Authorized Transitions:** `Understand` → `Execute` (generate code only) → `Sleep`.

### 3. Reviewer Agent
- **System Prompt Header:** Validates code quality, lint targets, and constitutional rules.
- **Forbidden Operations:** **Never edits source code.** Cannot deploy applications.
- **Authorized Transitions:** `Understand` → `Verify` (code review only) → `Sleep`.

### 4. Security Agent
- **System Prompt Header:** Audits tool parameters, command safety, and skill signatures.
- **Forbidden Operations:** Cannot edit code or run user applications.
- **Authorized Transitions:** `Understand` → `Verify` (audit parameter bounds) → `Sleep`.

## Responsibilities
- **Swarm Orchestrator:** Validates agent identity on PubSub channels and blocks message triggers that violate these bounds.
- **Developer Agent:** Restricts prompt adjustments to match these specifications.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 2 and Rule 8).

## Interfaces
- Local API configuration mapping: `jarvis.core.agents.registry`.

## Examples
- **Correct Swarm Action:** Developer generates code -> Reviewer approves -> Security verifies -> Executor container runs tests.
- **Incorrect Swarm Action:** Developer agent compiles code, runs a local terminal script, and approves its own PR. (Violates agent isolation rules).

## Failure Cases
- **Role Spillover:** An LLM agent generates a response containing both file planning and raw execution code. *Mitigation:* The Parser separates text output block types. If an agent output violates its role constraints, the orchestrator raises a validation error and requests retry.

## Security Considerations
- Restricting execution bounds ensures that a hijacked Developer or Planner agent cannot spawn system-level shell commands.

## Future Extension
- Enhancing agent profiles requires updating this specification and the matching prompt vaults via ADR.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [08_AI_AGENT_CONSTITUTION.md](file:///e:/jarvis/docs/08_AI_AGENT_CONSTITUTION.md)
- [13_AGENT_LIFECYCLE_DIAGRAM.md](file:///e:/jarvis/docs/architecture/13_AGENT_LIFECYCLE_DIAGRAM.md)
