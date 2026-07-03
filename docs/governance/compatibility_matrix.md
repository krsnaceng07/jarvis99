# Compatibility Matrix — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §7.6 (immutability of compiled objects, DTOs, Enums, frozen specs)
**Related:** DRG §3 (Q4: Upgrade path), Formal Interface Contract, Engineering Decision Log

---

## 1. Purpose

A Compatibility Matrix tracks **version compatibility** across all public components in the system. It is the source of truth for "can I upgrade component X without breaking component Y?"

**Rule:** Every public interface (DTO, Repository, Service, API endpoint, CLI command) MUST appear in a compatibility matrix. Versioning is mandatory. Backward-incompatible changes are forbidden without a CR.

---

## 2. When Compatibility Must Be Tracked

- Every Pydantic DTO with `schema_version` field.
- Every Repository interface (CRUD methods).
- Every Service interface (public methods).
- Every API endpoint (request/response shape).
- Every CLI command (arguments, output format).
- Every event topic (payload schema).

---

## 3. Compatibility Rules

| Change Type | Allowed? | Version Bump | Migration Required |
|---|---|---|---|
| **Add new field to DTO** (optional) | YES | MINOR (1.0 → 1.1) | No — old consumers ignore new field |
| **Add new method to Repository** | YES | MINOR (1.0 → 1.1) | No — old callers don't use it |
| **Add new event topic** | YES | MINOR (1.0 → 1.1) | No — subscribers register at runtime |
| **Remove field from DTO** | NO (without CR) | MAJOR (1.0 → 2.0) | Yes — all consumers must update |
| **Change field type in DTO** | NO (without CR) | MAJOR (1.0 → 2.0) | Yes — all consumers must update |
| **Remove method from Repository** | NO (without CR) | MAJOR (1.0 → 2.0) | Yes — all callers must update |
| **Rename event topic** | NO (without CR) | MAJOR (1.0 → 2.0) | Yes — all subscribers must update |
| **Change enum value semantics** | NO (without CR) | MAJOR (1.0 → 2.0) | Yes — all consumers must update |
| **Add new enum value (additive)** | YES | MINOR (1.0 → 1.1) | No — switch statements need a default case |

**Rule of thumb:** Additive changes = MINOR bump. Destructive changes = MAJOR bump + CR + migration plan.

---

## 4. Compatibility Matrix Template

Filed as `CM-YYYY-NNN-<subsystem>.md` in `docs/compatibility/`.

```markdown
# CM-YYYY-NNN — <Subsystem> Compatibility Matrix

**Status:** ACTIVE
**Date:** YYYY-MM-DD
**Owner:** <subsystem lead>

## Components

| Component | Current Version | Released | Owner |
|---|---|---|---|
| <DTO> | 1.0 | YYYY-MM-DD | <name> |
| <Validator> | 1.0 | YYYY-MM-DD | <name> |
| ... | ... | ... | ... |

## Compatibility Map

| Consumer → Producer | DTO v1.0 | DTO v1.1 (planned) | DTO v2.0 (future) |
|---|---|---|---|
| **Validator v1.0** | ✅ Compatible | ✅ Backward (additive) | ❌ Breaking — must upgrade |
| **Repository v1.0** | ✅ Compatible | ✅ Backward (additive) | ❌ Breaking — must upgrade |
| **API v1.0** | ✅ Compatible | ✅ Backward (additive) | ❌ Breaking — must upgrade |
| **CLI v1.0** | ✅ Compatible | ✅ Backward (additive) | ❌ Breaking — must upgrade |
| **Event Subscriber v1.0** | ✅ Compatible | ✅ Backward (additive) | ❌ Breaking — must upgrade |

## Upgrade Paths

### Minor (1.0 → 1.1)
1. Upgrade producer first (additive change is non-breaking).
2. Upgrade consumers at any time (they ignore new fields).
3. No coordination window required.

### Major (1.0 → 2.0)
1. **Both** producer and consumers must upgrade together.
2. Requires a CR + migration plan.
3. Requires a deprecation period (typically one minor version: 1.x deprecates, 2.0 removes).

## Migration History
- 1.0 → 1.1 (YYYY-MM-DD): added `properties["merged_into"]` to `KGNode`. Backward compatible.
- (future) 1.1 → 2.0: remove `KGNodeType.ORGANIZATION` (CR required).
```

---

## 5. CM-2026-001 — Knowledge Graph (M6) Compatibility Matrix

**Status:** DRAFT — pending M6.0 freeze
**Date:** 2026-07-03

### Components

| Component | Current Version | Released | Owner |
|---|---|---|---|
| `KGNode` (DTO) | 1.0 | pending M6.0 | Memory Lead |
| `KGEdge` (DTO) | 1.0 | pending M6.0 | Memory Lead |
| `KGNodeType` (Enum) | 1.0 (8 types) | pending M6.0 | Memory Lead |
| `KGEdgeType` (Enum) | 1.0 (7 types) | pending M6.0 | Memory Lead |
| `IKGRepository` (ABC) | 1.0 | pending M6.0 | Memory Lead |
| `KGService` | 1.0 | pending M6.0 | Memory Lead |
| `KGValidator` | 1.0 | pending M6.0 | Memory Lead |
| `TraversalEngine` | 1.0 | pending M6.0 | Memory Lead |
| `InferenceEngine` | 1.0 | pending M6.0 | Memory Lead |
| `Memory Orchestrator` (consumer) | 1.0 | pending M6.5 | Memory Lead |
| `Event subscribers` | 1.0 | pending M6.6 | Memory Lead |

### Compatibility Map

| Consumer → Producer | DTO v1.0 (8+7) | DTO v1.1 (10+8 if CR-1907 A) | DTO v2.0 (future) |
|---|---|---|---|
| **KGValidator v1.0** | ✅ Compatible | ✅ Backward (additive enum) | ❌ Breaking |
| **IKGRepository v1.0** | ✅ Compatible | ✅ Backward (no signature change) | ❌ Breaking |
| **KGService v1.0** | ✅ Compatible | ✅ Backward | ❌ Breaking |
| **Memory Orchestrator v1.0** | ✅ Compatible | ✅ Backward (new types passed-through) | ❌ Breaking |
| **Event Subscriber v1.0** | ✅ Compatible | ✅ Backward (new event topics registered at runtime) | ❌ Breaking |

### Upgrade Paths

#### Minor (1.0 → 1.1, e.g. after CR-1907 Option A)
1. Extend `KGNodeType` enum with DOCUMENT, SESSION. **Additive** — no consumer change required.
2. Extend `KGEdgeType` enum with REFERENCES. **Additive** — no consumer change required.
3. No migration script needed (new enum values are accepted by existing rows).
4. Consumers do NOT need to upgrade simultaneously.

#### Major (1.0 → 2.0, hypothetical)
1. Example: remove `KGNodeType.GOAL` and remap to `KGNodeType.TASK`.
2. Requires CR + migration plan: convert all `GOAL` rows to `TASK` with `properties["legacy_type"]="GOAL"`.
3. Requires deprecation period: 1.x logs warning when seeing `GOAL`; 2.0 rejects it.

### Migration History
(None yet — M6.0 is the initial release.)

### Sign-off
| Role | Name | Date |
|---|---|---|
| Memory Lead | ⏳ pending | |
| Architect | ⏳ pending | |
