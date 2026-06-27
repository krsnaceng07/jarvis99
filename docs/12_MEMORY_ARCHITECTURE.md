# 12_MEMORY_ARCHITECTURE.md

## Purpose
This document defines the multi-tiered Memory Architecture of JARVIS OS, mapping out how data moves through working memory, session storage, long-term databases, vector indices, and graph representations.

## Scope
Applies to all database schemas, Redis keyspace layouts, vector search queries, and graph indexing logic in the Memory Subsystem.

## Memory Architecture Tiers
The memory system is structured into five distinct levels to optimize speed, context size, and relational recall:

```
[Working Memory (Redis)] 
        ↓ (Fast-decay cache, active variables)
[Session Memory (PostgreSQL)] 
        ↓ (Active task status, conversational logs)
[Long-Term Memory (PostgreSQL / PgVector)] 
        ↓ (Semantic summaries, embeddings)
[Knowledge Graph (PostgreSQL Graph)] 
        ↓ (Entities, relations, ontology maps)
[Archive (Files / S3 / Compress)] (Deep backup)
```

### Memory Pipeline Validation Standard
Memory must never be modified directly by the core agent. All memory updates follow the pipeline:
```
Observe → Validate → Summarize → Store → Index → Retrieve → Archive
```
- **Observe:** Capture input/execution telemetry.
- **Validate:** Ensure data is well-formed, sanitizing sensitive strings.
- **Summarize:** Extract key takeaways to optimize context footprint.
- **Store:** Persist to database.
- **Index:** Generate vector embedding and graph links.

## Responsibilities
- **Memory Agent:** Responsible for indexing new items, cleaning up duplicate nodes, and conducting vector queries.
- **Database Administrator:** Sets up index structures, monitors Postgres tables, and maintains Redis config.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Memory API: `MemoryManager.store(node: MemoryNode)` and `MemoryManager.retrieve(query: str)`.

## Examples
- **Correct Memory Write:** Agent completes a coding task. The completed plan is summarized, pgvector indexes it, entities are linked to the Knowledge Graph, and details are archived.
- **Incorrect Memory Write:** Raw log files containing database passwords are saved directly into the vector index without sanitization or summarization. (Violates Security and Pipeline requirements).

## Failure Cases
- **Graph Drift:** Knowledge graph nodes grow disjointed or contain loops. *Mitigation:* The Memory Agent runs weekly graph integrity scripts to resolve redundant nodes and optimize traversal depth.

## Security Considerations
- All data stored in long-term memory must be filtered. High-security data (API keys, session tokens) must never enter the vector DB or knowledge graph.

## Future Extension
- Database migrations or schema updates are managed under the database standard policies.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [04_TECHNICAL_REQUIREMENTS.md](file:///e:/jarvis/docs/04_TECHNICAL_REQUIREMENTS.md)
- [25_KNOWLEDGE_GRAPH.md](file:///e:/jarvis/docs/25_KNOWLEDGE_GRAPH.md)
- [30_DATABASE_STANDARD.md](file:///e:/jarvis/docs/30_DATABASE_STANDARD.md)
