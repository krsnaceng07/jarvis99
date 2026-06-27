# 19_MODEL_ROUTING_POLICY.md

## Purpose
This document establishes the Model Routing Policy of JARVIS OS. It governs how execution tasks are routed to appropriate local or cloud LLMs based on task complexity, latency requirements, cost budgets, and privacy needs.

## Scope
Applies to the Model Router module, task queues, and configuration systems inside the Brain Core.

## Model Routing Policies
1. **The Capability-Cost Matrix:** Tasks must be categorized and routed to the most cost-efficient model capable of handling the work:
   - **Reasoning / Planning / Code Generation:** Cloud models (Claude 3.5 Sonnet / Gemini 1.5 Pro).
   - **Simple Tool Calling / Context Summarization:** Local models (Llama-3-8B / Qwen-2.5-Coder) or low-cost cloud APIs.
   - **Self-Debugging / Reflection:** Hybrid routing (routes to local models first, escalating to cloud if failure persists).
   - **Vision / OCR:** Vision-capable models (Claude Sonnet / local LLaVA / Gemini Flash).
2. **Local Fallback Protocol:** If cloud APIs are unavailable (due to network failure or rate limits), tasks must failover to local model endpoints (e.g. Ollama or local vLLM).
3. **API Budget Constraints:**
   - Maximum daily budget: **$10.00 USD** (default config, user customizable).
   - Before executing a cloud model call, the system must check cumulative daily spending. If exceeded, it halts cloud routing and switches exclusively to local models.

## Responsibilities
- **Model Router:** Dynamically selects the endpoint, formats payloads, manages retries, and records usage metrics.
- **Cost Governor:** Tallies API token usage and manages budget configurations.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Outbound API gateways: OpenAI API schemas, Anthropic API schemas, Google Gemini API schemas, and local Ollama REST endpoints.

## Examples
- **Correct Routing:** Planner needs to write a database migration -> routes to Claude 3.5 Sonnet. Self-improvement engine runs daily summary logs -> routes to local Llama-3-8B.
- **Incorrect Routing:** Summarizing a 50-line terminal log is sent directly to Gemini 1.5 Pro with a massive system prompt. (Violates Cost Optimization rule).

## Failure Cases
- **Cloud API Outage:** Anthropic API returns a `503 Service Unavailable`. *Mitigation:* The Model Router catches the exception, logs a warning, loads the local model configuration, and routes the code generation task to local Qwen-2.5-Coder.

## Security Considerations
- Tasks containing sensitive user files (defined by security policies) are restricted to local models to prevent data leakage to cloud endpoints.

## Future Extension
- Adding new models or adjusting fallback thresholds requires updating the Model Capability Matrix and this routing policy.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [09_PROMPT_CONSTITUTION.md](file:///e:/jarvis/docs/09_PROMPT_CONSTITUTION.md)
- [51_MODEL_ROUTING_POLICY.md](file:///e:/jarvis/docs/51_MODEL_ROUTING_POLICY.md)
- [65_COST_GOVERNOR.md](file:///e:/jarvis/docs/65_COST_GOVERNOR.md)
- [67_MODEL_CAPABILITY_MATRIX.md](file:///e:/jarvis/docs/67_MODEL_CAPABILITY_MATRIX.md)
