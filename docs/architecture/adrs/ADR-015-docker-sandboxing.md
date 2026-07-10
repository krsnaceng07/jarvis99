# ADR-015: Docker Containers for Local Tool Sandboxing

## Status
* **Status:** Accepted
* **Date:** 2026-07-10 (migrated from legacy 06_ARCHITECTURE_DECISION_RECORDS.md ADR-04)
* **Original Date:** Phase 0 (Foundation)
* **Author:** Architecture Team
* **Migration Note:** Originally filed at `docs/06_ARCHITECTURE_DECISION_RECORDS.md` as "ADR-04: Docker Containers for Local Tool Sandboxing". Migrated to canonical Nygard format on 2026-07-10.

---

## Context

JARVIS OS executes untrusted code in many contexts:

- **Dynamic skill compilation** — Phase 18 skills are authored, tested, and run in isolation.
- **Code execution tools** — interpreter-style tools (`python_executor`, `shell_executor`) that take user/LLM-generated code.
- **Web scrapers** — third-party browsers (Phase 25) operate outside the trust boundary.
- **Browser sandbox** — headless Chromium instances.
- **Compilation sandboxes** — for plugin / skill SDK builds.

Host-OS execution would be catastrophic. Even VMs are too heavy for per-tool ephemeral use. We need:

- **Filesystem isolation** — restricted mounts.
- **Resource caps** — RAM, CPU, network.
- **Network policy** — allow/deny by tool capability.
- **Sub-second startup** — for ephemeral tool runs.
- **Disposable** — auto-removed after execution.

---

## Decision

**Use Docker containers for all tool sandboxing.**

Key decisions:

- **Local Docker Engine required** — `Docker Desktop` or `Docker Engine 24+` on the host.
- **Per-tool ephemeral container** — `docker run --rm` for each tool invocation.
- **Resource limits enforced** — `--memory`, `--cpus`, `--pids-limit` per the tool's profile.
- **Network namespaces** — `bridge` for general tools, `none` for tools that should not phone home.
- **Read-only root filesystem** — all tool containers run with `:ro`.
- **Volume mounts are explicit** — only declared in `tool.manifest.yaml` mounts block.
- **Image registry policy** — no `latest` tag; pinned digests; signature verification (Phase 18).
- **No privileged mode** — `--privileged` banned; capabilities granted individually when needed.

---

## Consequences

### Positive

- **Strong isolation** — separate kernel namespaces, capability drops, seccomp profiles.
- **Sub-second startup** for small images (Alpine ~200ms).
- **Disposable** — `docker run --rm` ensures no leftover state.
- **Reproducible** — pinned image digests guarantee identical env every run.
- **Audit-friendly** — `--log-driver json-file` produces per-tool execution audit trail.

### Negative

- **Requires Docker installed** — non-trivial on Windows (WSL2 backend), macOS (Docker Desktop license).
- **Daemon overhead** — `dockerd` consumes ~100MB idle RAM.
- **No GPU passthrough by default** — Phase 7 inference tools must request GPU explicitly.
- **Image storage** — large images accumulate; periodic prune required.

### Risks

- **Docker escape CVEs** — mitigated by pinning to latest stable engine + seccomp default profile.
- **Container escape via malicious image** — mitigated by digest pinning + signature verification.

---

## Compliance & Invariants

- All tool execution MUST run in a container; bare `subprocess` calls to user code are forbidden.
- Containers MUST be `--rm` (no leftovers).
- Resource limits MUST be specified in `tool.manifest.yaml`; missing limits = CI failure.
- Network mode MUST be explicit (`bridge`, `host`, or `none`); defaulting is forbidden.
- Image digests MUST be pinned; `:latest` is banned.
- All container lifecycle events MUST be logged to the audit stream.

---

## Related

- `docs/28_SANDBOX_POLICY.md` — sandbox network/mount/cap policies
- `docs/18_TOOL_EXECUTION_POLICY.md` — tool security gates
- `docs/68_PLUGIN_TRUST_POLICY.md` — skill verification
- `docs/26_SECURITY_CONSTITUTION.md` — STRIDE threat model for sandbox escapes
- Phase 18 spec — skill runtime isolation (more detail)
- Phase 25 spec — headless browser containers

---

## References

- Original entry: `docs/06_ARCHITECTURE_DECISION_RECORDS.md` ADR-04 (preserved for audit trail)
- Migration record: `.audit/CLEANUP_REPORT.md` (Phase E — 2026-07-10)
