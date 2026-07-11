# 79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 18: Dynamic Skill Framework**. It defines how JARVIS OS discovers, downloads, validates, sandboxes, signs, installs, registers, and executes extensible skill packages — transforming the platform from a fixed toolset into an installable-capability operating system.

## Status
**STATUS:** FROZEN  
**Authority:** Rank 4 (Phase Specification)  
**Dependencies:** Phases 1–17 (FROZEN)  
**Freeze Date:** 2026-06-30  
**Implementation:** COMPLETE (M0–M11, 443 tests passing)  
**Freeze Report:** `PHASE18_FREEZE_REPORT.md`

---

## 2. Scope & Boundaries

### In Scope
- End-to-end skill lifecycle: search → download → validate → sandbox test → permission review → sign → install → registry → planner availability.
- Skill DTOs, validator, repository, registry, downloader, sandbox runner, permission engine integration, signer, installer orchestrator.
- REST API under `/api/v1/skills/*` and CLI under `jarvis skill *`.
- EventBus telemetry for every lifecycle transition.
- Integration with frozen `ToolRegistry`, `PermissionGatekeeper`, and `ExecutionOrchestrator`.

### Out of Scope (Non-Goals)
- ❌ Remote skill marketplace UI (Phase 26 Frontend).
- ❌ Automatic skill code generation by LLM (future Learning Engine extension).
- ❌ Modifying frozen Phase 1–17 core execution loops without CR.
- ❌ Hot-reloading production `core/` source code.
- ❌ Unsigned or un-sandboxed skill execution.

---

## 3. Architecture

```
                    User / Agent / CLI
                            │
                            ▼
              api/routes/skills.py  (Phase 18 — NEW)
                            │
                            ▼
              SkillInstaller (Orchestrator — coordinates only)
         ┌──────────┬──────────┬──────────┬──────────┐
         ▼          ▼          ▼          ▼          ▼
   SkillDownloader SkillValidator SandboxRunner PermissionGatekeeper
         │          │          │          │
         ▼          ▼          ▼          ▼
   SkillSigner   SkillRepository   ToolRegistry (frozen extend)
         │                              │
         ▼                              ▼
   skills/ directory            ExecutionOrchestrator (frozen)
```

**Dependency direction (frozen):** `api/ → core/skills/ → core/tools/`. `core/` MUST NOT import `api/`.

**DTO-First build order:** DTO → Validator → Repository → Registry → Downloader → Sandbox → Signer → Installer → API → CLI → Tests.

---

## 4. Skill Lifecycle (Frozen Pipeline)

Every skill installation MUST follow this exact sequence. No step may be skipped or reordered.

```text
Search Skill
        │
        ▼
Download
        │
        ▼
Manifest Validation
        │
        ▼
Dependency Check
        │
        ▼
Security Scan
        │
        ▼
Docker Sandbox Test
        │
        ▼
Permission Review
        │
        ▼
Signature Verify
        │
        ▼
Install
        │
        ▼
Registry
        │
        ▼
Available to Planner
```

### Lifecycle States (`SkillInstallState`)
| State | Description |
|-------|-------------|
| `SEARCHING` | Querying local and remote catalogs |
| `DOWNLOADING` | Fetching skill package archive |
| `VALIDATING` | Manifest, dependency, and version checks |
| `SCANNING` | Static security vulnerability scan |
| `SANDBOXING` | Docker test execution |
| `AWAITING_APPROVAL` | Human gatekeeper clearance (L2/L3 permissions) |
| `SIGNING` | Cryptographic signature verification |
| `INSTALLING` | Writing to `skills/` and database |
| `REGISTERED` | Available in `ToolRegistry` |
| `FAILED` | Terminal failure with `failure_code` |
| `REMOVED` | Uninstalled / deactivated |

### 4.1 Lifecycle State Machine (immutable)

The canonical lifecycle progression for Phase 18 is frozen as:

