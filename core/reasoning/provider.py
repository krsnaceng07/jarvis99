"""JARVIS OS - Model Provider Layer.

Defines IModelProvider and its concrete vendor implementations under circuit breaker health monitoring.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional


class ModelHealthStatus(Enum):
    """Circuit breaker states for model providers."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    COOLDOWN = "COOLDOWN"


class IModelProvider(ABC):
    """Abstract interface class representing an LLM model provider."""

    def __init__(self, name: str, model_name: str) -> None:
        """Initialize provider.

        Args:
            name: Provider vendor name.
            model_name: Loaded model name.
        """
        self.name = name
        self.model_name = model_name
        self.health_status = ModelHealthStatus.ONLINE
        self.failure_count = 0
        self.last_failed_at: Optional[float] = None
        self.cooldown_duration = 30.0  # seconds

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response text from prompt."""
        pass

    @abstractmethod
    async def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Any:
        """Stream response generator."""
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Return the estimated length of tokens for the given text."""
        pass

    @abstractmethod
    def supports_tools(self) -> bool:
        """Indicate if the model natively supports tool calling schemas."""
        pass

    @abstractmethod
    def supports_vision(self) -> bool:
        """Indicate if the model natively supports vision/image inputs."""
        pass

    async def health_check(self) -> ModelHealthStatus:
        """Determine health status based on current failure counts and cooldown stamps."""
        import time

        if self.health_status == ModelHealthStatus.COOLDOWN and self.last_failed_at:
            elapsed = time.time() - self.last_failed_at
            if elapsed >= self.cooldown_duration:
                self.health_status = ModelHealthStatus.ONLINE
                self.failure_count = 0

        return self.health_status

    def record_failure(self) -> None:
        """Register a request failure, moving status to cooldown or offline when limits exceed."""
        import time

        self.failure_count += 1
        self.last_failed_at = time.time()

        if self.failure_count >= 5:
            self.health_status = ModelHealthStatus.OFFLINE
        else:
            self.health_status = ModelHealthStatus.COOLDOWN

    def record_success(self) -> None:
        """Reset failure logs when success occurs."""
        self.failure_count = 0
        self.health_status = ModelHealthStatus.ONLINE


class GeminiProvider(IModelProvider):
    """Google Gemini model provider implementation."""

    def __init__(self, model_name: str = "gemini-1.5-pro") -> None:
        super().__init__("gemini", model_name)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        # Mock generator response for testing
        return f"[Gemini: {self.model_name}] Response to prompt."

    async def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Any:
        yield f"[Gemini: {self.model_name}] Stream chunk."

    def count_tokens(self, text: str) -> int:
        # standard mock estimation
        return len(text.split())

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return True


class ClaudeProvider(IModelProvider):
    """Anthropic Claude model provider implementation."""

    def __init__(self, model_name: str = "claude-3-5-sonnet") -> None:
        super().__init__("claude", model_name)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return f"[Claude: {self.model_name}] Response to prompt."

    async def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Any:
        yield f"[Claude: {self.model_name}] Stream chunk."

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return True


class OpenAIProvider(IModelProvider):
    """OpenAI GPT model provider implementation."""

    def __init__(self, model_name: str = "gpt-4o") -> None:
        super().__init__("openai", model_name)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return f"[OpenAI: {self.model_name}] Response to prompt."

    async def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Any:
        yield f"[OpenAI: {self.model_name}] Stream chunk."

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return True


class QwenProvider(IModelProvider):
    """Local Qwen model provider implementation."""

    def __init__(self, model_name: str = "qwen-2.5-coder") -> None:
        super().__init__("qwen", model_name)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return f"[Qwen: {self.model_name}] Response to prompt."

    async def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Any:
        yield f"[Qwen: {self.model_name}] Stream chunk."

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False


class LlamaProvider(IModelProvider):
    """Local Llama model provider implementation."""

    def __init__(self, model_name: str = "llama-3-8b") -> None:
        super().__init__("llama", model_name)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        return f"[Llama: {self.model_name}] Response to prompt."

    async def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Any:
        yield f"[Llama: {self.model_name}] Stream chunk."

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def supports_tools(self) -> bool:
        return False

    def supports_vision(self) -> bool:
        return False
