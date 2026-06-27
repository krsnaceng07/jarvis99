# 17_SKILL_SDK_SPEC.md

## Purpose
This document defines the Skill SDK Specification for JARVIS OS. It details the API hooks, manifest parameters, and directory layouts required for developers and agents to build compatible plugins.

## Scope
Applies to all generated code folders under `skills/`, skill packages, and import managers inside the Tool execution engine.

## SDK Manifest Schema
Every skill must be packaged inside its own folder, containing a JSON manifest named `manifest.json`. The schema is defined below:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SkillManifest",
  "type": "OBJECT",
  "properties": {
    "name": { "type": "STRING", "pattern": "^[a-z0-9_-]+$" },
    "display_name": { "type": "STRING" },
    "version": { "type": "STRING", "pattern": "^\\d+\\.\\d+\\.\\d+$" },
    "description": { "type": "STRING" },
    "entry_point": { "type": "STRING", "default": "main.py" },
    "dependencies": { "type": "ARRAY", "items": { "type": "STRING" } },
    "permissions": {
      "type": "ARRAY",
      "items": { "type": "STRING", "enum": ["network", "file_read", "file_write", "browser", "cli"] }
    },
    "signature": { "type": "STRING" }
  },
  "required": ["name", "display_name", "version", "entry_point", "permissions", "signature"]
}
```

### Folder Layout Standard
```
skills/
└── [skill_name]/
    ├── manifest.json
    ├── main.py
    ├── requirements.txt
    ├── README.md
    └── tests/
        └── test_main.py
```

### Main Class Hook Interface
The entry point file (e.g. `main.py`) must implement the standard `JarvisSkill` base class:
```python
class JarvisSkill:
    async def initialize(self) -> bool:
        """Runs setup tasks (database connection, client loads)."""
        pass
        
    async def execute(self, arguments: dict) -> dict:
        """Core execution point for tool call."""
        pass
        
    async def shutdown(self) -> bool:
        """Resource cleanup block."""
        pass
```

## Responsibilities
- **Developer Agent:** Must format all generated plugins to match this SDK layout and schema.
- **Reviewer Agent:** Rejects codebases that import third-party folders that do not match the SDK manifest parameters.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Base Class: `jarvis.sdk.skills.JarvisSkill`.

## Examples
- **Correct Manifest:**
```json
{
  "name": "youtube_downloader",
  "display_name": "YouTube Downloader",
  "version": "1.0.0",
  "entry_point": "main.py",
  "permissions": ["network", "file_write"],
  "signature": "8f3e2d...4a"
}
```
- **Incorrect Manifest:**
Manifest file is missing or has a display name but lacks the version and signature blocks. (Violates SDK Requirements).

## Failure Cases
- **Missing Entry Point:** The manifest specifies `run.py` but only `main.py` exists in the folder. *Mitigation:* The Skill Loader validates file existence before calling `initialize()`, flagging a missing entry point error and aborting installation.

## Security Considerations
- The manifest permissions field restricts what APIs are exposed to the skill sandbox. A skill that attempts to perform actions not declared in its permissions list is blocked by the Sandbox engine.

## Future Extension
- Modifications to the manifest schema or base class interfaces require updating this document and publishing a new SemVer release of the SDK.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [16_SKILL_SYSTEM.md](file:///e:/jarvis/docs/16_SKILL_SYSTEM.md)
- [52_PLUGIN_SDK_SPECIFICATION.md](file:///e:/jarvis/docs/52_PLUGIN_SDK_SPECIFICATION.md)
