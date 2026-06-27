# 61_RUNTIME_STATE_MACHINE.md

## Purpose
This document defines the Runtime State Machine for JARVIS OS. It establishes the global lifecycle states, transition validation rules, and loop locks that govern all active system agents.

## Scope
Applies to the Swarm Orchestrator, Planner Agent loops, and individual subagent execution profiles.

## Runtime State Machine & Transitions
System agents must strictly follow the transition path defined below. Skipping states or modifying sequences is forbidden:

```
    [Idle]
      ↓
  [Observe]  (Ingest prompts, system telemetry)
      ↓
[Understand] (Analyze context constraints)
      ↓
    [Plan]   (Create subtasks wave trees)
      ↓
   [Spawn]   (Instantiate subagent containers)
      ↓
  [Execute]  (Execute sandboxed tools)
      ↓
  [Verify]   (Run TDD assertions tests)
      ↓
  [Reflect]  (Assess performance, self-correct errors)
      ↓
   [Learn]   (Index Knowledge Graph relations)
      ↓
  [Archive]  (Sync session logs, write memory states)
      ↓
   [Sleep]   (Return to Idle queue)
```

### State Lock Heuristics
1. **Transition Verification:** Agents cannot transition to `Execute` until the `Plan` stage is fully verified and parsed as valid JSON.
2. **Post-Execution Lock:** No task state is marked `Complete` until the `Verify` and `Reflect` cycles return positive checks.
3. **Interrupt Transitions:** If a critical exception or budget limit is hit, the state machine bypasses normal transitions and routes directly to the Failsafe Recovery state (see `72_RECOVERY_MODE.md`).

## Responsibilities
- **Swarm Orchestrator:** Updates agent state values, processes transitions in Redis, and enforces loop locks.
- **System Supervisor:** Monitors active state paths and flags hung processes.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 2, Rule 5, and Rule 11).

## Interfaces
- WebSocket event: `agent_state_changed` payload (see `34_API_STANDARD.md`).
- Redis states: `jarvis:state:agent:[agent_id]`.

## Examples
- **Correct State Transition:** Agent starts `Idle` -> receives goal -> transitions to `Observe` -> parses constraints -> `Plan` -> `Execute` inside container -> `Verify` -> logs results -> `Sleep`.
- **Incorrect State Transition:** Agent receives goal, ignores planning, and directly runs terminal commands in `Execute` mode. (Violates State Sequence rule).

## Failure Cases
- **State Hang:** An agent gets stuck in `Understand` mode because the LLM prompt fails to parse. *Mitigation:* The orchestrator enforces a state timeout limit (default: 3 minutes). If a state does not change, it raises a timeout error and triggers the Debugger.

## Security Considerations
- The transition path guarantees that the Security Agent (in `Understand` and `Verify` modes) validates tool arguments before execution.

## Future Extension
- Adding new states to the lifecycle must be documented in ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [08_AI_AGENT_CONSTITUTION.md](file:///e:/jarvis/docs/08_AI_AGENT_CONSTITUTION.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
- [72_RECOVERY_MODE.md](file:///e:/jarvis/docs/72_RECOVERY_MODE.md)
