# 42_CI_CD_STANDARD.md

## Purpose
This document defines the CI/CD Standard for JARVIS OS. It establishes the automated pipeline rules, GitHub Actions templates, build artifacts packaging, and verification steps.

## Scope
Applies to all pull requests, branches, releases, and deployment configurations inside the JARVIS OS repository.

## CI/CD Pipeline Standards
1. **GitHub Actions Pipeline:** Every commit pushed to the repository and every pull request must trigger the automated CI/CD pipeline.
2. **Execution Pipeline Steps:**
   - **Linting:** Run Black, Flake8, ESLint, and Prettier checks.
   - **Type Validation:** Run MyPy and TypeScript compilers.
   - **Security Scan:** Run Bandit (Python security check) and NPM audit.
   - **Unit Tests:** Execute Pytest and Jest test suites.
   - **Build Verification:** Compile the Electron package and docker images.
3. **Merge Requirement:** Pull requests cannot be merged to the main branch unless all pipeline steps succeed (see `47_QUALITY_GATES.md`).

## Responsibilities
- **DevOps Engineer:** Configures YAML pipeline definitions and maintains API keys for runners.
- **Reviewer Agent:** Verifies pipeline status before authorizing branch merges.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- GitHub Actions YAML configurations in `.github/workflows/ci.yaml`.

## Examples
- **Correct Pipeline Flow:** Developer pushes code -> GitHub Actions runs lint, compiles Typescript, runs pytest, passes security, and flags PR green.
- **Incorrect Pipeline Flow:** Merging code directly to the main branch from a local machine, bypassing git checks. (Violates Merge Requirement).

## Failure Cases
- **Runner Timeout:** Heavy test suites cause the CI runner to hang and exceed execution budgets. *Mitigation:* Step timeouts are limited to 10 minutes, and tests are run in parallel where possible to optimize runner usage.

## Security Considerations
- CI/CD runner environments must use encrypted secrets for all Docker registry logins and deployment credentials. Secrets must never be printed to standard outputs.

## Future Extension
- Enhancing pipeline tasks (e.g. adding end-to-end integration test runners) requires updating this standard and creating an ADR.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [43_DEPLOYMENT_STANDARD.md](file:///e:/jarvis/docs/43_DEPLOYMENT_STANDARD.md)
- [44_GIT_WORKFLOW.md](file:///e:/jarvis/docs/44_GIT_WORKFLOW.md)
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md)
