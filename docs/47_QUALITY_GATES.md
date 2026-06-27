# 47_QUALITY_GATES.md

## Purpose
This document defines the Quality Gates for JARVIS OS. It establishes the mandatory linting, testing, security, and architectural checks that must pass before any code is merged into target branches.

## Scope
Applies to all pull requests, automated CI/CD runners, and repository branch configurations.

## Mandatory Quality Gates
To merge any pull request or execute a deployment, the following gates must be successfully validated:

| Gate | Target Metric | Tool / Command | Failure Action |
| --- | --- | --- | --- |
| **Linting** | Zero errors/warnings | `flake8`, `black --check`, `eslint` | Block Merge |
| **Type Check** | Zero type errors | `mypy`, `tsc --noEmit` | Block Merge |
| **Code Coverage** | Minimum **80%** (100% for Security) | `pytest-cov`, `jest --coverage` | Block Merge |
| **Security Scan** | Zero critical/high risks | `bandit`, `npm audit` | Block Merge |
| **Architecture Audit**| Zero dependency cycles, no direct system calls outside tool layer | Dependency check script | Block Merge |
| **Approval** | 1 human approval required | Github PR Approval | Block Merge |

## Responsibilities
- **CI/CD Build Runner:** Automates execution of linting, testing, security, and structural checks.
- **Reviewer Agent:** Manages code review checklists and verifies structural compliance (see `54_CODE_REVIEW_TEMPLATE.md`).

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 6, Rule 9, and Rule 10).

## Interfaces
- GitHub Actions Integration: Gates are run as steps inside `.github/workflows/ci.yaml`.

## Examples
- **Correct Gate Behavior:** A developer submits a PR. The linter runs cleanly, test coverage is verified as 84%, bandit scans report no security risks, and the PR is approved.
- **Incorrect Gate Behavior:** Merging code containing active flake8 errors and 60% test coverage because of project time pressure. (Violates Linting and Coverage gates).

## Failure Cases
- **Stale Dependabot Alerts:** An third-party library is flagged with a security risk, blocking the build. *Mitigation:* The Security Agent checks the package vulnerability severity. If it is high/critical, the package must be updated immediately before code merges are authorized.

## Security Considerations
- Bypassing Quality Gates is technically locked. Administrative overrides are disabled on main branches to prevent accidental security drops.

## Future Extension
- Enhancing gate parameters (e.g. adding performance benchmarking gates) is documented via ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [33_CODE_STANDARD.md](file:///e:/jarvis/docs/33_CODE_STANDARD.md)
- [41_TESTING_STANDARD.md](file:///e:/jarvis/docs/41_TESTING_STANDARD.md)
- [42_CI_CD_STANDARD.md](file:///e:/jarvis/docs/42_CI_CD_STANDARD.md)
- [54_CODE_REVIEW_TEMPLATE.md](file:///e:/jarvis/docs/54_CODE_REVIEW_TEMPLATE.md)
- [56_DEFINITION_OF_DONE.md](file:///e:/jarvis/docs/56_DEFINITION_OF_DONE.md)
- [69_SYSTEM_DEPENDENCY_GRAPH.md](file:///e:/jarvis/docs/69_SYSTEM_DEPENDENCY_GRAPH.md)
