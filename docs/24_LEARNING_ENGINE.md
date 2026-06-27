# 24_LEARNING_ENGINE.md

## Purpose
This document defines the Learning Engine of JARVIS OS. It governs how the system reads external documents, research papers, developer APIs, and software guides, summarizing them and updating the internal Knowledge Graph for future reuse.

## Scope
Applies to document scrapers, research engines, vector indexers, and ontology mapping modules.

## Learning Engine Workflow
When the agent encounters an unfamiliar library, API, or task requirement, it activates the Learning Engine to ingest and index the necessary knowledge:

```
Read Document / URL / Scrape Target API
        ↓
Extract Plain Text & Code Snippets
        ↓
Summarize Context & Remove Noise (Syntax Fluff, Ads)
        ↓
Run Semantic Entity Extraction (Extract Nodes & Relations)
        ↓
Insert Entities into Relational Knowledge Graph
        ↓
Generate Embeddings & Save to PgVector Database
        ↓
Convert Dynamic Knowledge to Reusable Skill Interface (If applicable)
        ↓
Register & Cache for future agent execution
```

### Ingestion Standard
1. **Source Verification:** Ingested documents must come from trusted, user-approved domains or documentation repositories (e.g. readthedocs, github, official API sites).
2. **Context Retention:** Embedded summaries must retain function signatures, error descriptions, and code examples.

## Responsibilities
- **Researcher Agent:** Scrapes URLs, reads PDFs, extracts text payloads, and formats summaries.
- **Memory Agent:** Indexes entities, inserts links to the Knowledge Graph, and generates embeddings.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Input: URL links or files parsed via REST endpoints `/api/v1/learning/ingest`.
- Output: Memory node IDs and Graph updates logged to PostgreSQL.

## Examples
- **Correct Ingestion:** Researcher scrapes the Playwright documentation page, extracts page click function schemas, saves them in the vector database, and links "Playwright" -> "Browser Scrape" in the Knowledge Graph.
- **Incorrect Ingestion:** Researcher scrapes entire news feeds or general forum threads and fills the vector memory with unstructured, irrelevant data. (Violates Ingestion Standard).

## Failure Cases
- **Stale Information:** Scraped API documentation contains deprecated functions. *Mitigation:* Ingested memory nodes are assigned a timestamp and a "valid until" duration. When accessed, if the timestamp is older than 30 days, the engine alerts the user or triggers an automated refresh.

## Security Considerations
- The engine blocks scraping of pages requiring authorization keys or credentials unless those keys are securely mounted via the Secrets Vault.

## Future Extension
- Enhancements to the learning rules or graph ontologies are managed through ADR entries.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [12_MEMORY_ARCHITECTURE.md](file:///e:/jarvis/docs/12_MEMORY_ARCHITECTURE.md)
- [25_KNOWLEDGE_GRAPH.md](file:///e:/jarvis/docs/25_KNOWLEDGE_GRAPH.md)
