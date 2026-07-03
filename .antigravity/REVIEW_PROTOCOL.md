# REVIEW PROTOCOL

## Pre-Completion Checklist

Before submitting a milestone or task for review, the coding agent must perform a multi-dimensional audit against the criteria below.

---

### 1. Architecture Audit
* [ ] Does every modified file have a single responsibility?
* [ ] Are there zero dependency cycles or layer reversals?
* [ ] Did we avoid calling repositories directly from the API layer?
* [ ] Are all core components sitting behind abstract interfaces?

### 2. Security Audit
* [ ] Are there strict validation checks on all incoming parameters?
* [ ] Are all credentials, keys, or passwords loaded from the configuration system/secrets vault?
* [ ] Are trust, permission, and validation boundaries explicitly respected?
* [ ] Does the security module maintain 100% test coverage?

### 3. Reliability Audit
* [ ] Does the implementation assume everything can fail (network, databases, LLM calls)?
* [ ] Are retry mechanisms with exponential backoffs applied to external HTTP/TCP requests?
* [ ] Are query or call timeouts explicitly set?
* [ ] Is state modification idempotent and recoverable?

### 4. Performance Audit
* [ ] Are database operations optimized (indexed search, limited batch queries, no N+1 query loops)?
* [ ] Is system memory footprint constrained (streaming large files/responses, avoiding loading massive tables)?
* [ ] Are caching layers implemented for high-frequency, slow-changing inputs?

### 5. Testing & Verification Audit
* [ ] Do unit tests cover success paths, edge boundary values, and explicit failure/exception branches?
* [ ] Have integration tests been run to ensure no regressions in surrounding subsystems?
* [ ] Are test database setups and teardowns fully clean and isolated?

### 6. Observability Audit
* [ ] Are all caught errors explicitly logged with structured JSON format and trace/correlation IDs?
* [ ] Are important lifecycle changes, state updates, and transaction completions logged?

### 7. Documentation & Naming Audit
* [ ] Are all public functions, classes, and variables named clearly according to project standard?
* [ ] Is every new file decorated with the standardized header docstring?
* [ ] Are specification files and the Master Index fully updated?
