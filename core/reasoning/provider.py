"""JARVIS OS - Model Provider Layer.

Defines IModelProvider, ProviderConfig, and concrete vendor implementations with circuit breaker health monitoring and streaming support.
"""

import json
import re
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator, Dict, Optional

from pydantic import BaseModel

from core.exceptions import (
    ModelProviderError,
    TransportError,
)
from core.reasoning.credentials import CredentialManager
from core.reasoning.transport import IHttpTransport, UrllibTransport


class ModelHealthStatus(Enum):
    """Circuit breaker states for model providers."""

    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    COOLDOWN = "COOLDOWN"


class ProviderConfig(BaseModel):
    """DTO defining the configuration parameters for a model provider."""

    provider_name: str
    model_name: str
    base_url: str
    timeout: float = 30.0
    max_retries: int = 3
    api_version: Optional[str] = None
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = True
    max_context_tokens: int = 32000
    max_output_tokens: int = 4096


async def _mock_stream(provider_name: str, model_name: str) -> AsyncIterator[str]:
    """Helper to yield a mock stream chunk for testing."""
    yield f"[{provider_name.capitalize()}: {model_name}] Stream chunk."


class IModelProvider(ABC):
    """Abstract interface representing an LLM model provider."""

    def __init__(
        self,
        config: ProviderConfig,
        transport: Optional[IHttpTransport] = None,
        cred_manager: Optional[CredentialManager] = None,
    ) -> None:
        """Initialize provider.

        Args:
            config: ProviderConfig DTO mapping vendor parameters.
            transport: Async HTTP transport client.
            cred_manager: API credentials manager.
        """
        self.config = config
        self.name = config.provider_name
        self.model_name = config.model_name
        self.transport = transport or UrllibTransport()
        self.cred_manager = cred_manager or CredentialManager()

        # Circuit Breaker state variables
        self.health_status: ModelHealthStatus = ModelHealthStatus.ONLINE
        self.failure_count = 0
        self.last_failed_at: Optional[float] = None
        self.cooldown_duration = 30.0  # seconds

    @abstractmethod
    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate response text from prompt."""
        pass

    @abstractmethod
    async def stream_generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream response chunks from prompt."""
        pass

    def count_tokens(self, text: str) -> int:
        """Estimate the length of tokens for the given text using standard word estimation."""
        return int(len(text.split()) * 1.3)

    def supports_tools(self) -> bool:
        """Indicate if the model natively supports tool calling schemas."""
        return self.config.supports_tools

    def supports_vision(self) -> bool:
        """Indicate if the model natively supports vision/image inputs."""
        return self.config.supports_vision

    def get_model_info(self) -> Dict[str, Any]:
        """Return provider capability descriptors."""
        return self.config.model_dump()

    async def health_check(self) -> ModelHealthStatus:
        """Determine health status based on current failure counts and cooldown stamps."""
        if self.health_status == ModelHealthStatus.COOLDOWN and self.last_failed_at:
            elapsed = time.time() - self.last_failed_at
            if elapsed >= self.cooldown_duration:
                self.health_status = ModelHealthStatus.ONLINE
                self.failure_count = 0

        return self.health_status

    def record_failure(self) -> None:
        """Register a request failure, moving status to cooldown or offline when limits exceed."""
        self.failure_count += 1
        self.last_failed_at = time.time()

        if self.failure_count >= 5 or self.health_status == ModelHealthStatus.OFFLINE:
            self.health_status = ModelHealthStatus.OFFLINE
        else:
            self.health_status = ModelHealthStatus.COOLDOWN

    def record_success(self) -> None:
        """Reset failure logs when success occurs."""
        self.failure_count = 0
        self.health_status = ModelHealthStatus.ONLINE

    def _get_api_key(self) -> str:
        """Retrieve credential API key from manager."""
        return self.cred_manager.get_api_key(self.name)


