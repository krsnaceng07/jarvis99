"""JARVIS OS - Prompt Builder.

Aggregates system prompts, personas, personal memories, conversation histories, and tool execution feedback under token budgets.
"""

from typing import Any, Dict, List, Optional


class PromptBuilder:
    """Assembles unified LLM prompts, injecting memory and history with token budget compression."""

    def __init__(self, max_context_tokens: int = 4000) -> None:
        """Initialize PromptBuilder.

        Args:
            max_context_tokens: Core maximum token allocation for context logs.
        """
        self.max_context_tokens = max_context_tokens

    def build_prompt(
        self,
        system_prompt: str,
        user_goal: str,
        memories: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        project_context: Optional[str] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Compile prompt payload segments.

        Args:
            system_prompt: Baseline instructions or persona.
            user_goal: Requested target task.
            memories: Retrieved personal facts list.
            history: Thread conversation messages.
            project_context: Associated project configurations.
            tool_results: Execution results parameters.

        Returns:
            String compiled prompt text.
        """
        prompt_parts = []

        # 1. System Instruction & Persona
        prompt_parts.append(f"System Context:\n{system_prompt}\n")

        # 2. Memories Context
        if memories:
            prompt_parts.append("User Personal Memories:")
            for idx, fact in enumerate(memories):
                prompt_parts.append(f"- {fact}")
            prompt_parts.append("")

        # 3. Project Context
        if project_context:
            prompt_parts.append(f"Active Project Details:\n{project_context}\n")

        # 4. History Logs
        if history:
            prompt_parts.append("Conversation History:")
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt_parts.append(f"{role.capitalize()}: {content}")
            prompt_parts.append("")

        # 5. Tool Results
        if tool_results:
            prompt_parts.append("Execution Feedbacks:")
            for res in tool_results:
                tool_name = res.get("tool_name", "unknown")
                status = res.get("status", "success")
                output = res.get("output", "")
                prompt_parts.append(f"Tool [{tool_name}] Status ({status}): {output}")
            prompt_parts.append("")

        # 6. Target Goal
        prompt_parts.append(f"User Goal Request:\n{user_goal}")

        compiled = "\n".join(prompt_parts)

        # Token-budget compression: if words exceed token allocations, truncate older segments
        words = compiled.split()
        estimated_tokens = int(len(words) * 1.3)
        if estimated_tokens > self.max_context_tokens:
            # Basic compression by truncating middle elements (e.g., history details)
            excess = estimated_tokens - self.max_context_tokens
            words_to_drop = int(excess / 1.3)
            if len(words) > words_to_drop:
                truncated = (
                    words[:200]
                    + ["... [truncated context due to budget] ..."]
                    + words[200 + words_to_drop :]
                )
                return " ".join(truncated)

        return compiled
