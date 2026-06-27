# 56_DEFINITION_OF_DONE.md

## Purpose
This document defines the Definition of Done (DoD) for JARVIS OS. It establishes the mandatory validation checklist that every task, module, and feature must pass before it is marked as completed in the repository.

## Scope
Applies to all source code changes, database migrations, document updates, and tool registrations.

## Definition of Done (DoD) Checklist
A feature is not complete and cannot be merged into the protected branch until it satisfies the following validation checklist:

- [ ] **Implementation Complete:** Code is written, refactored, and fits PEP 8 / TypeScript conventions cleanly.
- [ ] **Type Check Pass:** Zero type compilation errors or warnings (TSC / MyPy).
- [ ] **Unit & Integration Tests Pass:** Standard pytest and jest runs return 100% green.
- [ ] **Coverage Standard Met:** Code coverage is 80% or higher (100% for security files).
- [ ] **Security Audits Pass:** Bandit and NPM audit checks return zero critical or high-severity vulnerabilities.
- [ ] **No Circular Dependencies:** Verified by dependency graph analyzers.
- [ ] **No Hardcoded Secrets:** Vault integration confirmed.
- [ ] **Documentation Updated:** Section docstrings are complete, and matching user guides are written.
- [ ] **Performance Benchmarks Met:** API latencies run below 200ms.
- [ ] **Peer/AI Review Approved:** PR approved by the Reviewer Agent and at least one human developer.

## Responsibilities
- **Developer Agent:** Verifies compliance with this checklist before submitting PRs.
- **Reviewer Agent:** Validates each DoD item and blocks merges if any checkbox is incomplete.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 6, Rule 9, and Rule 10).

## Interfaces
- Input: Active PR metadata and verification results.
- Output: DoD verification report appended to the Git history.

## Examples
- **Correct DoD Verification:** A task checklist shows all 10 checkboxes marked, the CI pipeline verifies test coverage is 85%, and the PR is merged.
- **Incorrect DoD Verification:** Marking a task as done when tests are failing or type annotations are missing. (Violates core quality guidelines).

## Failure Cases
- **Bypassed Checkpoints:** Merge rules are ignored to push a hot-patch quickly. *Mitigation:* Branch protections block repository merge access until the automated CI/CD pipeline returns positive checks for all quality gates.

## Security Considerations
- Code reviews must verify that test cases are realistic and do not use generic assertions (e.g. `assert True`) to cheat coverage metrics.

## Future Extension
- Template updates are logged in ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [33_CODE_STANDARD.md](file:///e:/jarvis/docs/33_CODE_STANDARD.md)
- [43_DEFINITION_OF_DONE.md](file:///e:/jarvis/docs/43_DEFINITION_OF_DONE.md)
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md)
- [54_CODE_REVIEW_TEMPLATE.md](file:///e:/jarvis/docs/54_CODE_REVIEW_TEMPLATE.md)