```text
DISCOVERED
    ↓
DOWNLOADED
    ↓
VERIFIED
    ↓
SANDBOX_TESTED
    ↓
APPROVED
    ↓
INSTALLED
    ↓
ACTIVE
    ↓
DISABLED
    ↓
REMOVED
```

`SkillInstallState` is the internal orchestrator enum; this state machine is the external product-level contract. Implementations MUST maintain a deterministic mapping between both representations.

### 4.2 State Transition Telemetry

Every state transition MUST publish an EventBus event with `{skill_id, from_state, to_state, timestamp, trace_id}`.

---

## 5. Manifest

Every skill package MUST contain `manifest.json` conforming to `docs/17_SKILL_SDK_SPEC.md` and the extended Phase 18 schema:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Lowercase identifier `^[a-z0-9_-]+$` |
| `display_name` | Yes | Human-readable label |
| `version` | Yes | SemVer `X.Y.Z` |
| `entry_point` | Yes | Default `main.py` |
| `permissions` | Yes | Declared capability scopes |
| `dependencies` | No | Python package requirements |
| `signature` | Yes | SHA-256 package signature |
| `checksum` | Yes | SHA-256 archive checksum |
| `jarvis_api_version` | Yes | Compatible JARVIS API version |
| `min_runtime_version` | Yes | Minimum OS runtime version |
| `approval_level` | Yes | `L0`–`L3` per `docs/27_PERMISSION_SYSTEM.md` |
| `sandbox_policy` | Yes | Docker resource limits reference |
| `capabilities` | Yes | Planner-searchable capability list |
| `trust_level` | Yes | `OFFICIAL`, `VERIFIED`, `COMMUNITY`, `LOCAL` |

### 5.1 Skill Package Standard (immutable for Phase 18)

Before M0 implementation, the package contract is frozen as follows:

| Path | Required | Purpose |
|------|----------|---------|
| `manifest.json` | Yes | Canonical metadata and compatibility contract |
| `main.py` | Yes | Skill entrypoint implementation |
| `requirements.txt` | Yes | Runtime dependencies |
| `README.md` | Yes | Usage, setup, and constraints |
| `permissions.yaml` | Yes | Human-readable permission declaration and rationale |
| `tests/test_main.py` | Yes | Sandbox-verifiable behavior tests |
| `docs/` | No | Optional skill-specific documentation |
| `icon.png` | No | Optional UI metadata asset |

**Canonical format rule:** For Phase 18, `manifest.json` is authoritative. A package containing only `manifest.yaml` is invalid unless a future CR updates this contract.

### 5.2 Immutable Manifest Minimum Fields

The following fields are mandatory and frozen for compatibility:

| Field | Mapping | Notes |
|-------|---------|-------|
| `id` | unique skill ID | immutable package identifier |
| `name` | display name slug | aligns with `name` constraints |
| `version` | SemVer | upgrade/rollback key |
| `author` | publisher identity | audit provenance |
| `description` | summary | searchable metadata |
| `entrypoint` | runtime entry function | maps to `entry_point` |
| `permissions` | required scopes | gatekeeper + approval routing |
| `dependencies` | runtime deps | allowlist validation |
| `signature` | package signature | trust verification |
| `min_runtime_version` | runtime floor | forward/backward compatibility |
| `capabilities` | planner contract | explicit actions this skill provides |
| `trust_level` | risk tier | controls default planner selection policy |

### 5.4 Skill Compatibility Matrix (immutable)

Every manifest MUST declare compatibility boundaries for platform/runtime enforcement.

```json
{
  "platforms": ["windows", "linux"],
  "architectures": ["x64", "arm64"],
  "python": ">=3.11",
  "jarvis_runtime": ">=0.8"
}
```

Compatibility enforcement rules:
1. Installer MUST reject unsupported OS/platform values.
2. Installer MUST reject unsupported architecture values.
3. Installer MUST reject Python/runtime mismatches before sandbox start.
4. Compatibility check result MUST be persisted in install metadata.

