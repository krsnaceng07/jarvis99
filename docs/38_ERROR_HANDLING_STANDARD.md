# 38_ERROR_HANDLING_STANDARD.md

## Purpose
This document defines the Error Handling Standard for JARVIS OS. It establishes the base exception hierarchy, bubble rules, retry logic, and recovery protocols for all system errors.

## Scope
Applies to all source code written in backend api modules, agents, custom tools, and database clients.

## Error Handling Standards & Custom Classes
1. **Base Exception Hierarchy:** All system errors must derive from a single unified class: `JarvisError`.
   - Custom exceptions must represent specific error categories:
     - `JarvisConnectionError`: Database, Redis, or API connection drops.
     - `JarvisValidationError`: Schema validation failures, invalid arguments.
     - `JarvisPermissionError`: Unapproved L2/L3 operations, security blocks.
     - `JarvisExecutionError`: Tool execution runtime failures inside sandbox.
2. **Explicit Try-Catch Rules:**
   - Empty catch blocks (`except: pass` or `catch(e) {}`) are strictly prohibited.
   - Exceptions must be caught at logical boundaries, logged with correlation tracing IDs, and resolved or re-thrown safely.
3. **Structured Retry Policies:** Outbound network requests and database queries must implement exponential backoff retry parameters:
   - Initial delay: 100ms.
   - Max retries: 3 attempts.
   - Backoff multiplier: 2.0.

## Responsibilities
- **Developer Agent:** Uses custom exception classes and implements retry wrapper decorators.
- **System Supervisor:** Manages thread crashes and triggers recovery loops (see `23_SELF_HEALING_POLICY.md`).

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Base Exception Class: `jarvis.core.exceptions.JarvisError`.

## Examples
- **Correct Error Handling:**
```python
try:
    await database.execute(query)
except JarvisConnectionError as err:
    logger.error("DB query failed", exc_info=err)
    await retry_with_backoff(database.execute, query)
```
- **Incorrect Error Handling:**
```python
try:
    database.execute(query)
except:
    pass  # Swallows exception silently (Violates Try-Catch and Logging rules).
```

## Failure Cases
- **Infinite Retry Loop:** Network remains offline, causing infinite retries. *Mitigation:* The system enforces a maximum of 3 retry attempts. If all 3 fail, the exception is raised up the chain to the supervisor.

## Security Considerations
- Stack traces containing file paths or variables must never be returned in API response payloads or written to external logs (see `34_API_STANDARD.md`).

## Future Extension
- Modifying exception structures or base classes requires updates in the system configurations.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [23_SELF_HEALING_POLICY.md](file:///e:/jarvis/docs/23_SELF_HEALING_POLICY.md)
- [33_ERROR_HANDLING_STANDARD.md](file:///e:/jarvis/docs/33_ERROR_HANDLING_STANDARD.md)
- [34_API_STANDARD.md](file:///e:/jarvis/docs/34_API_STANDARD.md)
