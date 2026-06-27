# 41_TESTING_STANDARD.md

## Purpose
This document defines the Testing Standard for JARVIS OS. It establishes unit testing structures, Mock library usage, integration pipeline testing, and Test-Driven Development (TDD) execution rules.

## Scope
Applies to all source directories, dynamically generated skills, backend APIs, and desktop tests.

## Testing Guidelines & TDD Rules
1. **Mandatory Test Coverage:** No production code is accepted unless accompanied by automated tests.
   - Code coverage target: Minimum of **80% coverage** for all new modules.
   - Core security modules require **100% test coverage**.
2. **TDD Execution Flow:**
   - **Red Phase:** Write failing tests matching requirements under `tests/`. Verify they fail.
   - **Green Phase:** Implement the minimal code required to pass tests. Verify they pass.
   - **Refactor Phase:** Improve code styling, modularity, and comments while protecting tests.
3. **Sandbox Test Runners:**
   - Dynamic skills must execute tests inside a isolated container profile prior to registration (see `16_SKILL_SYSTEM.md`).
   - Mocking standards: Network calls to external LLM APIs or browser controllers must be mocked during local unit test suites to prevent cost runaways and environment inconsistencies.

## Responsibilities
- **Developer Agent:** Implements test cases concurrently with code updates (TDD preferred).
- **QA / Testing Agent:** Executes test suites, computes coverage metrics, and validates boundaries.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 9 and Rule 12).

## Interfaces
- Test commands: `pytest tests/ --cov=core` (Python) and `npm test` (Next.js).

## Examples
- **Correct Test Practice:** Writing a pytest file that mocks the OpenAI request call and checks that the parser returns the correct object payload.
- **Incorrect Test Practice:** Deploying an API route without writing any matching test files in `/tests/`. (Violates Mandatory Test Coverage rule).

## Failure Cases
- **Flaky Tests:** Tests that fail randomly due to timing issues or state leaks. *Mitigation:* Integration tests must use fresh transaction contexts and cleanup database inserts upon completion. Dynamic delays are forbidden; use explicit event heartbeats instead.

## Security Considerations
- Tests must never load real API keys or sensitive system configurations. Test environment files must contain mock settings only.

## Future Extension
- Changes to testing frameworks or assertions are updated via standard code modifications.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [15_TESTING_POLICY.md](file:///e:/jarvis/docs/15_TESTING_POLICY.md)
- [16_SKILL_SYSTEM.md](file:///e:/jarvis/docs/16_SKILL_SYSTEM.md)
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md)
