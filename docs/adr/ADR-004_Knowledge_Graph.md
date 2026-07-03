# ADR-004: Relational Knowledge Graph BFS Traversal

## Status
* **Status:** Accepted
* **Date:** 2026-07-02
* **Author:** Architecture Team

---

## Context
Entities and concepts stored in different memory records (e.g. users, tasks, skills) have complex relational associations that cannot be mapped effectively using flat vectors or simple string search.

---

## Decision
Implement a persistent entity-relationship Knowledge Graph:
* **Storage Schema:** Nodes (`graph_nodes`) and directional edges (`graph_edges`) mapped in relational tables (PostgreSQL/SQLite).
* **Constraints:** Node types must belong to the spec-defined `KGNodeType` list (Person, Organization, Location, Concept, Event, Task, Goal, Skill). Relation/edge types must belong to `KGEdgeType` (knows, works_on, depends_on, owns, related_to, caused_by, uses).
* **Query Traversal:** BFS traversal starting from a node up to `max_depth` with cycle avoidance to prevent infinite loop crashes.

---

## Consequences
* **Positive:** Relational context retrieval allows semantic expansions during query processing.
* **Negative:** Node/edge count scaling requires database indexing and query limits to prevent execution timeout under high depth parameters.

---

## Compliance & Invariants
* Validator must reject nodes or relations with undefined type strings.
* Graph traversal must always implement cycle tracking (e.g., visited node IDs list).
