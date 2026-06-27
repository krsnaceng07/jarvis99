# 08_COMPONENT_INTERFACE_FREEZE.md

## Purpose
This document freeze-locks the public and internal API method signatures, parameter types, return values, and event bindings for all major components of JARVIS OS.

## Scope
Applies to the Kernel, Event Bus, Memory Core, Planner, Browser Engine, PC Controller, Tool Runtime, Agent Runtime, Voice, and Vision subsystems.

## Immutability Policy
This freeze document is strictly immutable. Future changes require:
```
Architecture Decision Record (ADR) → Impact Analysis → Human Approval → Version Increment
```

## Component Public & Internal APIs

### 1. Kernel Interface
- **Public API:** `Kernel.boot(config_path: str) -> bool`
- **Internal API:** `Kernel._load_vault() -> bool`, `Kernel._initialize_event_bus() -> bool`
- **Events:** Publishes `system.kernel.ready`.

### 2. Event Bus Interface
- **Public API:** `EventBus.publish(topic: str, message: InterAgentMessage) -> bool`
- **Public API:** `EventBus.subscribe(topic: str, callback: Callable) -> str`
- **Internal API:** `EventBus._cleanup_stream() -> None`

### 3. Memory Core Interface
- **Public API:** `MemoryCore.store_node(node: MemoryNode) -> UUID`
- **Public API:** `MemoryCore.query_vector(embedding: list[float], limit: int) -> list[MemoryNode]`
- **Internal API:** `MemoryCore._generate_embedding(text: str) -> list[float]`
- **Events:** Publishes `memory.node.created`.

### 4. Planner Interface
- **Public API:** `Planner.create_goal_tree(goal: str) -> GoalTree`
- **Public API:** `Planner.decompose_task(task_id: UUID) -> list[Task]`
- **Events:** Publishes `agent.task.started`, `agent.task.completed`.

### 5. Tool Runtime Interface
- **Public API:** `ToolRuntime.execute_tool(tool_name: str, arguments: dict) -> dict`
- **Internal API:** `ToolRuntime._create_sandbox() -> str`, `ToolRuntime._verify_signature(signature: str) -> bool`
- **Events:** Publishes `system.tool.executed`.

### 6. Browser Engine Interface
- **Public API:** `BrowserEngine.navigate(url: str) -> bool`
- **Public API:** `BrowserEngine.extract_dom() -> str`
- **Events:** Publishes `browser.page.loaded`.

### 7. PC Controller Interface
- **Public API:** `PCController.execute_action(action: str, params: dict) -> dict`
- **Internal API:** `PCController._check_coordinates(x: int, y: int) -> bool`

## Responsibilities
- **Developer Agent:** Must implement classes matching these method signatures.
- **Reviewer Agent:** Blocks PR merges if public interfaces deviate from these definitions.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Python class type annotations and interface definitions.

## Examples
- **Correct Implementation:**
```python
class EventBus:
    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        # Code matches signature exactly
        pass
```
- **Incorrect Implementation:**
```python
class EventBus:
    async def publish(self, topic: str, payload_dict: dict, priority: str) -> None:
        # Violates the frozen parameters and return types
        pass
```

## Failure Cases
- **Parameter Mismatch:** A developer changes a return type from `bool` to `dict`. *Mitigation:* The Quality Gates run `mypy` static type checking. If signatures fail type matching against this freeze list, compilation fails.

## Security Considerations
- Interfaces separating the PC Controller and Browser Engine from the reasoning core must enforce type validation to prevent injection exploits.

## Future Extension
- Modifying method parameters or return types requires updating this document via ADR approval.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [05_SYSTEM_ARCHITECTURE.md](file:///e:/jarvis/docs/05_SYSTEM_ARCHITECTURE.md)
- [18_TOOL_EXECUTION_POLICY.md](file:///e:/jarvis/docs/18_TOOL_EXECUTION_POLICY.md)
- [02_API_CONTRACTS_FREEZE.md](file:///e:/jarvis/docs/architecture/02_API_CONTRACTS_FREEZE.md)