### 5.3 Skill Capability Contract (immutable)

Capability discovery is contract-based, not name-based. The Planner MUST search by capability key and map to eligible skills via registry metadata.

| Field | Type | Rule |
|-------|------|------|
| `capabilities` | `list[str]` | Required, non-empty, unique entries |
| Capability format | dotted namespace | `domain.resource.action` |
| Example | string | `github.repo.clone`, `docker.image.build`, `youtube.video.search` |

Example:
```json
{
  "id": "youtube",
  "capabilities": [
    "youtube.video.search",
    "youtube.video.download",
    "youtube.playlist.read"
  ]
}
```

**Separation rule (frozen):**
- Capability = what the skill can do.
- Permission = what resources the skill may access.

Both MUST be declared; neither implies the other.

### Folder Layout (frozen)
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

---

## 6. DTOs

All DTOs are immutable Pydantic models (`frozen=True`).

| DTO | Location | Purpose |
|-----|----------|---------|
| `SkillManifest` | `core/skills/dto.py` | Parsed manifest (extends frozen `core/tools/base.py`) |
| `SkillInstallRequest` | `api/dto.py` | `{skill_name, source_url?, version?, force?}` |
| `SkillInstallResult` | `api/dto.py` | `{skill_id, name, version, state, installed_at}` |
| `SkillMetadata` | `core/skills/dto.py` | Registry record: status, permissions, version history |
| `SkillSearchQuery` | `api/dto.py` | `{query, source?, limit?, offset?}` |
| `SkillSearchResult` | `api/dto.py` | Paginated skill catalog entries |
| `SkillRemoveRequest` | `api/dto.py` | `{skill_name, purge?}` |
| `SkillUpdateRequest` | `api/dto.py` | `{skill_name, target_version?}` |

---

## 7. Validation (`SkillValidator`)

**Responsibility:** Schema, permission, dependency, and version validation ONLY. No DB writes, no execution.

Checks:
1. Manifest schema compliance (Pydantic + JSON Schema).
2. Permission declarations are valid enum values.
3. Declared dependencies pass allowlist scan (`docs/18_TOOL_EXECUTION_POLICY.md`).
4. Version compatibility with `ToolRegistry.SYSTEM_API_VERSION`.
5. No circular dependency with installed skills.
6. Checksum matches downloaded archive.

Raises `SkillValidationError` with codes `SKILL_V001`–`SKILL_V099`.

---

## 8. Repository (`SkillRepository`)

**Responsibility:** CRUD + transactions ONLY. No business logic.

Tables (extend shared `Base` in `core/memory/models.py`):

### `installed_skills`
| Column | Type | Description |
|--------|------|-------------|
| `id` | `Uuid` | PK |
| `name` | `String(100)` | Unique skill name |
| `version` | `String(20)` | Installed SemVer |
| `status` | `String(30)` | `REGISTERED`, `DISABLED`, `REMOVED` |
| `manifest_json` | `JSONB` | Frozen manifest snapshot |
| `checksum` | `String(64)` | SHA-256 |
| `signature` | `String(255)` | Package signature |
| `approval_level` | `String(5)` | L0–L3 |
| `installed_at` | `DateTime` | UTC timestamp |
| `updated_at` | `DateTime` | UTC timestamp |

### `skill_versions`
Version history per skill (append-only audit trail).

---

## 9. Registry (`SkillRegistry`)

Extends frozen `core/tools/registry.py` `ToolRegistry`:

- **Local catalog:** Installed skills from `skills/` + database.
- **Remote catalog:** Configurable skill index URL (read-only HTTP).
- **Search:** Name, tag, and permission-scope queries.
- **Update check:** Compare installed vs remote latest version.

`ToolRegistry.load_skill_manifest()` remains the runtime entry point. Phase 18 adds install-time registration without modifying frozen signature verification logic.

---

## 9.1 Skill Dependency Resolution Policy (immutable)

Dependencies are declared and resolved before sandbox execution.

