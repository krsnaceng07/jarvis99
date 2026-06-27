# 31_FOLDER_STRUCTURE_STANDARD.md

## Purpose
This document defines the Folder Structure Standard for JARVIS OS. It establishes directory mappings, file layouts, and structural rules to prevent random file creation by agents.

## Scope
Applies to all files, modules, directories, assets, and libraries created in the JARVIS OS workspace.

## Folder Structure Mapping
The workspace follows a strict modular structure. Agents are forbidden from creating files outside this designated skeleton without approval:

```
jarvis-os/
├── core/                  # Core AI Brain, router, and engines
│   ├── brain/             # Reasoning and Planning modules
│   ├── memory/            # Postgres, Vector, and Graph adapters
│   ├── security/          # Sandbox controllers and key vaults
│   └── tools/             # Built-in execution tool drivers
├── skills/                # Dynamic plugins SDK directory
├── browser/               # Electron frontend custom browser source code
├── pc/                    # PC automation adapters (pyautogui, shell)
├── api/                   # FastAPI backend server modules
├── frontend/              # Next.js web application files
├── desktop/               # Electron main process wrapper
├── docs/                  # System specs and constitution (Phase 0)
├── scripts/               # CI/CD and auxiliary management scripts
├── tests/                 # Unit, Integration, and Regression tests
├── .env.example           # Variables template
└── requirements.txt       # Python dependencies manifest
```

## Responsibilities
- **Developer Agent:** Must place generated code and files in the designated folders.
- **Reviewer Agent:** Audits directory mapping and rejects code that violates this structure.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 1, Rule 5, and Rule 8).

## Interfaces
- Local file path validation checkers.

## Examples
- **Correct File Placement:** Adding a custom PostgreSQL wrapper file to `core/memory/postgres_client.py`.
- **Incorrect File Placement:** Placing a database helper script directly in the root workspace folder `jarvis-os/db_helper.py`. (Violates structural isolation).

## Failure Cases
- **Stray File Spawns:** An agent generates temporary files in the root folder during debugging. *Mitigation:* The Quality Gates run a check that raises errors if any undocumented files exist in the root folder during CI/CD.

## Security Considerations
- Directories containing sensitive code (e.g. `core/security/`) are protected by write-permissions. Developer agents cannot modify them directly without authorization.

## Future Extension
- Adding new top-level directories requires an ADR entry and human approval.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [07_FOLDER_STANDARDS.md](file:///e:/jarvis/docs/07_FOLDER_STANDARDS.md)
- [25_FOLDER_STRUCTURE.md](file:///e:/jarvis/docs/25_FOLDER_STRUCTURE.md)
- [47_QUALITY_GATES.md](file:///e:/jarvis/docs/47_QUALITY_GATES.md)
