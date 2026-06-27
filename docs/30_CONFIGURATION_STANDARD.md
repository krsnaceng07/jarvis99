# 30_CONFIGURATION_STANDARD.md

## Purpose
This document defines the Configuration Standard for JARVIS OS. It establishes the rules, syntax, validations, and environment profiles required to manage settings across backend, frontend, database, and sandbox systems.

## Scope
Applies to all configuration files (`config.yaml`, settings schemas), Pydantic settings modules, and environment initialization scripts.

## Configuration Standards & Environment Profiles
1. **Pydantic Validation standard:** All configurations must be loaded and parsed using Pydantic Settings models to ensure type safety and run-time validation.
2. **Environment Profiles:** The system must support three operational profiles:
   - `development`: Verbose logging, SQLite fallback options enabled, local sandbox overrides.
   - `staging`: Postgres database integration, strict sandbox isolation, automated testing suites.
   - `production`: SSL required, Postgres/PgVector required, strict multi-tier permissions, production models active.
3. **Structured YAML Configuration:** Static configurations (model names, tool registry keys, retry behaviors) must go into a unified `config.yaml` file validated against a JSON schema.

## Responsibilities
- **Configuration Manager Service:** Loads environment settings, validates types on startup, and exports active settings profiles.
- **Developer Agent:** Adds config variables to the Pydantic models when creating new modules.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 13 and Rule 14).

## Interfaces
- Base Class: `jarvis.core.config.Settings` (derived from Pydantic `BaseSettings`).

## Examples
- **Correct Configuration Model:**
```python
from pydantic_settings import BaseSettings

class DatabaseSettings(BaseSettings):
    host: str
    port: int = 5432
    username: str
    password: str

    class Config:
        env_prefix = "DB_"
```
- **Incorrect Configuration Model:**
Using unstructured python dictionaries `config = {"db_port": 5432}` without type verification, defaults, or schema validations. (Violates Pydantic Validation rule).

## Failure Cases
- **Missing Variable on Startup:** The `.env` file lacks the `DB_PASSWORD` string. *Mitigation:* The system boot sequence loads Pydantic Settings and raises a `ValidationError` exception, preventing the API server from starting up with incomplete parameters.

## Security Considerations
- Default configurations must never include production secrets. Template configuration files (e.g. `.env.example`) must contain placeholder values only.

## Future Extension
- Configuration updates are managed via standard code reviews and quality gates.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [04_TECHNICAL_REQUIREMENTS.md](file:///e:/jarvis/docs/04_TECHNICAL_REQUIREMENTS.md)
- [29_SECRET_MANAGEMENT.md](file:///e:/jarvis/docs/29_SECRET_MANAGEMENT.md)
- [70_BOOT_SEQUENCE.md](file:///e:/jarvis/docs/70_BOOT_SEQUENCE.md)
