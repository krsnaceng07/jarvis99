# 103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md

## Status
**STATUS:** ✅ FROZEN (2026-07-06)
**Test Count:** 60 passed (1215 total)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 40 (Event Bus & Reactive Architecture)
**Date:** 2026-07-06

---

## 1. Problem Statement

JARVIS OS needs to run external capabilities dynamically without redeploying the core repository. While the platform contains elements of dynamic loading, it lacks a unified, secure, version-controlled **Capability Registry & Skill Runtime** that decouples the execution planner from static tools.

Phase 41 introduces the centralized `CapabilityRegistry`. Instead of hardcoding tool mappings, the planner dynamically queries discoverable capabilities (e.g. `notion.page.create`), resolves SemVer version constraints, validates cryptographic signatures, resolves transitive dependencies, and schedules sandboxed executions within resource-controlled Docker subprocesses.

---

## 2. Architecture & Design

```text
       [ Planner / Agent Loop ]
                   │
                   ▼ (Queries)
      ============================
          CAPABILITY REGISTRY
      ============================
        ├─ [Capability Discovery API]
        └─ [Dynamic Skill Router]
                   │
                   ▼ (Installs & Schedules)
      ============================
          DYNAMIC SKILL RUNTIME
      ============================
        ├─ Downloader & Dependency Resolver
        ├─ Digital Signature Verifier (ECDSA / SHA-256)
        └─ Sandbox Execution Engine (Process / Docker)
```

---

## 3. Directory Layout

Pluggable capability extensions are organized cleanly under the core namespaces:

```text
core/skills/
  ├── capability_registry.py   # Global registry matching capability names to skills
  ├── dependency_resolver.py   # Resolves Python dependencies and skill-to-skill links
  ├── sandbox.py               # Sandboxed runtime (Docker constraints)
  ├── signer.py                # ECDSA public key signature verification
  └── installer.py             # Durable staging, installation, and rollbacks
```

---

## 4. Key Invariants

| # | Invariant |
|---|-----------|
| CR-1 | **Signature Enforcement**: Unsigned or tampered skill packages must be rejected. The system registry will never load capabilities failing signature checks. |
| CR-2 | **Sandbox Isolation**: Writable directories are isolated per skill. A running skill cannot read or write to another skill's workspace. |
| CR-3 | **Dependency Allowlist**: Transitive packages must pass the security allowlist check before resolution. |
| CR-4 | **Durable Rollback**: If a plugin fails validation tests during staging, the registry rollback mechanism must deterministically restore the previous version. |

---

## 5. Manifest Standard (`manifest.json`)

Every plugin manifest must structure its capabilities and permissions explicitly:

```json
{
  "id": "github-helper",
  "name": "github",
  "version": "1.2.0",
  "capabilities": [
    "github.repo.clone",
    "github.repo.fork"
  ],
  "permissions": [
    "network",
    "filesystem"
  ],
  "dependencies": [
    { "skill": "git-core", "version": ">=1.0.0" }
  ],
  "signature": "ecdsa-signature-hash",
  "min_runtime_version": "1.0.0"
}
```

---

## 6. Verification Plan

- **Registry Resolution Verification**: Verify that querying `github.repo.clone` dynamically resolves to the loaded plugin.
- **Rollback Audit**: Confirm that installing a corrupted update triggers a clean database and filesystem rollback.
- **Isolation Constraint Test**: Verify that executing a test container attempting to write outside allowed scopes is blocked by the Sandbox engine.
