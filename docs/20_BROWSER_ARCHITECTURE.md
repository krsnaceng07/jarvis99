# 20_BROWSER_ARCHITECTURE.md

## Purpose
This document defines the Browser Architecture for JARVIS OS. It details the structure of the custom Electron Chromium wrapper (Jarvis Browser) and the protocols for existing browser automation.

## Scope
Applies to the custom browser UI components, Playwright overlay scripts, proxy configs, and DOM parsing tools.

## Browser Subsystem Layout
The browser system isolates the automated browser instance from the reasoning core, using a tool gateway to process actions safely:

```
[Planner / Agent Core]
        ↓ (JSON Command API)
[Browser Tool Adapter (Tool Layer)]
        ↓ (Playwright / CDP Protocol)
[Jarvis Browser Engine (Electron Wrapper)]
    ├─ [Proxy Server / Fingerprint Profiles]
    ├─ [Cookie Manager / Storage Vault]
    ├─ [OCR / Vision Parser Sidebar]
    └─ [Target Page (DOM Viewport)]
```

### Browser Automation Policies
1. **Decoupled Reasoning Interface:** The Planner Agent cannot communicate directly with the browser thread. All navigations, clicks, and script injections must route through the Browser Tool Adapter.
2. **Session & Fingerprint Isolation:** Each browser profile must maintain isolated cookies, session files, cache directories, and custom user-agent fingerprint profiles to mimic natural user interaction.
3. **Audit Logging:** Every navigation, cookie change, page reload, download request, and automated form submission must write a security log entry.

## Responsibilities
- **Browser Agent:** Runs the page DOM parser, translates agent clicks into coordinate-based events, and handles OCR element detection.
- **Security Auditor:** Validates that injected Javascript files do not contain shell exploit strings.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- REST API: `/api/v1/browser/` (e.g. `/open`, `/navigate`, `/click`, `/extract-dom`).
- WebSocket: `/ws/v1/browser/viewport` (streams base64 screenshot frames to the UI dashboard).

## Examples
- **Correct Execution Flow:** Core requests page title -> Browser Tool executes `page.title()` via CDP -> returns string payload to core.
- **Incorrect Execution Flow:** Core agent directly imports selenium and attempts to interact with local system browser window. (Violates Decoupled Reasoning Interface).

## Failure Cases
- **Page Load Hang / Timeout:** Scraped page triggers an infinite redirection loop or loads massive media assets. *Mitigation:* The browser engine enforces a hard page load timeout of 30 seconds and utilizes network proxy blocklists to filter video and advertisement trackers.

## Security Considerations
- The browser proxy restricts navigations to safe, validated domains unless explicitly overridden by the user. Downloads of executable files (e.g. `.exe`, `.sh`, `.bat`) are blocked by default.

## Future Extension
- Browser extension support and native proxy rotations are documented in the browser specifications.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [13_BROWSER_SYSTEM.md](file:///e:/jarvis/docs/13_BROWSER_SYSTEM.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
