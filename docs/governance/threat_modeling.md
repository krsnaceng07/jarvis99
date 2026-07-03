# Threat Modeling (STRIDE) — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §6 (STOP Protocol), Pre-Milestone Gate §2.11
**Related:** ARB, DRG, FMEA (failure matrix), Security review

---

## 1. Purpose

Threat modeling applies **STRIDE** — a structured classification of security threats developed at Microsoft — to every new subsystem **before** implementation. It complements the failure mode analysis (FMEA) which focuses on *reliability*; threat modeling focuses on *adversarial* failure.

**Rule:** Any milestone that introduces a new component, a new external dependency, or processes user data MUST have a STRIDE analysis filed. The Security Agent uses this to perform their veto.

---

## 2. STRIDE Categories

| Letter | Category | Question |
|---|---|---|
| **S** | **Spoofing** | Can an attacker impersonate a legitimate user/system? |
| **T** | **Tampering** | Can data be modified in transit or at rest by an attacker? |
| **R** | **Repudiation** | Can a user deny performing an action that the system cannot disprove? |
| **I** | **Information Disclosure** | Can data leak to an unauthorized party? |
| **D** | **Denial of Service** | Can the system be made unavailable through resource exhaustion? |
| **E** | **Elevation of Privilege** | Can a low-privilege user gain higher privilege? |

---

## 3. Threat Model Template

Each subsystem's threat model is filed as `TM-YYYY-NNN-<subsystem>.md` in `docs/threat/`.

```markdown
# TM-YYYY-NNN — <Subsystem Name>

**Status:** DRAFT | REVIEWED | APPROVED
**Date:** YYYY-MM-DD
**Reviewer:** Security Agent
**Affects:** <subsystem / spec / interface>

## System Description
<2-3 paragraphs>

## Data Flow Diagram (DFD)
```
[Source] → [Process] → [Storage]
              ↓
            [External API]
```

## Trust Boundaries
1. <boundary 1 — e.g. "API layer to Brain">
2. <boundary 2 — e.g. "Brain to Memory Repository">

## STRIDE Analysis

### S — Spoofing
| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| <threat> | <vector> | <mitigation> | <test path> |

### T — Tampering
| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| ... | ... | ... | ... |

### R — Repudiation
| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| ... | ... | ... | ... |

### I — Information Disclosure
| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| ... | ... | ... | ... |

### D — Denial of Service
| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| ... | ... | ... | ... |

### E — Elevation of Privilege
| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| ... | ... | ... | ... |

## Residual Risks
<list of risks that remain after mitigations; require sign-off>

## Sign-off
| Role | Name | Date |
|---|---|---|
| Security Agent | | |
| Architect | | |
```

---

## 4. TM-2026-001 — Knowledge Graph (M6)

**Status:** DRAFT — pending Security Agent review
**Date:** 2026-07-03
**Affects:** Knowledge Graph subsystem, M6

### System Description
The Knowledge Graph is a Domain-layer component that stores and queries entity-relationship data extracted from `MemoryRecord`. It accepts node/edge creation requests from the Memory Orchestrator (authenticated), persists them in PostgreSQL, and serves traversal/inference queries back to the Orchestrator. It is reachable only via internal IPC, never directly from the API layer.

### Data Flow Diagram
```
[Memory Orchestrator] → [KGService] → [KGValidator] → [IKGRepository] → [PostgreSQL]
       ↑                      ↓
       └──── events ←──── [EventBus]
```

### Trust Boundaries
1. **API layer → Memory Orchestrator:** requests are authenticated; Orchestrator enforces authorization.
2. **Memory Orchestrator → KGService:** internal IPC; assumes orchestrator is trusted.
3. **KGService → PostgreSQL:** authenticated via DB credentials from `core.config.MemoryConfig`.
4. **KGService → EventBus:** internal; events carry no PII (see contract §13.8).

### STRIDE Analysis

#### S — Spoofing

| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| Attacker forges `created_by` field on a node | Direct DB write or API call | `created_by` is set by Orchestrator from authenticated session; KG ignores client-supplied `created_by` | `test_kg_spoofing_created_by_rejected.py` |
| Attacker forges node UUID to overwrite existing node | Direct DB write | UUID v4 generated server-side; never accept client UUIDs in `create_node` | `test_kg_spoofing_uuid_overwrite_rejected.py` |

#### T — Tampering

| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| Attacker modifies `kg_nodes` rows via SQL injection | Unsanitized property values | All `properties` values passed through Pydantic validation; SQL uses parameterized queries (asyncpg/SQLAlchemy) | `test_kg_tampering_sql_injection.py` (uses adversarial payloads) |
| Attacker modifies `properties` after creation | Direct DB write or replay | Optimistic concurrency (`expected_version`); updates require version check | `test_kg_tampering_version_mismatch.py` |
| Attacker tampers with event payloads | EventBus MITM | Events are emitted only AFTER successful write; payloads carry `schema_version`; consumers validate | `test_kg_tampering_event_payload.py` |

#### R — Repudiation

| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| User denies creating a node | No audit trail | `created_by` + `created_at` are immutable; audit log table records all writes with caller identity | `test_kg_repudiation_audit_trail.py` |
| User denies merging two nodes | Merge is silent | `kg.node.merged` event always emitted with both ids, reason, actor | `test_kg_repudiation_merge_event.py` |

#### I — Information Disclosure

| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| Graph data leaked via event payloads | Events carry raw properties | Event payloads carry ids and types only; PII fields in `properties` are stripped before emission (per contract §13.8) | `test_kg_info_disclosure_event_pii.py` |
| Graph data leaked via traversal result to unauthorized caller | Missing authorization at KG layer | KG assumes Orchestrator is trusted; Orchestrator enforces row-level auth before calling KG | `test_kg_info_disclosure_orchestrator_gate.py` (orchestrator-level test) |
| Graph data leaked via Postgres backup or log | DB logs contain query + data | Pydantic masks sensitive fields; Postgres `log_statement = 'ddl'` (no data); backups encrypted at rest | Operational concern; documented in `docs/29_SECRET_MANAGEMENT.md` |
| Graph data leaked via error messages | Verbose error messages | Error hierarchy uses stable codes (`KGValidationError`); no raw property values in error messages | `test_kg_info_disclosure_error_messages.py` |

#### D — Denial of Service

| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| Attacker submits huge traversal depth | API call with `max_depth=1000` | `max_depth` capped at 8 (raises `MaxDepthExceededError`); default is 3 | `test_kg_dos_max_depth.py` |
| Attacker creates millions of duplicate nodes | API flood | Idempotency on `(type, content_hash, valid_from)` returns existing node | `test_kg_dos_duplicate_creation.py` |
| Attacker causes OOM via huge `properties` blob | API call with 10MB property | `properties` size capped at 64KB (Pydantic constraint); raises `KGValidationError` | `test_kg_dos_property_size.py` |
| Attacker causes DB connection exhaustion | Connection leak | Pool size capped at 10; queries timeout at 5s; `RepositoryUnavailableError` raised on pool exhaustion | `test_kg_dos_connection_pool.py` |
| Attacker creates cycles to slow traversal | Adversarial node/edge creation | Cycle prevention in traversal (visited-set); cycle in graph itself is permitted (data model is DAG-tolerant) | `test_kg_dos_traversal_cycles.py` |
| Attacker floods event bus | High write rate | Events are emitted AFTER write (no amplification); rate-limiting at API layer (out of scope for KG) | Operational concern |

#### E — Elevation of Privilege

| Threat | Vector | Mitigation | Test |
|---|---|---|---|
| Low-privilege user creates high-privilege node type | No type-based authz | KG does not enforce authz; relies on Orchestrator. All node types are equally "privileged" — type does not confer capabilities | Documented in contract §11 (KG has no authz; orchestrator owns it) |
| Attacker manipulates `expected_version` to bypass concurrency | Crafted request | Optimistic concurrency is a *correctness* mechanism, not a *security* one. Authz happens at Orchestrator. | Documented |

### Residual Risks
1. **KG has no authz layer** — accepts any internal request. This is by design (Orchestrator enforces authz). Risk: if a future module calls KG directly without going through Orchestrator, no defense in depth. **Mitigation:** Dependency-direction rule (§7.4) forbids API/CLI from calling KG directly. Enforced by `audit/architecture_audit.py`.
2. **Postgres backup encryption** depends on operational discipline, not code. **Mitigation:** Documented runbook in `docs/43_DEPLOYMENT_STANDARD.md`.
3. **Inference engine abuse** — a malicious caller could request infinite transitive closure. **Mitigation:** Max-depth cap (8) and result-set cap (10K nodes) in inference query (per contract §13.4).

### Sign-off
| Role | Name | Date |
|---|---|---|
| Security Agent | ⏳ pending | |
| Architect | ⏳ pending | |