class GeminiProvider(IModelProvider):
    """Google Gemini model provider implementation."""

    def __init__(
        self,
        config: Optional[ProviderConfig] = None,
        transport: Optional[IHttpTransport] = None,
        cred_manager: Optional[CredentialManager] = None,
    ) -> None:
        cfg = config or ProviderConfig(
            provider_name="gemini",
            model_name="gemini-1.5-pro",
            base_url="https://generativelanguage.googleapis.com",
            max_context_tokens=1048576,
            max_output_tokens=8192,
        )
        super().__init__(cfg, transport, cred_manager)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if self.model_name.startswith("mock"):
            return f"[Gemini: {self.model_name}] Response to prompt."

        api_key = self._get_api_key()
        url = f"{self.config.base_url}/v1beta/models/{self.model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}

        contents = [{"parts": [{"text": prompt}]}]
        payload: Dict[str, Any] = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        try:
            res_bytes = await self.transport.request(
                "POST",
                url,
                headers,
                json.dumps(payload).encode("utf-8"),
                self.config.timeout,
            )
            data = json.loads(res_bytes.decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            self.record_success()
            return str(text)
        except Exception as err:
            self.record_failure()
            self._handle_error(err)
            raise

    async def stream_generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        if self.model_name.startswith("mock"):
            return _mock_stream(self.name, self.model_name)

        api_key = self._get_api_key()
        url = f"{self.config.base_url}/v1beta/models/{self.model_name}:streamGenerateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}

        contents = [{"parts": [{"text": prompt}]}]
        payload: Dict[str, Any] = {"contents": contents}
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        async def generator() -> AsyncIterator[str]:
            try:
                stream = await self.transport.stream_request(
                    "POST",
                    url,
                    headers,
                    json.dumps(payload).encode("utf-8"),
                    self.config.timeout,
                )
                buffer = ""
                async for chunk in stream:
                    buffer += chunk.decode("utf-8")
                    # Gemini returns stream chunks within JSON array objects: [{...}, {...}]
                    # Find all objects using regex matching candidates parts text
                    matches = re.findall(r'"text"\s*:\s*"([^"]+)"', buffer)
                    if matches:
                        for text_match in matches:
                            # Clean up backslash escape chars
                            yield text_match.encode("utf-8").decode("unicode-escape")
                        buffer = ""
                self.record_success()
            except Exception as err:
                self.record_failure()
                self._handle_error(err)
                raise

        return generator()

    def _handle_error(self, err: Exception) -> None:
        if isinstance(err, ModelProviderError):
            raise err
        raise TransportError(
            code="GEMINI_ERR",
            message=f"Gemini API request failed: {err}",
        ) from err


class ClaudeProvider(IModelProvider):
    """Anthropic Claude model provider implementation."""

    def __init__(
        self,
        config: Optional[ProviderConfig] = None,
        transport: Optional[IHttpTransport] = None,
        cred_manager: Optional[CredentialManager] = None,
    ) -> None:
        cfg = config or ProviderConfig(
            provider_name="claude",
            model_name="claude-3-5-sonnet",
            base_url="https://api.anthropic.com",
            max_context_tokens=200000,
            max_output_tokens=8192,
        )
        super().__init__(cfg, transport, cred_manager)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if self.model_name.startswith("mock"):
            return f"[Claude: {self.model_name}] Response to prompt."

        api_key = self._get_api_key()
        url = f"{self.config.base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.config.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            res_bytes = await self.transport.request(
                "POST",
                url,
                headers,
                json.dumps(payload).encode("utf-8"),
                self.config.timeout,
            )
            data = json.loads(res_bytes.decode("utf-8"))
            text = data["content"][0]["text"]
            self.record_success()
            return str(text)
        except Exception as err:
            self.record_failure()
            self._handle_error(err)
            raise

    async def stream_generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        if self.model_name.startswith("mock"):
            return _mock_stream(self.name, self.model_name)

        api_key = self._get_api_key()
        url = f"{self.config.base_url}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.config.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async def generator() -> AsyncIterator[str]:
            try:
                stream = await self.transport.stream_request(
                    "POST",
                    url,
                    headers,
                    json.dumps(payload).encode("utf-8"),
                    self.config.timeout,
                )
                async for chunk in stream:
                    lines = chunk.decode("utf-8").split("\n")
                    for line in lines:
                        line = line.strip()
                        if line.startswith("data:"):
                            data_json = line[5:].strip()
                            if data_json == "[DONE]":
                                break
                            try:
                                data = json.loads(data_json)
                                if (
                                    data.get("type") == "content_block_delta"
                                    and "delta" in data
                                ):
                                    yield data["delta"].get("text", "")
                            except Exception:
                                pass
                self.record_success()
            except Exception as err:
                self.record_failure()
                self._handle_error(err)
                raise

        return generator()

    def _handle_error(self, err: Exception) -> None:
        if isinstance(err, ModelProviderError):
            raise err
        raise TransportError(
            code="CLAUDE_ERR",
            message=f"Claude API request failed: {err}",
        ) from err


