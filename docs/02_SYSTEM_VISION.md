# 02_SYSTEM_VISION.md

## Purpose
This document outlines the System Vision for JARVIS OS. It details the conceptual distinction between a conversational chatbot and an autonomous AI Employee/AI Operating System.

## Scope
Defines the user experience paradigm, design metaphors, and operational boundaries of the JARVIS OS execution environment.

## The Vision: What JARVIS OS Is vs. What It Is Not
- **What It Is:**
  - **An AI Employee:** An agent that takes complete ownership of high-level goals (e.g. "Maintain this codebase" or "Build this web dashboard") and works independently.
  - **An Operating System:** A software environment that orchestrates resources, coordinates specialized agents, manages memory state, runs execution sandboxes, and controls standard UI inputs (Browser/PC).
  - **State-Driven:** Operates on a strict state machine, transitioning systematically through planning, executing, verifying, and learning.
- **What It Is Not:**
  - **A Chatbot:** It does not exist simply to answer questions or write code snippets in response to immediate prompts.
  - **A Passive tool:** It actively initiates subtasks, reviews its own output, patches errors, and seeks user feedback only when necessary.
  - **An Unstructured Shell:** It does not run commands or modify files arbitrarily. All actions are traced back to the goal tree.

## Responsibilities
- **AI Core Brain:** Manages the system-wide vision by rejecting unstructured chat requests and steering all operations towards structured task execution.
- **Human Owner:** Reviews agent execution stats, adjusts budgets, and provides strategic direction.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- GUI: Dashboard showing task progress, current agent states, browser stream viewport, and log streams.
- CLI: Command interface for launching system goals and managing settings.

## Examples
- **Chatbot Metaphor (Rejected):** User says "write a python function to merge lists." Agent outputs code and stops.
- **AI Operating System Metaphor (Accepted):** User says "Merge lists functionality needs to be added to utils.py." Agent reads utils.py, writes tests, implements the function, runs the tests, and reports completion status.

## Failure Cases
- **Aesthetic Regression:** The system dashboard looks like a plain chatbot window. *Mitigation:* The dashboard design principles (see `07_DESIGN_PRINCIPLES.md`) dictate a command center layout with real-time graphs, memory maps, and task status cards.

## Security Considerations
- The vision maintains strict separation between the AI's reasoning core and direct OS execution layers, ensuring no single model call has raw shell access.

## Future Extension
- The system vision is updated and extended via the Architecture Decision Record (ADR) workflow.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [01_PROJECT_CHARTER.md](file:///e:/jarvis/docs/01_PROJECT_CHARTER.md)
- [03_PRODUCT_REQUIREMENTS.md](file:///e:/jarvis/docs/03_PRODUCT_REQUIREMENTS.md)
- [07_DESIGN_PRINCIPLES.md](file:///e:/jarvis/docs/07_DESIGN_PRINCIPLES.md)