Schema:
```json
"dependencies": [
  { "skill": "browser", "version": ">=1.2.0" }
]
```

Resolution rules:
1. Installer MUST resolve transitive skill dependencies before install.
2. Version constraints MUST use SemVer comparator syntax.
3. Circular dependencies MUST fail validation (`SKILL_V005` reserved).
4. Missing dependency MAY trigger auto-install only for trust levels `OFFICIAL` or `VERIFIED`; otherwise require explicit approval.
5. Dependency resolution results MUST be persisted in `skill_versions` metadata for reproducibility.

---

## 10. Installer (`SkillInstaller`)

**Responsibility:** Orchestrate lifecycle steps. Never perform CRUD directly — delegates to Repository, Validator, Sandbox, Signer.

Operations:
- `install(request) → SkillInstallResult`
- `remove(name) → bool`
- `update(name, version?) → SkillInstallResult`
- `rollback(name, target_version) → SkillInstallResult` (on failed upgrade)

Rollback policy: If post-install sandbox re-test fails, restore previous version from `skill_versions` history.

### 10.1 Update and Rollback Policy (immutable)

Canonical flow:

```text
v1.2
  ↓ update
v1.3
  ↓ failure
automatic rollback
  ↓
v1.2 ACTIVE
```

Rules:
1. Installer MUST keep previous active version until new version reaches `ACTIVE`.
2. On validation/sandbox/activation failure, rollback MUST be automatic and deterministic.
3. Rollback event and failure reason MUST be persisted in `skill_versions`.
4. Partial installs MUST never leave ambiguous active state.

---

## 11. Downloader (`SkillDownloader`)

- Download skill ZIP from `source_url` or remote catalog.
- Verify archive checksum (SHA-256).
- Extract to staging directory (`/tmp/jarvis-skills-staging/`).
- Enforce max package size (default 50 MB).
- Timeout: 120 seconds.

Raises `SkillDownloadError` codes `SKILL_D001`–`SKILL_D099`.

### 11.1 Marketplace Contract (immutable, provider-agnostic)

Although marketplace implementation is out of scope for Phase 18 UI, the integration contract is frozen now to avoid backend breaking changes later.

Required marketplace metadata contract:
- Search
- Download URL
- Skill metadata
- Publisher identity
- Rating/reputation metadata
- Signature payload
- Trust tier

Minimal search response shape:
```json
{
  "id": "youtube",
  "name": "YouTube Skill",
  "publisher": "jarvis-official",
  "rating": 4.8,
  "signature": "<sig>",
  "trust_level": "OFFICIAL",
  "download_url": "https://..."
}
```

---

## 12. Sandbox (`SandboxTestRunner`)

Uses frozen `core/tools/sandbox.py` Docker executor:

| Constraint | Default |
|------------|---------|
| CPU limit | 1 core |
| Memory limit | 512 MB |
| Timeout | 60 seconds |
| Network | Denied unless manifest requests `network` |
| Mounts | Staging dir read-only |

Runs `tests/test_main.py` inside container. Failure → `FAILED` state, no install.

### 12.1 Skill Resource Limits (immutable)

Resource limits are manifest-driven and enforced by sandbox runtime:

```json
{
  "limits": {
    "memory": "512MB",
    "cpu": "1",
    "timeout": 60,
    "network": true,
    "filesystem": "sandbox"
  }
}
```

Rules:
1. Sandbox MUST read limits from manifest and enforce hard ceilings.
2. Manifest limits MAY be stricter than defaults, never looser than global security policy.
3. Any limit violation MUST terminate execution and emit failure telemetry.

### 12.2 Skill Isolation Policy (immutable)

Execution isolation modes:

```text
process
container
vm (future)
```

Rules:
1. Default isolation mode for Phase 18 is `container`.
2. A skill MUST NOT directly access another skill's memory/state.
3. Inter-skill communication MUST occur through EventBus contracts only.
4. Any request for weaker isolation than `container` is invalid in Phase 18.

