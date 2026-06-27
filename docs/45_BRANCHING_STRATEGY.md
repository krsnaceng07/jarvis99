# 45_BRANCHING_STRATEGY.md

## Purpose
This document defines the Branching Strategy for JARVIS OS. It establishes branch naming rules, main branch protections, and hotfix pipelines to ensure safe parallel development.

## Scope
Applies to all branches, tags, and version merges created inside the repository.

## Branching Guidelines & Strategy
1. **Branch Naming Standard:** All development branches must follow a structured naming pattern:
   - `[category]/[issue-id]-[short-description]`
   - Categories: `feature/` (new features), `bugfix/` (bug resolutions), `hotfix/` (production patch), `docs/` (specification updates).
   - Example: `feature/12-dynamic-skill-compilation`.
2. **Main Branch Protection:**
   - The `main` branch is protected. Direct commits are disabled.
   - Merging to `main` requires a pull request, passing CI/CD tests, and manual reviewer approval.
3. **Hotfix Pipeline:** Hotfixes are branched directly from the current production tag, patched, tested, merged back to both `main` and active development branches, and tagged immediately.

## Responsibilities
- **Developer Agent:** Creates branches using the naming standard.
- **System Administrator:** Configures branch protection rules in GitHub/GitLab repository settings.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 3, Rule 4, and Rule 5).

## Interfaces
- Repository API: Git branch and checkout endpoints.

## Examples
- **Correct Branch Name:** `bugfix/45-pgvector-timeout-error`.
- **Incorrect Branch Name:** `fix-db-timeout`. (Violates category and issue ID requirements).

## Failure Cases
- **Merge Conflicts:** Two parallel feature branches modify the same file layer, causing a merge block. *Mitigation:* The branching strategy mandates pulling updates from `main` into the feature branch daily. If conflicts occur, they must be resolved locally and tested before PR submission.

## Security Considerations
- Feature branches are publicly visible in standard team setups. Developers must verify that no sensitive configuration files are committed to feature branches.

## Future Extension
- Modifying branching patterns (e.g. adopting GitFlow fully) is managed via ADR logs.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [44_GIT_WORKFLOW.md](file:///e:/jarvis/docs/44_GIT_WORKFLOW.md)
- [46_RELEASE_POLICY.md](file:///e:/jarvis/docs/46_RELEASE_POLICY.md)
