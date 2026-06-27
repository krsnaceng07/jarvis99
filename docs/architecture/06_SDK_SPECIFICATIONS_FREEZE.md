# 06_SDK_SPECIFICATIONS_FREEZE.md

## Purpose
This document freeze-locks the Skill SDK and Browser SDK specifications, manifest parameters, process lifecycles, and class method signatures.

## Scope
Applies to all dynamically compiled plugins under `skills/`, browser driver interfaces, and loading gateways.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## SDK Specifications & Lifecycle (Frozen)

### 1. Skill SDK Manifest JSON Schema
```json
{
  "type": "object",
  "properties": {
    "name": { "type": "string", "pattern": "^[a-z0-9_-]+$" },
    "version": { "type": "string", "pattern": "^\\d+\\.\\d+\\.\\d+$" },
    "entry_point": { "type": "string" },
    "permissions": {
      "type": "array",
      "items": { "type": "string", "enum": ["network", "file_read", "file_write", "browser", "cli"] }
    },
    "signature": { "type": "string" }
  },
  "required": ["name", "version", "entry_point", "permissions", "signature"]
}
```

### 2. Browser SDK Client API Interface
The custom browser module exposes these exact automation methods:
- `Browser.open_tab(url: str) -> str`: Opens page and returns Tab ID.
- `Browser.click_element(tab_id: str, selector: str) -> bool`: Simulates click.
- `Browser.inject_js(tab_id: str, script: str) -> Any`: Injects custom JS.
- `Browser.get_cookies(tab_id: str) -> list[dict]`: Retrieves page cookies.

## Responsibilities
- **Developer Agent:** Instantiates skills and browser integrations matching these schemas.
- **Reviewer Agent:** Verifies manifest keys and blocks non-compliant tools.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Base class: `jarvis.sdk.skills.JarvisSkill`.
- Browser client: `jarvis.sdk.browser.JarvisBrowser`.

## Examples
- **Correct Integration:** Scraper skill imports `JarvisSkill`, defines execution handlers, and registers `manifest.json`.
- **Incorrect Integration:** A plugin attempts to access local file systems directly without declaring the `file_write` permission parameter in `manifest.json`. (Violates Permission and Sandbox isolation rules).

## Failure Cases
- **Signature Corruption:** The signature string in the manifest has been modified. *Mitigation:* The Skill Loader compares the sha256 checksum on load. If it fails, the skill is blocked and the warning is logged.

## Security Considerations
- Sandbox environments check declared permissions at runtime, shutting down container processes if unauthorized system calls occur.

## Future Extension
- Enhancements to the SDK schemas require ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [16_SKILL_SYSTEM.md](file:///e:/jarvis/docs/16_SKILL_SYSTEM.md)
- [17_SKILL_SDK_SPEC.md](file:///e:/jarvis/docs/17_SKILL_SDK_SPEC.md)
- [52_PLUGIN_SDK_SPECIFICATION.md](file:///e:/jarvis/docs/52_PLUGIN_SDK_SPECIFICATION.md)
