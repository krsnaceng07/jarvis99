# 03_DATABASE_SCHEMAS_FREEZE.md

## Purpose
This document freeze-locks the database schemas, table definitions, constraints, primary/foreign keys, and vector indices for JARVIS OS.

## Scope
Applies to all PostgreSQL tables, pgvector configurations, Alembic migration files, and database client models.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## SQL DDL Schemas (Frozen)

### 1. Agent Sessions Table (`agent_sessions`)
```sql
CREATE TABLE agent_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status VARCHAR(50) NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
```

### 2. Goal Trees Table (`goal_trees`)
```sql
CREATE TABLE goal_trees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES agent_sessions(id) ON DELETE CASCADE NOT NULL,
    goal_text TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_goal_trees_session_id ON goal_trees(session_id);
```

### 3. Memory Nodes Table (`memory_nodes`)
```sql
CREATE TABLE memory_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES agent_sessions(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536), -- pgvector index
    properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
CREATE INDEX idx_memory_nodes_session_id ON memory_nodes(session_id);
CREATE INDEX idx_memory_nodes_embedding ON memory_nodes USING hnsw (embedding vector_cosine_ops);
```

## Responsibilities
- **Database Administrator Agent:** Validates table indices and updates Alembic files during modifications.
- **Developer Agent:** Restricts SQL transactions to use these schema keys and types.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 4, Rule 11, and Rule 13).

## Interfaces
- Alembic database migration files: `/alembic/versions/*.py`.

## Examples
- **Correct DDL execution:** Deploying Alembic script adding `created_at` column matching standard type and index.
- **Incorrect DDL execution:** Injecting raw schema modifications inside test runs that alter target types or drop keys. (Violates frozen table structures).

## Failure Cases
- **PgVector HNSW Corruption:** The vector database index fails to return matching nodes. *Mitigation:* The memory core runs weekly index rebuild tests inside the database. If index errors occur, it logs warnings and alerts the user.

## Security Considerations
- Database users must operate under low-privilege settings (L1). The core execution gateway must not have permission to run `DROP TABLE` commands.

## Future Extension
- Enhancements to the relational structure require a new Alembic version script and ADR entry.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [12_MEMORY_ARCHITECTURE.md](file:///e:/jarvis/docs/12_MEMORY_ARCHITECTURE.md)
- [35_DATABASE_STANDARD.md](file:///e:/jarvis/docs/35_DATABASE_STANDARD.md)
- [25_KNOWLEDGE_GRAPH.md](file:///e:/jarvis/docs/25_KNOWLEDGE_GRAPH.md)
