# 53_DOCUMENTATION_TEMPLATE.md

## Purpose
This document defines the Documentation Template for JARVIS OS. It establishes the mandatory markdown skeleton, headers, cross-referencing styles, and index tags for all documentation.

## Scope
Applies to all files written under the `docs/` folder, including API guides, architecture summaries, and rule files.

## Documentation Template Layout
To prevent documentation drift and maintain consistency, every system document must use the exact structure defined below:

```markdown
# [Document ID]_[Document Name].md

## Purpose
Detailed description of the document purpose and why it matters.

## Scope
Boundaries and application rules for this specification.

## [Core Specification Header]
The detailed rules, parameters, models, and data tables representing the core guidelines.

## Responsibilities
Roles and modules responsible for enforcing or executing these rules.

## Dependencies
Mandatory reference to 00_PROJECT_CONSTITUTION.md and other prerequisites.

## Interfaces
Input, output, API routes, or data interfaces related to this policy.

## Examples
- Correct Behavior: Step-by-step example.
- Incorrect Behavior: Bad practice example and warning.

## Failure Cases
Potential risks, anomalies, loop behaviors, and mitigation actions.

## Security Considerations
Credential vaults, sandbox parameters, and user permissions implications.

## Future Extension
How this policy is upgraded or migrated in the future.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [Master Index](file:///e:/jarvis/docs/60_MASTER_INDEX.md)
- list of linked documents.
```

## Responsibilities
- **Documentation Agent / Developer Agent:** Writes and updates files matching this standard.
- **Reviewer Agent:** Verifies document layout during PR reviews.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 10).

## Interfaces
- Local documentation validation checker: [validate_docs.py](file:///C:/Users/kcs23/.gemini/antigravity-ide/brain/b1f9dfe1-fff1-4d36-897d-b179c507ba0c/scratch/validate_docs.py).

## Examples
- **Correct Doc:** This file matches this exact layout, including the Purpose and Security Considerations sections.
- **Incorrect Doc:** Writing a text file with only a list of notes and no standardized header sections. (Violates Documentation Standard).

## Failure Cases
- **Section Omission:** An agent forgets to include the "Security Considerations" section. *Mitigation:* The validation script scans all files and flags errors if any of the required section headers are missing.

## Security Considerations
- All documentation files are strictly read-only for agent routines unless explicitly authorized during compilation waves.

## Future Extension
- Template updates require ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [28_DOCUMENTATION_STANDARD.md](file:///e:/jarvis/docs/28_DOCUMENTATION_STANDARD.md)
- [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md)
