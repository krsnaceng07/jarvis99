# 54_CODE_REVIEW_TEMPLATE.md

## Purpose
This document defines the Code Review Template for JARVIS OS. It establishes the mandatory checklist, security audit matrix, type validation, and performance parameters that the Reviewer Agent must use to audit code submissions.

## Scope
Applies to all code reviews, pull request audits, and quality gate evaluations.

## Code Review Template Checklist
The Reviewer Agent must generate a review report containing the exact sections defined below:

```markdown
# Code Review Report - PR #[PR_ID]

## Constitutional Audit
- [ ] Rule 2: Checked context load sequence?
- [ ] Rule 7: No duplicate logic?
- [ ] Rule 9: Automated tests written?
- [ ] Rule 11: Single responsibility enforced?
- [ ] Rule 13: Zero hardcoded secrets?

## Code Quality Check
- **Flake8 / ESLint Status:** [PASS/FAIL]
- **MyPy / TypeScript Compiler:** [PASS/FAIL]
- **File Length Check (<300 lines):** [PASS/FAIL]
- **Type Hint Completeness:** [PASS/FAIL]

## Security & Sandbox Audit
- **Vulnerability scan (Bandit/NPM Audit):** [PASS/FAIL]
- **Direct Syscall Check:** Are all terminal and file APIs wrapped behind the Tool Layer? [PASS/FAIL]
- **Permission Level:** [L0/L1/L2/L3]

## Test Coverage
- **Coverage Metric (%):** [Coverage percentage]
- **Mock Integrity:** Are external APIs mocked? [PASS/FAIL]

## Recommendation
- **Status:** [APPROVED / REQUEST CHANGES]
- **Change Requests:** Detailed file path and lines to correct.
```

## Responsibilities
- **Reviewer Agent:** Generates this report for every pull request.
- **Developer Agent:** Resolves change requests listed in the report.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 3, Rule 6, and Rule 9).

## Interfaces
- Input: Git pull requests and diff data.
- Output: Review report file saved to `/docs/reviews/`.

## Examples
- **Correct Audit:** A detailed review report flagging a 400-line file, requesting decomposition, and checking off the constitutional rules.
- **Incorrect Audit:** Approving a pull request with a simple comment "LGTM" without running linters, tests, or checking coding rules. (Violates Quality Gates and Review rules).

## Failure Cases
- **Stale Reviews:** Review reports are not generated due to queue hangs. *Mitigation:* The CI/CD pipeline blocks branch merges if the review report file is missing or if its recommendation status is "REQUEST CHANGES".

## Security Considerations
- Review reports are logged to the repository history, providing a permanent security audit log of all code changes.

## Future Extension
- Template updates are logged in ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [33_CODE_STANDARD.md](file:///e:/jarvis/docs/33_CODE_STANDARD.md)
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md)
- [56_DEFINITION_OF_DONE.md](file:///e:/jarvis/docs/56_DEFINITION_OF_DONE.md)
