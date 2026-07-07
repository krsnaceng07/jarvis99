# Phase 24 — Autonomous Agent Runtime Specification

## 1. Goal
Transition the JARVIS execution layer into a fully autonomous, self-correcting agent loop (`Observe-Think-Plan-Execute-Reflect-Replan`). This phase enables the engine to make runtime adjustments based on tool outputs, critique its own execution failures, update memory context dynamically, and call LLM API endpoints safely within token/cost budgets.

---

## 2. Architecture & Components

### 2.1 LLM Runtime (`core/tools/llm_runtime.py`)
Provides model routing, cost/token budgeting, and function-calling:
- **Interface:**
  ```python
  class ILLMRuntime(ABC):
      @abstractmethod
      async def generate(self, prompt: str, schema: Optional[Dict[str, Any]] = None) -> LLMResult:
          pass
  ```
- **Cost & Token tracking:** Integrates with `CostGovernor` to monitor cumulative usage.

### 2.2 Reflection Engine (`core/reasoning/reflection.py`)
Evaluates completed task status:
- **Evaluation Loop:**
  - Evaluates exit code, stdout, stderr, and output artifacts.
  - Matches runtime errors (e.g. `ModuleNotFoundError`) to known failure strategies.
- **Replanning Advice:** Returns structured correction inputs if failures occur.

### 2.3 Agent Loop (`core/reasoning/agent_loop.py`)
The orchestrator of the cognitive loop:
- Loops over execution waves.
- If a wave fails, it queries the Reflection Engine and requests the Planner to insert/modify tasks.
- Caps iterations (max 10) to prevent infinite loops.

---

## 3. Interfaces & Contracts

### LLM Call Payload
```json
{
  "prompt": "Evaluate target files...",
  "model_group": "reasoning",
  "temperature": 0.0,
  "max_tokens": 1000
}
```

### Reflection Output
```json
{
  "success": false,
  "failure_type": "ToolFailure",
  "reason": "Missing python package 'requests'",
  "advice": {
    "repair_strategy": "Install package 'requests' using pip or shell executor and retry."
  }
}
```
