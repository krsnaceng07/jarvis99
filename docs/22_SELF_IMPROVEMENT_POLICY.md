# 22_SELF_IMPROVEMENT_POLICY.md

## Purpose
This document defines the Self-Improvement Policy of JARVIS OS. It details how the system analyzes execution logs, optimizes routing parameters, patches runtime components, and deploys updates safely.

## Scope
Applies to the Self-Improvement Engine, performance log parsers, and deployment gates inside the Brain Core.

## Self-Improvement Framework & Gated Deployment
The system runs a structured, daily self-improvement cycle. However, **fully autonomous code modification of the production core is strictly prohibited without human approval**. The cycle must follow this flow:

```
Daily Performance Log Review
        ↓
Identify Latency Bottlenecks or Error Trends
        ↓
Isolate Root Cause Component
        ↓
Generate Target Patch inside Sandbox (docs, tests, code)
        ↓
Run Security & Verification Scans (Quality Gates)
        ↓
Pass Scans? → [NO] → Abort & Log
        ↓ [YES]
Queue Gated Release Request & Alert User
        ↓
Awaiting Human Manual Approval
    ├─ [DENY]  → Rollback Sandbox & Log
    └─ [APPROVE] → Merge Patch & Sync Database
```

### Self-Improvement Constraints
1. **Scope Limits:** Self-patching is restricted to utility files, custom skills, and prompt variables. The core system architecture, routing gateway, and database DDL cannot be modified by the self-improvement loop.
2. **Rollback Baseline:** Every self-patch must include an automated git commit checkpoint. If system integration fails, the system rolls back to the pre-patch commit (see `48_FAILSAFE_AND_ROLLBACK.md`).

## Responsibilities
- **Self-Improvement Engine:** Parses execution logs, flags optimization patches, and manages the deployment queue.
- **Reviewer Agent:** Performs strict structural reviews of generated patches.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 3, Rule 5, and Rule 12).

## Interfaces
- Input: Telemetry databases and execution logs.
- Output: Git pull requests and dashboard alerts requesting approval.

## Examples
- **Correct Improvement:** Engine finds that a scraper fails on a specific site structure, generates a parsing patch, runs local tests successfully, and sends a merge request to the user.
- **Incorrect Improvement:** Engine directly updates the FastAPI gateway file on the live production server without sandboxing or user approval. (Violates gated deployment and scope constraints).

## Failure Cases
- **Infinite Patch Cycle:** A generated patch introduces a new dependency conflict. *Mitigation:* The Quality Gates block merge if the compilation fails or if test coverage drops below the baseline.

## Security Considerations
- Generated patches are treated as untrusted code. They are scanned for malicious functions (e.g. keyloggers, phone-home network calls) by the Security Agent before being queued.

## Future Extension
- Modifying improvement scopes or logging formats must be updated in the system rules.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [23_SELF_HEALING_POLICY.md](file:///e:/jarvis/docs/23_SELF_HEALING_POLICY.md)
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md)
- [48_FAILSAFE_AND_ROLLBACK.md](file:///e:/jarvis/docs/48_FAILSAFE_AND_ROLLBACK.md)