class OpenAIProvider(IModelProvider):
    """OpenAI GPT model provider implementation."""

    def __init__(
        self,
        config: Optional[ProviderConfig] = None,
        transport: Optional[IHttpTransport] = None,
        cred_manager: Optional[CredentialManager] = None,
    ) -> None:
        cfg = config or ProviderConfig(
            provider_name="openai",
            model_name="gpt-4o",
            base_url="https://api.openai.com/v1",
            max_context_tokens=128000,
            max_output_tokens=4096,
        )
        super().__init__(cfg, transport, cred_manager)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if self.model_name.startswith("mock"):
            return f"[OpenAI: {self.model_name}] Response to prompt."

        api_key = self._get_api_key()
        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.config.max_output_tokens,
        }

        try:
            res_bytes = await self.transport.request(
                "POST",
                url,
                headers,
                json.dumps(payload).encode("utf-8"),
                self.config.timeout,
            )
            data = json.loads(res_bytes.decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            self.record_success()
            return str(text)
        except Exception as err:
            self.record_failure()
            self._handle_error(err)
            raise

    async def stream_generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        if self.model_name.startswith("mock"):
            return _mock_stream(self.name, self.model_name)

        api_key = self._get_api_key()
        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.config.max_output_tokens,
            "stream": True,
        }

        async def generator() -> AsyncIterator[str]:
            try:
                stream = await self.transport.stream_request(
                    "POST",
                    url,
                    headers,
                    json.dumps(payload).encode("utf-8"),
                    self.config.timeout,
                )
                async for chunk in stream:
                    lines = chunk.decode("utf-8").split("\n")
                    for line in lines:
                        line = line.strip()
                        if line.startswith("data:"):
                            data_json = line[5:].strip()
                            if data_json == "[DONE]":
                                break
                            try:
                                data = json.loads(data_json)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                            except Exception:
                                pass
                self.record_success()
            except Exception as err:
                self.record_failure()
                self._handle_error(err)
                raise

        return generator()

    def _handle_error(self, err: Exception) -> None:
        if isinstance(err, ModelProviderError):
            raise err
        raise TransportError(
            code="OPENAI_ERR",
            message=f"OpenAI API request failed: {err}",
        ) from err