### 12.3 Skill Storage Policy (immutable)

Allowed writable paths per skill:

```text
/skills/<id>/
/data/<skill>/
/cache/<skill>/
/logs/<skill>/
```

Forbidden paths:

```text
core/
api/
docs/
```

Rules:
1. Sandbox MUST enforce path allowlist and block forbidden writes.
2. Skill runtime MUST treat filesystem outside allowlist as read-denied.
3. Violations MUST emit security telemetry and fail execution.

---

## 13. Permission Engine

Integrates frozen `PermissionGatekeeper` (`core/tools/security.py`):

| Permission | Gate |
|------------|------|
| `filesystem` | L1+ for `file_read`/`file_write` |
| `browser` | L2+ |
| `network` | L2+ |
| `clipboard` | L2+ |
| `shell` | L3 + human approval |
| `desktop` | L3 + human approval |

Skills declaring L2/L3 permissions enter `AWAITING_APPROVAL` until gatekeeper clears via EventBus `skill.approval.waiting` → `skill.approval.granted`.

---

## 14. Signing (`SkillSigner`)

- Verify SHA-256 signature against Security Agent public key.
- Recompute directory hash via `PermissionGatekeeper.calculate_directory_hash()`.
- Reject tampered packages (signature mismatch → `SKILL_S001`).
- No unsigned skill may reach `REGISTERED` state.

Policy authority: `docs/68_PLUGIN_TRUST_POLICY.md`.

### 14.1 Certificate Chain Validation (immutable)

Signature validation is chain-based, not signature-only:

```text
Jarvis Root Certificate
    ↓
Marketplace/Publisher Certificate
    ↓
Skill Signature
```

Validation sequence:
1. Verify skill signature against publisher certificate.
2. Verify publisher certificate against trusted chain/root.
3. Verify certificate validity window and revocation status.
4. Only then allow install/activation.

If any chain step fails, installation MUST fail with signing/trust error.

---

## 15. API Endpoints

All endpoints require authentication (Phase 17). Wrapped in frozen success/error envelopes.

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| `POST` | `/api/v1/skills/install` | `skill.install` | Install skill package |
| `POST` | `/api/v1/skills/remove` | `skill.remove` | Uninstall skill |
| `POST` | `/api/v1/skills/update` | `skill.update` | Upgrade skill version |
| `GET` | `/api/v1/skills` | `skill.read` | List installed skills |
| `GET` | `/api/v1/skills/search` | `skill.read` | Search local + remote catalog |
| `GET` | `/api/v1/skills/{id}` | `skill.read` | Skill metadata detail |

---

## 16. CLI

Command group: `jarvis skill` (extends `audit/cli.py` pattern).

```bash
jarvis skill install youtube
jarvis skill remove youtube
jarvis skill search notion
jarvis skill update youtube
jarvis skill list
```

CLI calls the same `SkillInstaller` orchestrator as the API — no duplicate business logic.

---

## 17. Security

Every skill MUST have:
- Valid `manifest.json`
- SHA-256 `checksum`
- SHA-256 `signature`
- Explicit `permissions` declaration
- SemVer `version`
- Declared `dependencies` (allowlist-scanned)
- `sandbox_policy` compliance
- `approval_level` gate

**Invariant:** No unsigned skill executes. Unsigned imports blocked at `ToolRegistry.load_skill_manifest()`.

**Invariant:** `SkillRepository` = CRUD only. No validation or execution logic.

**Invariant:** `SkillInstaller` coordinates; never writes DB directly.

New permission scopes (seeded by `SecuritySeedService`):
- `skill.install`, `skill.remove`, `skill.update`, `skill.read`

---

## 17.1 Skill Trust Model (immutable)

Each skill is classified by trust tier:

