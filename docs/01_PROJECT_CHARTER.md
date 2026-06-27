# 01_PROJECT_CHARTER.md

## Purpose
This document establishes the project charter, mission, and scope boundaries for JARVIS OS. It outlines the core organizational objective: building a production-grade, highly autonomous AI Operating System (AI Employee) rather than a chatbot.

## Scope
Includes all system capabilities, architectural modules, and deployment plans for the JARVIS OS ecosystem. It defines what features are in-scope and explicitly maps out-of-scope items to prevent feature creep.

## Core Charter & Mission
- **Mission:** Empower developers and enterprises with a digital worker capable of autonomous goal planning, reasoning, tool execution, memory indexing, and self-improvement inside a secure sandbox.
- **Goal:** Reach a fully autonomous operational loop where JARVIS OS can receive high-level targets, break them down into modular tasks, write and test code, run local/web automations, and debug runtime failures without constant human hand-holding.
- **In-Scope:**
  - Multi-agent swarm orchestration.
  - Hybrid memory (Working, Session, Long, Vector DB, Knowledge Graph).
  - Custom browser execution shell and external browser control.
  - Sandboxed tool calling and PC terminal control.
  - Runtime self-healing and code patching.
- **Out-of-Scope:**
  - Standard chat-based question answering (unless used as a system debug input).
  - Unsupervised execution of destructive actions on host hardware (requires human approval, see `27_PERMISSION_SYSTEM.md`).

## Responsibilities
- **Project Sponsor (User):** Defines target goals, approves ADRs, and issues permissions for high-risk operations.
- **AI Operating System (Core Agent):** Functions as the primary worker executing the plan backlog.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Input: User-defined goals via CLI, Web Dashboard, or WebSocket streams.
- Output: Execution telemetry logs, file modifications, browser session records, and task statuses.

## Examples
- **In-Scope Task:** "Automate checking daily marketing leads from email, scrape target sites, update lead sheets, and email summary."
- **Out-of-Scope Task:** "Provide a conversational essay about the Roman Empire."

## Failure Cases
- **Scope Creep:** System expands into general-purpose chat features. *Mitigation:* The system planner rejects prompts that do not map to autonomous task decomposition.

## Security Considerations
- This charter mandates human-in-the-loop validation for all external system calls or destructive terminal operations.

## Future Extension
- Charter updates are subject to revision through Architecture Decision Records (ADRs).

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [02_SYSTEM_VISION.md](file:///e:/jarvis/docs/02_SYSTEM_VISION.md)
- [03_PRODUCT_REQUIREMENTS.md](file:///e:/jarvis/docs/03_PRODUCT_REQUIREMENTS.md)
