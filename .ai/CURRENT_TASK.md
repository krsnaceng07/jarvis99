# CURRENT TASK

**Goal:** Perform Platform Stabilization Pass (Audit, cleanup, and warn-resolution).

**Files Allowed:**
- api/dependencies.py (MODIFY)
- api/main.py (MODIFY)
- core/runtime/federation.py (MODIFY)
- tests/test_federation.py (MODIFY)
- tests/test_api_gateway.py (MODIFY)
- tests/test_browser.py (MODIFY)
- tests/test_runtime.py (MODIFY)
- .ai/CURRENT_TASK.md (this file)
- task.md (in brain directory)
- walkthrough.md (in brain directory)

**Files Forbidden:**
- Core business logic engines.
- Frozen interface modules.

**Success Criteria:**
- Fixed all async mock `RuntimeWarning` un-awaited coroutines in the test suite.
- Verified timeouts are explicitly specified for all outbound http requests.
- Validated fail-closed and log sanitization properties across federation endpoints.