class QwenProvider(IModelProvider):
    """Local Qwen model provider implementation (Ollama baseline)."""

    def __init__(
        self,
        config: Optional[ProviderConfig] = None,
        transport: Optional[IHttpTransport] = None,
        cred_manager: Optional[CredentialManager] = None,
    ) -> None:
        cfg = config or ProviderConfig(
            provider_name="qwen",
            model_name="qwen-2.5-coder",
            base_url="http://localhost:11434/api",
            max_context_tokens=32000,
            max_output_tokens=4096,
            supports_vision=False,
        )
        super().__init__(cfg, transport, cred_manager)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if self.model_name.startswith("mock"):
            return f"[Qwen: {self.model_name}] Response to prompt."

        url = f"{self.config.base_url}/chat"
        headers = {"Content-Type": "application/json"}

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
        }

        try:
            res_bytes = await self.transport.request(
                "POST",
                url,
                headers,
                json.dumps(payload).encode("utf-8"),
                self.config.timeout,
            )
            data = json.loads(res_bytes.decode("utf-8"))
            text = data["message"]["content"]
            self.record_success()
            return str(text)
        except Exception as err:
            self.record_failure()
            self._handle_error(err)
            raise

    async def stream_generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        if self.model_name.startswith("mock"):
            return _mock_stream(self.name, self.model_name)

        url = f"{self.config.base_url}/chat"
        headers = {"Content-Type": "application/json"}

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
        }

        async def generator() -> AsyncIterator[str]:
            try:
                stream = await self.transport.stream_request(
                    "POST",
                    url,
                    headers,
                    json.dumps(payload).encode("utf-8"),
                    self.config.timeout,
                )
                async for chunk in stream:
                    lines = chunk.decode("utf-8").split("\n")
                    for line in lines:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                if "message" in data and "content" in data["message"]:
                                    yield data["message"]["content"]
                            except Exception:
                                pass
                self.record_success()
            except Exception as err:
                self.record_failure()
                self._handle_error(err)
                raise

        return generator()

    def _handle_error(self, err: Exception) -> None:
        if isinstance(err, ModelProviderError):
            raise err
        raise TransportError(
            code="QWEN_ERR",
            message=f"Qwen local API request failed: {err}",
        ) from err


class LlamaProvider(IModelProvider):
    """Local Llama model provider implementation (Ollama baseline)."""

    def __init__(
        self,
        config: Optional[ProviderConfig] = None,
        transport: Optional[IHttpTransport] = None,
        cred_manager: Optional[CredentialManager] = None,
    ) -> None:
        cfg = config or ProviderConfig(
            provider_name="llama",
            model_name="llama-3-8b",
            base_url="http://localhost:11434/api",
            max_context_tokens=16000,
            max_output_tokens=4096,
            supports_tools=False,
            supports_vision=False,
        )
        super().__init__(cfg, transport, cred_manager)

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if self.model_name.startswith("mock"):
            return f"[Llama: {self.model_name}] Response to prompt."

        url = f"{self.config.base_url}/chat"
        headers = {"Content-Type": "application/json"}

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
        }

        try:
            res_bytes = await self.transport.request(
                "POST",
                url,
                headers,
                json.dumps(payload).encode("utf-8"),
                self.config.timeout,
            )
            data = json.loads(res_bytes.decode("utf-8"))
            text = data["message"]["content"]
            self.record_success()
            return str(text)
        except Exception as err:
            self.record_failure()
            self._handle_error(err)
            raise

    async def stream_generate(
        self, prompt: str, system_prompt: Optional[str] = None
    ) -> AsyncIterator[str]:
        if self.model_name.startswith("mock"):
            return _mock_stream(self.name, self.model_name)

        url = f"{self.config.base_url}/chat"
        headers = {"Content-Type": "application/json"}

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
        }

        async def generator() -> AsyncIterator[str]:
            try:
                stream = await self.transport.stream_request(
                    "POST",
                    url,
                    headers,
                    json.dumps(payload).encode("utf-8"),
                    self.config.timeout,
                )
                async for chunk in stream:
                    lines = chunk.decode("utf-8").split("\n")
                    for line in lines:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                if "message" in data and "content" in data["message"]:
                                    yield data["message"]["content"]
                            except Exception:
                                pass
                self.record_success()
            except Exception as err:
                self.record_failure()
                self._handle_error(err)
                raise

        return generator()

    def _handle_error(self, err: Exception) -> None:
        if isinstance(err, ModelProviderError):
            raise err
        raise TransportError(
            code="LLAMA_ERR",
            message=f"Llama local API request failed: {err}",
        ) from err
