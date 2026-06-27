# 10_CONTEXT_LOADING_RULES.md

## Purpose
This document establishes the Context Loading Rules for JARVIS OS. It defines how agents search, load, compress, and prune context files during development and execution to avoid LLM quality degradation due to high context pressure.

## Scope
Applies to all reasoning agent loops, workspace indexes, search operations, and external development scripts.

## Context Loading Rules (Layered Context Loading)

### 1. The Context Budget Rule
- **Standard:** Active agent sessions must operate within a **50% context budget window** relative to the target LLM's maximum token limit. This keeps reasoning accuracy at peak.
- **Action:** If context usage exceeds 50%, the system must trigger context compression or memory archiving.

### 2. Search-First Retrieval Protocol
- **Action:** Agents must query vector indexes or directories first using keyword searches before reading entire files.
- **Rule:** Never read a file unless its relevance is confirmed by search results.

### 3. Layered Context Structure
- When starting any task, the context must be loaded in the following strict layers:
```
System Prompt
    ↓
00_PROJECT_CONSTITUTION.md
    ↓
08_AI_AGENT_CONSTITUTION.md
    ↓
09_PROMPT_CONSTITUTION.md
    ↓
Current Phase Index (e.g. docs/57_IMPLEMENTATION_ROADMAP.md)
    ↓
Current Module Directory Map
    ↓
Current Task Specification (task.md)
    ↓
Target Implementation Files
```
This hierarchy ensures the agent always understands the constitutional rules before looking at source code details.

## Responsibilities
- **Context Engine:** Automatically computes token sizes, truncates long lists, and injects context layers in correct order.
- **Agent Developers:** Use relative imports and granular files to keep individual file sizes small (<300 lines) so they are easy to load.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Context Loader APIs: `ContextEngine.load_context(task_id: str)`.

## Examples
- **Correct Context Loading:** Agent is asked to fix a database bug. The Context Engine loads the Project Constitution, the Database Standard, the active task details, and ONLY the database wrapper file. Total token count is 12,000 tokens (5% context budget).
- **Incorrect Context Loading:** Agent is asked to fix a database bug. The developer loads the entire docs folder, all Python source code files, and the full PostgreSQL log history. Total token count is 180,000 tokens (90% context budget). (Violates the Context Budget Rule).

## Failure Cases
- **Context Overload:** Agent hallucinates or ignores instruction bounds due to a massive context payload. *Mitigation:* The system halts the loop and triggers the Context Compression policy (see `66_CONTEXT_COMPRESSION_POLICY.md`).

## Security Considerations
- Context loading filters out files containing API tokens, secrets, or SSH keys before passing data to cloud-based LLM APIs.

## Future Extension
- Modification of context budgets or loading parameters must be approved via ADR updates.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [08_AI_AGENT_CONSTITUTION.md](file:///e:/jarvis/docs/08_AI_AGENT_CONSTITUTION.md)
- [09_PROMPT_CONSTITUTION.md](file:///e:/jarvis/docs/09_PROMPT_CONSTITUTION.md)
- [66_CONTEXT_COMPRESSION_POLICY.md](file:///e:/jarvis/docs/66_CONTEXT_COMPRESSION_POLICY.md)
