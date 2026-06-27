# 29_SECRET_MANAGEMENT.md

## Purpose
This document defines the Secret Management Policy for JARVIS OS. It details how the system encrypts, isolates, accesses, and rotates API credentials, database passwords, and user authorization tokens.

## Scope
Applies to all environment variables, `.env` file configurations, vault storage APIs, and active database credential tables.

## Secret Isolation & Storage Policies
1. **No Plaintext Storage:** Storage of secrets, database credentials, or API keys in code repos, text logs, or plaintext configuration files is strictly forbidden.
2. **Encrypted Vault Standard:** All active credentials must be stored inside a secure database vault encrypted using AES-256-GCM.
3. **Environment Isolation:** Standard configuration keys are loaded via environment variables, but sensitive keys (e.g. cloud LLM keys) must be fetched dynamically at runtime from the vault by authorized agents.
4. **Token Isolation:** Sandbox containers are blocked from reading the `.env` file of the host system. Needed tokens must be injected as transient container variables during boot.

## Responsibilities
- **Vault Manager Service:** Decrypts required credentials in memory, restricts access based on calling agent permissions, and monitors token access logs.
- **Human Owner:** Inputs credentials via the dashboard settings page, and manages key rotation variables.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 13 and Rule 14).

## Interfaces
- Local API queries: `VaultManager.get_secret(key_name: str, agent_id: UUID)`.

## Examples
- **Correct Flow:** Planner requests a search tool. The system retrieves the Google API key from the encrypted Postgres vault, decrypts it in memory, invokes the API, and immediately discards the key string.
- **Incorrect Flow:** The agent commits a `.env` file containing the Anthropic API key to the public git repository. (Violates core security rules).

## Failure Cases
- **Key Decryption Failure:** The vault master key is corrupted, preventing access to LLMs. *Mitigation:* The vault manager checks key validity during the system boot sequence (see `70_BOOT_SEQUENCE.md`). If validation fails, it halts boot, logs a fatal system alert, and escalates to recovery mode.

## Security Considerations
- Memory cores must sweep sensitive variable allocations from the garbage collector immediately after use to prevent memory-dump attacks.

## Future Extension
- Integration with external enterprise vaults (e.g. HashiCorp Vault) is managed through the Configuration and Database standards.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [26_SECURITY_CONSTITUTION.md](file:///e:/jarvis/docs/26_SECURITY_CONSTITUTION.md)
- [30_CONFIGURATION_STANDARD.md](file:///e:/jarvis/docs/30_CONFIGURATION_STANDARD.md)
- [70_BOOT_SEQUENCE.md](file:///e:/jarvis/docs/70_BOOT_SEQUENCE.md)