| Trust Level | Meaning | Default Planner Policy |
|-------------|---------|------------------------|
| `OFFICIAL` | First-party signed and maintained | Preferred for production tasks |
| `VERIFIED` | Third-party reviewed and signed | Allowed for medium-risk tasks |
| `COMMUNITY` | Community-provided, minimally reviewed | Disallow for high-risk tasks by default |
| `LOCAL` | User-local development skill | Require explicit user intent for non-dev tasks |

Planner selection rules:
1. High-risk workflows MUST prefer `OFFICIAL`/`VERIFIED` skills.
2. `COMMUNITY`/`LOCAL` skills require higher approval threshold for privileged permissions.
3. Trust level MUST be visible in API and CLI list/search responses.

---

## 18. Events (EventBus Telemetry)

| Event | When |
|-------|------|
| `skill.download.started` | Download begins |
| `skill.download.completed` | Archive verified and extracted |
| `skill.validation.failed` | Validator rejects package |
| `skill.sandbox.started` | Docker test container launched |
| `skill.sandbox.failed` | Sandbox tests fail |
| `skill.approval.waiting` | L2/L3 permission requires human gate |
| `skill.approval.granted` | Gatekeeper approves install |
| `skill.installed` | Successfully registered |
| `skill.updated` | Version upgrade complete |
| `skill.removed` | Skill uninstalled |

### 18.2 Telemetry Contract (immutable event names)

The following event names are frozen and MUST remain stable for dashboard/analytics compatibility:

- `skill.search.started`
- `skill.download.started`
- `skill.download.completed`
- `skill.validation.failed`
- `skill.signature.failed`
- `skill.sandbox.started`
- `skill.sandbox.failed`
- `skill.installed`
- `skill.removed`
- `skill.updated`

Event payload minimum fields:
- `skill_id`
- `skill_name`
- `state`
- `timestamp`
- `trace_id`
- `result` (`success`/`failure`)

---

## 18.1 Skill API Versioning Policy (immutable)

To ensure forward/backward compatibility across hundreds of skills, Phase 18 freezes the following versioning contract:

| Field | Contract | Rule |
|-------|----------|------|
| `jarvis_api_version` | `MAJOR.MINOR` | Declares skill SDK/API compatibility target |
| `min_runtime_version` | `MAJOR.MINOR` | Lowest runtime allowed to execute skill |
| `version` | `MAJOR.MINOR.PATCH` | Skill package semantic version |

### Compatibility Rules
1. Runtime MUST reject a skill when `jarvis_api_version.major` does not match the runtime API major.
2. Runtime MUST reject a skill when runtime version is lower than `min_runtime_version`.
3. Runtime SHOULD allow `MINOR` drift when backward compatibility is preserved by the SDK contract.
4. `PATCH` upgrades MUST NOT alter manifest field semantics or permission meaning.
5. Any breaking schema or execution-contract change requires major bump and a CR update to this spec.

### Upgrade Policy
- **Patch upgrade (`X.Y.Z -> X.Y.Z+1`)**: bugfix/security-only, auto-eligible.
- **Minor upgrade (`X.Y -> X.Y+1`)**: additive capability, requires sandbox re-test.
- **Major upgrade (`X -> X+1`)**: breaking change, blocked by default until explicit approval and migration notes.

### Version Enforcement Points
| Layer | Enforcement |
|-------|-------------|
| `SkillValidator` | Validates version format and compatibility |
| `SkillInstaller` | Blocks incompatible installs/upgrades |
| `ToolRegistry` | Refuses activation when runtime contract is not met |
| API (`/skills/install`, `/skills/update`) | Returns deterministic version mismatch error |

---

## 19. Error Codes

| Code | Meaning |
|------|---------|
| `SKILL_V001` | Invalid manifest schema |
| `SKILL_V002` | Unsupported permission declaration |
| `SKILL_V003` | Dependency not on allowlist |
| `SKILL_V004` | API version mismatch |
| `SKILL_D001` | Download timeout |
| `SKILL_D002` | Checksum mismatch |
| `SKILL_S001` | Signature verification failed |
| `SKILL_S002` | Unsigned package rejected |
| `SKILL_I001` | Install rollback triggered |
| `SKILL_I002` | Skill already installed (use `force`) |
| `SKILL_I008` | Skill package not found at expected path (route pre-check) |
| `SKILL_P001` | Insufficient approval level |

