# PHASE_36_IMPLEMENTATION_PLAN.md

## Purpose
This document outlines the detailed implementation plan for **Phase 36: Swarm Intelligence & Multi-Agent Consensus**, focusing on adding consensus coordination capabilities, REST voting APIs, and cryptographic validation suites without modifying any frozen interfaces.

## Status
**STATUS:** DRAFT (Awaiting Approval)
**Authority:** Rank 5 (Implementation Plan)
**Dependencies:** Phase 35

---

## 1. File Changes and Ownership

To implement multi-agent consensus, the following files will be added or modified:

| Action | Path | Responsibility |
| ------ | ---- | -------------- |
| **[NEW]** | `core/runtime/consensus.py` | Core `ConsensusManager` service class. Contains consensus proposing, voting, and checks. |
| **[NEW]** | `api/routes/consensus_routes.py` | REST API routes under `/api/v1/federation/consensus` for proposing and voting. |
| **[NEW]** | `tests/test_consensus.py` | Verification suite testing proposal status, votes signature, and expirations. |
| **[MODIFY]** | `core/kernel.py` | Boot wiring to register `ConsensusManager` in container. |
| **[MODIFY]** | `api/dependencies.py` | Dependency injection setup exposing `get_consensus_manager`. |
| **[MODIFY]** | `api/main.py` | Route registering setup mounting the consensus router. |

---

## 2. Milestones and Deliverables

### Milestone 1: Consensus Core & DI Setup
- Implement `core/runtime/consensus.py` with `ConsensusManager` and proposal lifecycle structures.
- Register `ConsensusManager` in `core/kernel.py`.
- Expose `get_consensus_manager` in `api/dependencies.py`.
- **Mini-Quality Gate**: `ruff check`, `mypy --strict core/runtime/consensus.py`.

### Milestone 2: API Route Integrations
- Create `api/routes/consensus_routes.py` with `/propose`, `/vote`, and status polling.
- Gate routes with signature verification middleware (`verify_federation_signature`).
- Register router in `api/main.py`.
- **Mini-Quality Gate**: `ruff check`, `mypy --strict api/routes/consensus_routes.py`.

### Milestone 3: Test Verification
- Create `tests/test_consensus.py` testing state machine logic, cryptographic vote verification, double voting blocks, and expirations.
- Run complete test suite and coverage check.
- **Final Quality Gate**: `python scripts/quality_gate.py`.
