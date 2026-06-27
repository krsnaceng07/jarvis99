# 26_SECURITY_CONSTITUTION.md

## Purpose
This document establishes the Security Constitution for JARVIS OS. It defines the core security principles, data encryption standards, access control models, and signature rules.

## Scope
Applies to all source code repositories, databases, file system adapters, API endpoints, and execution environments in the JARVIS OS ecosystem.

## Core Security Rules
1. **Zero Trust execution:** Every code module, dynamic skill, or browser page is treated as untrusted. Host system operations require permission checking.
2. **Encrypted Storage Standard:** Sensitive database fields (e.g. workspace credentials, user settings, vector memory summaries) must be encrypted using AES-256-GCM. Plaintext storage of secrets is strictly prohibited.
3. **Execution Sandbox Isolation:** Untrusted tool code and custom plugins must run inside Docker containers with restricted disk, memory, and network permissions (see `28_SANDBOX_POLICY.md`).
4. **Immutable Audit Logging:** Every system call, configuration update, command run, and authorization gate must write a signed, read-only audit log entry (see `37_LOGGING_STANDARD.md`).
5. **Skill Signing Gate:** Dynamic skills must contain a SHA-256 signature generated and verified by the Security Agent before execution (see `68_PLUGIN_TRUST_POLICY.md`).

## Responsibilities
- **Security Agent:** Reviews source code, scans dependencies, audits dynamic skill signatures, and intercepts runtime command payloads.
- **System Administrator:** Rotates database keys and manages secrets vaults configurations.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4, Rule 13, and Rule 14).

## Interfaces
- Local APIs: `jarvis.security.encrypt`, `jarvis.security.decrypt`, and `jarvis.security.verify_signature`.

## Examples
- **Correct Flow:** An API token is stored in the database. The system encrypts the token using the primary key from the local vault before saving the database row.
- **Incorrect Flow:** An agent generates a script that writes a plaintext configuration file containing AWS credentials to the workspace directory. (Violates Encrypted Storage and Secret Management rules).

## Failure Cases
- **Key Compromise:** The primary database encryption key is leaked or lost. *Mitigation:* The system supports automated key rotation schedules. A master recovery key is stored securely offsite or managed via standard environment vaults.

## Security Considerations
- High-level security protocols must never be bypassed by local debug switches or "dry-run" modes.

## Future Extension
- Security policy updates require explicit ADR entries and multi-factor human user approval.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [27_PERMISSION_SYSTEM.md](file:///e:/jarvis/docs/27_PERMISSION_SYSTEM.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
- [29_SECRET_MANAGEMENT.md](file:///e:/jarvis/docs/29_SECRET_MANAGEMENT.md)
