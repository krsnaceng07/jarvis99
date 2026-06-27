# 65_COST_GOVERNOR.md

## Purpose
This document defines the Cost Governor policy for JARVIS OS. It establishes cloud model budget constraints, token cost calculations, estimation checkpoints, and local model failover triggers.

## Scope
Applies to all cloud LLM API calls, model routing tasks, and billing log integrations.

## Cost Limits & Fallback Policies
1. **Daily API Budget:**
   - The maximum daily spending on cloud models is limited to **$10.00 USD** (default config).
   - If cumulative daily spending reaches **$8.00 USD** (80% threshold), the system sends a high-priority dashboard alert to the user.
2. **Pre-Call Token Estimation:**
   - Before executing a cloud model call with a large context, the system must compute the input token count.
   - If the estimated cost of a single request exceeds **$0.50 USD**, the routing queue is paused, and the request is sent to the user for manual approval.
3. **Budget Exhaustion Failover:**
   - When the daily budget is 100% exhausted ($10.00), all cloud model routing is immediately blocked.
   - The Model Router switches automatically to local model endpoints (e.g. local Ollama or vLLM) for all active tasks.

## Responsibilities
- **Cost Governor Service:** Calculates token costs (input/output parameters), logs usage, and updates active budget balances in PostgreSQL.
- **Model Router:** Dispatches API requests and catches budget exhaustion warnings.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md) (specifically Rule 13 and Rule 14).

## Interfaces
- Output: Cost alerts on the UI dashboard.
- Database: Spending tables initialized in PostgreSQL.

## Examples
- **Correct Cost Flow:** Agent is asked to summarize a huge repository. The token estimator calculates a cost of $1.20, pauses the queue, shows the estimate to the user, and awaits confirmation.
- **Incorrect Cost Flow:** Agent runs a looping task containing bugs that repeatedly calls Claude API, consuming $150 in cloud fees within 10 minutes. (Violates Daily API Budget and Pre-Call Estimation rules).

## Failure Cases
- **Stale Token Pricing:** Cloud API providers change token prices, causing incorrect cost estimations. *Mitigation:* The Cost Governor fetches active model pricing lists from a central registry once a week or maps them to configurable settings.

## Security Considerations
- Budget limits must be locked inside Pydantic Settings models on the host machine to prevent agents from modifying pricing variables.

## Future Extension
- Enhancing pricing rules or supporting new models requires updating configuration values.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [19_MODEL_ROUTING_POLICY.md](file:///e:/jarvis/docs/19_MODEL_ROUTING_POLICY.md)
- [30_CONFIGURATION_STANDARD.md](file:///e:/jarvis/docs/30_CONFIGURATION_STANDARD.md)
- [67_MODEL_CAPABILITY_MATRIX.md](file:///e:/jarvis/docs/67_MODEL_CAPABILITY_MATRIX.md)