---

## 20. Milestones

| Milestone | Component | Gate |
|-----------|-----------|------|
| **M0** | Skill DTOs (`SkillInstallRequest`, `SkillInstallResult`, `SkillMetadata`) | ruff + mypy + unit |
| **M1** | `SkillValidator` | validator unit tests |
| **M2** | `SkillRepository` | CRUD tests, no business logic |
| **M3** | `SkillRegistry` (extend `ToolRegistry`) | search + load tests |
| **M4** | `SkillDownloader` | download + checksum tests |
| **M5** | `SandboxTestRunner` | Docker integration test |
| **M6** | Permission engine wiring | L0–L3 gate tests |
| **M7** | `SkillSigner` | signature verify tests (100% security) |
| **M8** | `SkillInstaller` | end-to-end install/rollback test |
| **M9** | API routes (`api/routes/skills.py`) | route integration tests |
| **M10** | CLI (`jarvis skill *`) | CLI smoke tests |
| **M11** | Full gate + freeze | 100% security coverage, ≥95% logic, audit pass |

Each milestone emits `AGENTS.md` §10 MILESTONE REPORT and stops for approval.

---

## 20.1 Phase 18 Freeze Readiness Checklist

All items MUST be complete before setting `STATUS: FROZEN`.

- [ ] Package Standard frozen
- [ ] Manifest Specification frozen
- [ ] Compatibility Matrix frozen
- [ ] Capability Contract frozen
- [ ] API Versioning Policy frozen
- [ ] Lifecycle State Machine frozen
- [ ] Dependency Resolution Policy frozen
- [ ] Trust Model frozen
- [ ] Resource Limits frozen
- [ ] Signing + Certificate Chain model frozen
- [ ] API contract frozen
- [ ] CLI contract frozen
- [ ] Event contracts frozen
- [ ] DTO contract frozen
- [ ] Test strategy frozen
- [ ] Security invariants frozen

Governance lock:
- Spec evolution should stop at freeze gate.
- Post-freeze architecture-level changes require CR process only.

---

## Architecture Invariants

| # | Invariant |
|---|-----------|
| I1 | No unsigned skill executes |
| I2 | `SkillRepository` = CRUD only |
| I3 | `SkillValidator` never writes DB or executes tools |
| I4 | `SkillInstaller` orchestrates only — delegates all I/O |
| I5 | `api/ → core/skills/ → core/tools/` layer direction preserved |
| I6 | CLI and API share single `SkillInstaller` instance |
| I7 | Sandbox runs before every install and upgrade |
| I8 | L2/L3 skills require human approval by default |

---

## Version Roadmap Alignment

| Product Version | Phases | Capability |
|-----------------|--------|------------|
| **JARVIS v0.5** | 1–17 | Core backend + security (current) |
| **JARVIS v0.8** | 18–21 | Skills + Memory + Browser + PC |
| **JARVIS v1.0** | 22–27 | Multi-Agent + Voice + Vision + Desktop + Production |

Phase 18 is the **turning point** from static backend to extensible OS.

---

## Related Documents
- [16_SKILL_SYSTEM.md](file:///e:/jarvis/docs/16_SKILL_SYSTEM.md)
- [17_SKILL_SDK_SPEC.md](file:///e:/jarvis/docs/17_SKILL_SDK_SPEC.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [27_PERMISSION_SYSTEM.md](file:///e:/jarvis/docs/27_PERMISSION_SYSTEM.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
- [68_PLUGIN_TRUST_POLICY.md](file:///e:/jarvis/docs/68_PLUGIN_TRUST_POLICY.md)
- [78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md](file:///e:/jarvis/docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md)
- [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md)
