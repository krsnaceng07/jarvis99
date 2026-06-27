# 50_FEATURE_TEMPLATE.md

## Purpose
This document defines the Feature Template for JARVIS OS. It establishes the mandatory specification format that agents and developers must use when proposing or implementing a new feature in the codebase.

## Scope
Applies to all feature proposal documents, pull request descriptions, and feature specifications.

## Feature Template Layout
Every new feature specification file must use the exact markdown structure defined below:

```markdown
# [Feature Name]

## Feature Overview
- **Objective:** What problem does this solve and why does it matter?
- **User Story:** As a [role], I want to [action] so that [benefit].

## Functional Requirements
- Requirement 1: Description and DoD.
- Requirement 2: Description and DoD.

## Technical Design & API Specifications
- File Layout: List of paths to modify or create.
- Endpoints: REST and WebSocket contracts.
- Database Changes: Schema updates and index creations.

## Security Considerations
- Permission levels required (L0 to L3).
- Input sanitization requirements.

## Testing & Verification Plan
- Unit tests: Expected files and mocks.
- Integration tests: Execution flows.

## Related Documents
- Links to relevant foundation files.
```

## Responsibilities
- **Developer Agent:** Must write new feature proposals matching this template structure before coding begins.
- **Reviewer Agent:** Rejects PRs and feature files that do not follow this layout.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 10 and Rule 11).

## Interfaces
- Input: User feature requests.
- Output: Generated feature specification file (e.g. `docs/features/lead_scraper.md`).

## Examples
- **Correct Feature Spec:** A developer drafts a clean feature file following this layout, defining permission targets and testing plans.
- **Incorrect Feature Spec:** A developer starts coding a feature directly in the repository without drafting any requirements or layout plans. (Violates core planning and documentation rules).

## Failure Cases
- **Template Drift:** Agents ignore template fields to save time. *Mitigation:* The Quality Gates check that every new feature PR contains a corresponding spec file matching these exact headers.

## Security Considerations
- Proposing features that bypass sandboxing or permission systems is blocked during feature review.

## Future Extension
- Template fields can be extended through ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [08_AI_AGENT_CONSTITUTION.md](file:///e:/jarvis/docs/08_AI_AGENT_CONSTITUTION.md)
- [43_DEFINITION_OF_DONE.md](file:///e:/jarvis/docs/43_DEFINITION_OF_DONE.md)
- [56_DEFINITION_OF_DONE.md](file:///e:/jarvis/docs/56_DEFINITION_OF_DONE.md)
