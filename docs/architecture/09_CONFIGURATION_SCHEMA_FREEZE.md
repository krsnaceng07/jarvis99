# 09_CONFIGURATION_SCHEMA_FREEZE.md

## Purpose
This document freeze-locks the configuration schemas, Pydantic settings models, environment profiles, and static config files formats for JARVIS OS.

## Scope
Applies to all configuration files (`config.yaml`, `models.yaml`, `permissions.yaml`), Pydantic settings packages, and system boot validation rules.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## Configuration Schemas & Models (Frozen)

### 1. Unified Configuration Schema (`config.yaml`)
```yaml
system:
  environment: "production"  # development / staging / production
  debug: false
  log_level: "INFO"

database:
  host: "localhost"
  port: 5432
  name: "jarvis_db"
  username: "jarvis_user"

redis:
  host: "localhost"
  port: 6379

vault:
  encryption_key_path: "secrets/master.key"
```

### 2. Pydantic Settings Validation Model
```python
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

class SystemConfig(BaseModel):
    environment: str = Field(default="production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

class DatabaseConfig(BaseModel):
    host: str
    port: int = 5432
    name: str
    username: str

class Settings(BaseSettings):
    system: SystemConfig
    database: DatabaseConfig

    class Config:
        env_prefix = "JARVIS_"
```

## Responsibilities
- **Configuration Manager:** Parses config files, validates types, and rejects boot if variables do not match these specifications.
- **Developer Agent:** Adds variables to matching schema definitions before calling them in source code files.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 13 and Rule 14).

## Interfaces
- Config loader class: `jarvis.core.config.Settings`.

## Examples
- **Correct Configuration:** Defining `database.port` as integer `5432` in `config.yaml`.
- **Incorrect Configuration:** Defining `database.port` as string `"fifty-four-thirty-two"` or omitting required database keys. (Violates validation models).

## Failure Cases
- **Missing Environment Variable:** The server attempts to boot in production but the `.env` lacks database connection strings. *Mitigation:* The Configuration Manager catches Pydantic validation errors, logs a FATAL startup trace, halts the boot sequence, and exits.

## Security Considerations
- Configuration schemas must never store active passwords, access tokens, or vault keys. These variables must use the secure placeholder values.

## Future Extension
- Enhancements to the settings schema require updating Pydantic models and creating ADR logs.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [29_SECRET_MANAGEMENT.md](file:///e:/jarvis/docs/29_SECRET_MANAGEMENT.md)
- [30_CONFIGURATION_STANDARD.md](file:///e:/jarvis/docs/30_CONFIGURATION_STANDARD.md)
- [70_BOOT_SEQUENCE.md](file:///e:/jarvis/docs/70_BOOT_SEQUENCE.md)
