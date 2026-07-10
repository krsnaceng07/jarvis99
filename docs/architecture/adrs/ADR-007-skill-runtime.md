# ADR-007: Dynamic Skill System Runtime & Isolation

## Status
* **Status:** Accepted
* **Date:** 2026-07-02
* **Author:** Architecture Team

---

## Context
AI agents must extend their functionality dynamically by creating, downloading, and running executable code packages (Skills). Executing unverified third-party code directly on the host system presents high security risks (sandbox escapes, malicious IO).

---

## Decision
Establish a structured Skill Registry and execution runtime:
* **Registry and Signing:** All skills must be registered and signed with a cryptographic signature verified at load time.
* **Execution Sandbox:** Run dynamic python executions inside containerized environments (Docker or strict isolated process shells) with restricted access to filesystem paths, hardware, and external network domains.
* **Permission Model:** Standardize security clearances (L0 to L3) mapped to resource request envelopes.

---

## Consequences
* **Positive:** Prevents malicious code execution from compromising host configurations; enforces secure access control.
* **Negative:** Container startup latency adds to runtime overhead; local setups require Docker or local isolated execution wrappers.

---

## Compliance & Invariants
* Dynamic executions must pass parameters scanning via security validators.
* Skill execution must fail immediately if the cryptographical signature check fails.
