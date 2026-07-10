# ADR-016: Electron Wrapper for Desktop Integration

## Status
* **Status:** Accepted
* **Date:** 2026-07-10 (migrated from legacy 06_ARCHITECTURE_DECISION_RECORDS.md ADR-05)
* **Original Date:** Phase 0 (Foundation)
* **Author:** Architecture Team
* **Migration Note:** Originally filed at `docs/06_ARCHITECTURE_DECISION_RECORDS.md` as "ADR-05: Electron Wrapper for Desktop Integration". Migrated to canonical Nygard format on 2026-07-10.

---

## Context

JARVIS requires desktop-side capabilities that web browsers deliberately block:

- **Native window control** — managing the desktop window stack (always-on-top, multi-monitor).
- **Mouse/keyboard listeners** — for PC automation (Phase 21: pyautogui-style control).
- **File system APIs** — beyond browser sandbox restrictions.
- **Native child processes** — launching local tools (browser runners, terminal automation).
- **System tray + global shortcuts** — for "always-on assistant" UX.
- **Notifications** — OS-native toasts and banners.

A pure-browser frontend cannot perform these actions. A native C++/Swift app duplicates effort across platforms and breaks the web-first UI stack (`frontend/` is Next.js).

---

## Decision

**Use Electron as a thin wrapper around the existing Next.js web frontend, providing a desktop application that can execute native child processes locally.**

Key decisions:

- **Electron version:** pinned to an LTS release (>= 28); updated quarterly.
- **Renderer = Next.js** — the existing web frontend is embedded via `BrowserWindow.loadURL`.
- **IPC isolation** — strict `contextBridge` exposure; no `nodeIntegration` in renderer.
- **Capabilities exposed** — only a narrow, audited surface (`window.jarvis.*` API): file dialog, tray, notifications, native clipboard, OS info.
- **No `remote` module** — disabled.
- **CSP enforced** — strict Content-Security-Policy in renderer.
- **Native child processes** — sandboxed via Electron's helper process; arguments and env filtered.
- **Auto-update** — Phase 46 plan; out of scope for this ADR.

---

## Consequences

### Positive

- **Cross-platform** — Windows, macOS, Linux from one codebase.
- **Web stack reuse** — Next.js frontend unchanged; gains desktop features incrementally.
- **Mature ecosystem** — battle-tested by VS Code, Slack, Discord, Notion.
- **Native APIs accessible** — without writing C++/Swift modules per platform.

### Negative

- **Larger binary** — Electron runtime is ~150MB per platform installer.
- **Memory overhead** — Chromium + Node.js + Next.js = ~250-400MB RAM at idle.
- **Security surface** — Electron's API is large; misconfiguration can lead to RCE. Tight CSP + IPC isolation is mandatory.
- **Slower cold start** — ~2-3s vs <1s for a native app.

### Risks

- **Electron security CVEs** — mitigated by allowing only audited APIs and pinning to LTS.
- **Renderer-level XSS escaping the sandbox** — mitigated by CSP + `contextIsolation: true` and disabling `nodeIntegration`.

---

## Compliance & Invariants

- `nodeIntegration` MUST be `false` in all renderer processes.
- `contextIsolation` MUST be `true`.
- `sandbox` MUST be `true` where possible.
- IPC handlers MUST validate inputs against Pydantic-equivalent Zod schemas on both renderer and main sides.
- All native API calls MUST go through the audited `window.jarvis.*` bridge.
- Electron version MUST be pinned in `package.json` (no `^` or `~`).

---

## Related

- `docs/20_BROWSER_ARCHITECTURE.md` — Chromium/Electron wrapper overlays
- `docs/21_PC_AUTOMATION_ARCHITECTURE.md` — PC automation layer
- `docs/26_SECURITY_CONSTITUTION.md` — desktop security policy
- `docs/29_SECRET_MANAGEMENT.md` — local credential vaults (Electron safeStorage)
- Phase 21 spec — PC automation runtime

---

## References

- Original entry: `docs/06_ARCHITECTURE_DECISION_RECORDS.md` ADR-05 (preserved for audit trail)
- Migration record: `.audit/CLEANUP_REPORT.md` (Phase E — 2026-07-10)
