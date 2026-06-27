# 10_REPOSITORY_LAYOUT_FREEZE.md

## Purpose
This document freeze-locks the physical repository directory layout of JARVIS OS to prevent agents or developers from spawning files or folders in arbitrary locations.

## Scope
Applies to all files, directories, sub-packages, and configuration entries in the workspace.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## Repository Structure (Frozen)
The following directory tree is locked. No new top-level directories may be created:

```
jarvis-os/
├── core/                  # Core Brain and engine packages
│   ├── brain/             # Planner and reasoning engine
│   ├── memory/            # Postgres, Redis, and PgVector adapters
│   ├── security/          # Vaults, sandboxing, and signers
│   └── tools/             # Built-in tool wrappers
├── skills/                # Dynamic plugins
├── browser/               # Electron frontend custom browser
├── pc/                    # pyautogui and shell adapters
├── api/                   # FastAPI routing endpoints
├── frontend/              # Next.js web application
├── desktop/               # Electron main wrapper
├── docs/                  # System specs and constitution (Phase 0)
│   └── architecture/      # Phase 0.5 architecture freeze files
├── tests/                 # Unit, Integration, and Regression tests
├── .env.example           # Variables template
└── requirements.txt       # Python dependencies
```

## Responsibilities
- **Developer Agent:** Must place files strictly inside this structure.
- **Reviewer Agent:** Scans PR changes and rejects modifications that add undocumented files or directories outside this layout.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- File system access API.

## Examples
- **Correct File Save:** Saving a custom scraper module to `skills/web_scraper/main.py`.
- **Incorrect File Save:** Creating a scratch folder `/scratch_temp/` in the root workspace folder. (Violates Repository structure rules).

## Failure Cases
- **Dynamic File Pollutions:** An agent writes debugging log dumps to the root directory. *Mitigation:* The Quality Gates check for stray files in the root folder during CI/CD checks and fail the build if any are found.

## Security Considerations
- Restricting folder structures ensures that files containing secret parameters or key files cannot be written outside the secure, git-ignored directories.

## Future Extension
- Modifying this directory layout requires updating this document via ADR approval.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [31_FOLDER_STRUCTURE_STANDARD.md](file:///e:/jarvis/docs/31_FOLDER_STRUCTURE_STANDARD.md)
- [01_ARCHITECTURE_FREEZE.md](file:///e:/jarvis/docs/architecture/01_ARCHITECTURE_FREEZE.md)
