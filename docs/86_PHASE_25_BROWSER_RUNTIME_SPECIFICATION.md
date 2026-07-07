# Phase 25 — Browser Runtime & Execution Journal Specification

## 1. Goal
Integrate the existing `core/browser/` subsystem as a first-class executor (`ExecutorType.BROWSER`) within the `AgentLoop` reasoning pipeline. This enables autonomous agents to execute web browsing tasks (navigate, click, type, screenshot, DOM extraction) and receive structured reflection. Additionally, implement an append-only, in-memory `ExecutionJournal` to track details of each agent loop iteration deterministically.

---

## 2. Architecture & Components

### 2.1 Browser Executor (`core/tools/browser_runtime.py`)
Acts as the thin adapter wrapping the `BrowserEngine` and providing the `BaseExecutor` interface:
- **Interface:**
  ```python
  class BrowserRuntime:
      def __init__(self, engine: BrowserEngine) -> None:
          pass

      async def execute(self, task: Task, context: Dict[str, Any]) -> ToolExecutionResult:
          pass
  ```
- **Actions:** Maps payload actions (`navigate`, `click`, `type`, `scroll`, `hover`, `upload`, `download`, `press_key`, `screenshot`, `extract_dom`, `wait`) to `BrowserEngine` and its driver.
- **Auto-Launch:** Automatically launches the browser driver with the specified or default profile if it is not already launched.
- **Self-Healing Tab:** Auto-initializes/opens a browser tab on a `navigate` action if no active tab is registered in `BrowserStateManager`.
- **Permission Enforcement:** Permission restrictions and validation exceptions return as structured `FAILURE` results (not raised exceptions) to allow `ReflectionEngine` diagnostics.

### 2.2 Execution Journal (`core/reasoning/journal.py`)
Maintains a deterministic, append-only chronological log of all iterations in the `AgentLoop`:
- **Interface:**
  ```python
  class IterationRecord(BaseModel):
      iteration: int
      goal_description: str
      chosen_executor: str
      reasoning: str
      output_summary: str
      reflection_category: Optional[str]
      next_action: str
      timestamp: datetime

  class ExecutionJournal:
      def record_iteration(self, ...) -> None:
          pass

      def export(self) -> List[IterationRecord]:
          pass

      def export_text(self) -> str:
          pass
  ```
- **Constraints:**
  - **Append-only:** No edit, update, delete, or clear APIs.
  - **No Raw Prompts:** Only summaries and key decisions are recorded.
  - **Deterministic Export:** Records sorted by `iteration` ASC.

---

## 3. Payload Contracts

### Browser Task Payload
```json
{
  "action": "navigate",
  "url": "https://google.com",
  "selector": "#search",
  "text": "JARVIS OS",
  "profile": "default",
  "timeout": 30
}
```

### Agent Loop Result with Journal
```json
{
  "termination_reason": "SUCCESS",
  "iterations_used": 1,
  "tasks_completed": 1,
  "tasks_failed": 0,
  "final_outputs": [...],
  "memory_updates": [...],
  "journal": [
    {
      "iteration": 1,
      "goal_description": "Search google for JARVIS OS",
      "chosen_executor": "BROWSER",
      "reasoning": "Need to look up documentation online.",
      "output_summary": "Navigated to https://google.com",
      "reflection_category": null,
      "next_action": "SUCCESS",
      "timestamp": "2026-07-04T11:00:00Z"
    }
  ]
}
```
