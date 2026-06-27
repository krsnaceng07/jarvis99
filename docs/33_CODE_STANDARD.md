# 33_CODE_STANDARD.md

## Purpose
This document defines the Code Standard for JARVIS OS. It establishes coding conventions, syntax formatting, typing rules, and patterns to avoid across TypeScript and Python files.

## Scope
Applies to all source code written in the backend, frontend, desktop wrapping layers, and test suites.

## Code Standards & Rules

### 1. Python Code Standards
- **Style:** Strictly adhere to PEP 8. Use Black for formatting.
- **Type Annotations:** Every function signature must contain explicit type hints for both parameters and return values:
```python
async def fetch_user(user_id: str) -> UserProfile:
```
- **Async Heuristic:** Long-running I/O operations (DB queries, HTTP requests, file access) must be asynchronous.

### 2. TypeScript / React Standards
- **Style:** Enforced via Prettier.
- **Types:** Strictly avoid using `any`. Declare custom interfaces or types for all objects.

### 3. Anti-Patterns to Avoid
- **Circular Imports:** Modules must have clear dependency chains. No horizontal imports across parallel layers.
- **God Files:** No source file may exceed **300 lines of code**. Large modules must be decomposed into smaller files.
- **Deep Nesting:** Limit nesting to a maximum of 3 levels. Extract deeply nested logic into helper functions.

## Responsibilities
- **Developer Agent:** Must format and type all generated scripts.
- **Reviewer Agent:** Runs linters (e.g. MyPy, TypeScript compiler) and rejects non-compliant code.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 7, Rule 8, and Rule 11).

## Interfaces
- Lint Gate: Automated check running `black --check`, `mypy`, and `tsc --noEmit`.

## Examples
- **Correct Implementation:** Granular imports, fully annotated type parameters, and async database querying.
- **Incorrect Implementation:** A 1,200-line single file route with multiple inline SQL queries and no type annotations. (Violates PEP 8, God File, and Modularity rules).

## Failure Cases
- **Silent Type Failures:** Code is merged with hidden `any` casts, leading to runtime crashes. *Mitigation:* The TypeScript compiler quality gate configuration contains `"noImplicitAny": true`.

## Security Considerations
- Hardcoded secrets, raw dynamic execution commands (`exec()`, `eval()`), and unsafe imports are automatically blocked by the linter parser.

## Future Extension
- Enhancing styling rules requires an ADR update before linter configurations are modified.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [27_CODE_STANDARD.md](file:///e:/jarvis/docs/27_CODE_STANDARD.md)
- [32_NAMING_STANDARD.md](file:///e:/jarvis/docs/32_NAMING_STANDARD.md)
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md)
