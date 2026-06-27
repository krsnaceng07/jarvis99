# 67_MODEL_CAPABILITY_MATRIX.md

## Purpose
This document defines the Model Capability Matrix for JARVIS OS. It establishes model attributes, routing categories, cost weights, and fallback execution targets for all AI agents.

## Scope
Applies to the Model Router configurations, cost governors, and agents initialization files.

## Model Capability Matrix
The system maps runtime tasks to specific models using the matrix defined below:

| Task Category | Primary Target | Secondary Fallback | Min Context Size | Cost Profile | Key Capability Required |
| --- | --- | --- | --- | --- | --- |
| **Planning** | Claude 3.5 Sonnet | Gemini 1.5 Pro | 64k | Premium | Goal decomposition, JSON parsing |
| **Code Generation** | Claude 3.5 Sonnet | Qwen-2.5-Coder (Local)| 32k | Premium / Free | Multi-file edits, PEP 8 syntax |
| **Summarization** | Gemini 1.5 Flash | Llama-3-8B (Local) | 128k | Economy / Free | Long context processing speed |
| **Self-Debugging** | Gemini 1.5 Pro | Qwen-2.5-Coder (Local)| 64k | Premium / Free | Stack trace reading, logical RCA |
| **Tool Calling** | Llama-3-8B (Local) | Gemini 1.5 Flash | 16k | Free / Economy | Parameter binding, low latency |
| **Vision / OCR** | Claude 3.5 Sonnet | Gemini 1.5 Flash | 32k | Premium / Economy | coordinate translation, image mapping|

## Responsibilities
- **Model Router:** Dynamically queries this matrix to select endpoints and formats payloads.
- **Cost Governor:** Evaluates cost weights to optimize token usage.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 2 and Rule 13).

## Interfaces
- Input: Task context payload.
- Output: Model endpoint payload (API key, endpoint URL).

## Examples
- **Correct Mapping:** Router routes a code block patch task to Qwen-2.5-Coder (Local) when the daily budget is low.
- **Incorrect Mapping:** Routing a simple regex tool parameter verification task to Claude 3.5 Sonnet. (Violates Cost Profile rules).

## Failure Cases
- **Fallback Exhaustion:** Both primary and secondary models are offline. *Mitigation:* The Model Router loops through all active endpoints. If all fail, the task is suspended, and the supervisor triggers Safe Mode.

## Security Considerations
- Matrix configuration is hardcoded in settings and cannot be altered by agent-generated scripts to prevent unauthorized cloud redirection.

## Future Extension
- Adding new models requires updating this matrix and verifying endpoint connectivity.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [09_PROMPT_CONSTITUTION.md](file:///e:/jarvis/docs/09_PROMPT_CONSTITUTION.md)
- [19_MODEL_ROUTING_POLICY.md](file:///e:/jarvis/docs/19_MODEL_ROUTING_POLICY.md)
- [65_COST_GOVERNOR.md](file:///e:/jarvis/docs/65_COST_GOVERNOR.md)
