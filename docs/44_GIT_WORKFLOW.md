# 44_GIT_WORKFLOW.md

## Purpose
This document defines the Git Workflow for JARVIS OS. It establishes the commit message guidelines, pull request structures, and branch merge policies to maintain a clean git history.

## Scope
Applies to all commits, branches, pull requests, and merges inside the JARVIS OS source code repositories.

## Git Workflow Standards
1. **Commit Message Format:** All commits must follow the Conventional Commits specification:
   - `<type>(<scope>): <subject>`
   - Types: `feat` (new feature), `fix` (bug fix), `docs` (documentation), `style` (formatting), `refactor` (code reorganization), `test` (adding tests), `chore` (CI/build updates).
   - Subject: Concise summary in the present tense (e.g. `feat(api): add user profile endpoint`).
2. **Pull Request Template:** Every PR must include:
   - Objective & Context.
   - Reference task IDs.
   - Output/Diff breakdown.
   - Verification status (link to test runs).
3. **No Force Pushes:** Force pushing to main branches (`main`, `master`, `develop`) is strictly forbidden. All updates must go through pull request reviews.

## Responsibilities
- **Developer Agent:** Formats commit messages and creates structured pull requests.
- **Reviewer Agent:** Audits branch history and merges approved PRs.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 3, Rule 4, and Rule 10).

## Interfaces
- Git Client APIs and repository hooks.

## Examples
- **Correct Commit Message:** `fix(memory): resolve pgvector index mismatch during query`.
- **Incorrect Commit Message:** `fixed some stuff in DB`. (Violates Conventional Commits specification).

## Failure Cases
- **Unstructured commits:** An agent generates 10 minor commits with generic subjects like `work`, `wip`, `update`. *Mitigation:* A pre-commit hook runs a syntax check on commit messages and rejects pushes that do not match the Conventional Commits format.

## Security Considerations
- Commit logs must never contain access tokens, credentials, or personal system paths. Pre-commit hooks run key scans to block credential exposures.

## Future Extension
- Changes to git hooks or branch locks are updated via standard development workflows.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [42_CI_CD_STANDARD.md](file:///e:/jarvis/docs/42_CI_CD_STANDARD.md)
- [45_BRANCHING_STRATEGY.md](file:///e:/jarvis/docs/45_BRANCHING_STRATEGY.md)
