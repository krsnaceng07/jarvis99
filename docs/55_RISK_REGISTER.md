# 55_RISK_REGISTER.md

## Purpose
This document defines the Risk Register for JARVIS OS. It compiles the technical risks, security vulnerabilities, API cost concerns, and resource constraints, mapping out their probabilities, impacts, and rollback paths.

## Scope
Applies to all system-level architectures, dynamic skill systems, and automated browser routines.

## Technical Risk Matrix

| Risk ID | Description | Probability | Impact | Mitigation Strategy | Rollback Path |
| --- | --- | --- | --- | --- | --- |
| **R-01** | **Sandbox Escape:** Dynamically compiled code executes on host hardware. | Low | Critical | Low-privilege UIDs, read-only Docker mounts, AppArmor seccomp profiles (see `28_SANDBOX_POLICY.md`). | Kill all active docker processes, toggle system to Emergency Stop. |
| **R-02** | **Cost Runaway:** Swarm loop hangs, spawning infinite Claude/Gemini API calls. | Medium | High | Daily budget limits ($10.00 max), pre-call checks, local fallbacks (see `65_COST_GOVERNOR.md`). | Flush active task queues, switch router to Ollama local-only mode. |
| **R-03** | **Memory Corruption:** Knowledge graph gets bloated or develops circular loops. | Medium | Medium | Traversal limit rules (3 degrees max), weekly integrity cleanups (see `25_KNOWLEDGE_GRAPH.md`). | Restore DB from last daily snapshot file. |
| **R-04** | **Prompt Drift:** Model ignores constitution rules due to large context. | High | Medium | Layered context loading rules (50% max budget), token compression (see `10_CONTEXT_LOADING_RULES.md`). | Restart agent session, wipe transient variable states. |

## Responsibilities
- **Security Agent:** Regularly reviews risk factors and audits compliance.
- **Human Administrator:** Monitors daily costs, reviews security alerts, and manages recovery overrides.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4 and Rule 13).

## Interfaces
- Input: Telemetry metric logs.
- Output: Security notifications on the UI dashboard.

## Examples
- **Correct Mitigation Flow:** System detects a sudden surge in API calls, flags R-02, reaches the daily budget limit, switches to local Qwen model, and logs warnings.
- **Incorrect Mitigation Flow:** A system process consumes $500 in cloud tokens because loop monitoring delays were bypassed for speed. (Violates Cost runaway mitigation rules).

## Failure Cases
- **Simultaneous Multiple Risks:** A sandbox escape occurs concurrently with database corruption. *Mitigation:* The supervisor immediately initiates an Emergency Stop, locks the host workspace, and boots into a read-only offline shell.

## Security Considerations
- The Risk Register is updated after every system integration test to capture new dependencies and potential attack vectors.

## Future Extension
- Adding risk factors requires documenting them here and updating the matching security policies.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [26_SECURITY_CONSTITUTION.md](file:///e:/jarvis/docs/26_SECURITY_CONSTITUTION.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
- [65_COST_GOVERNOR.md](file:///e:/jarvis/docs/65_COST_GOVERNOR.md)
