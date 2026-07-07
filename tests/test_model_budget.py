"""JARVIS OS - Model Providers & Budgeting Tests.

Verifies HTTP transports, streaming generation, circuit breakers, cost governors, capability routing, rate limiters, and telemetry.
"""

import asyncio
import json
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Optional, cast
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.exceptions import (
    AuthenticationError,
    BudgetExceededError,
    JarvisSystemError,
    RateLimitError,
    TimeoutError,
    TransportError,
)
from core.interfaces import InterAgentMessage
from core.memory.models import APIBillingLog, Base
from core.reasoning.cost import CostGovernor
from core.reasoning.health_monitor import ProviderHealthMonitor
from core.reasoning.provider import (
    ClaudeProvider,
    GeminiProvider,
    IModelProvider,
    LlamaProvider,
    ModelHealthStatus,
    OpenAIProvider,
    ProviderConfig,
    QwenProvider,
)
from core.reasoning.rate_limiter import ProviderRateLimiter
from core.reasoning.registry import ModelCapabilityRegistry
from core.reasoning.router import ModelRouter
from core.reasoning.telemetry import ReasoningTelemetry
from core.reasoning.token_counter import TokenCounter
from core.reasoning.transport import IHttpTransport, UrllibTransport


class MockTransport(IHttpTransport):
    """Mock implementation of IHttpTransport to intercept requests in tests."""

    def __init__(
        self,
        response_bytes: bytes = b"{}",
        stream_chunks: Optional[List[bytes]] = None,
        should_fail_with: Optional[Exception] = None,
    ) -> None:
        self.response_bytes = response_bytes
        self.stream_chunks = stream_chunks or []
        self.should_fail_with = should_fail_with
        self.last_request: Optional[Dict[str, Any]] = None

    async def request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Optional[bytes] = None,
        timeout: float = 30.0,
    ) -> bytes:
        self.last_request = {
            "method": method,
            "url": url,
            "headers": headers,
            "data": data,
            "timeout": timeout,
        }
        if self.should_fail_with:
            raise self.should_fail_with
        return self.response_bytes

    async def stream_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Optional[bytes] = None,
        timeout: float = 30.0,
    ) -> AsyncIterator[bytes]:
        self.last_request = {
            "method": method,
            "url": url,
            "headers": headers,
            "data": data,
            "timeout": timeout,
        }
        if self.should_fail_with:
            raise self.should_fail_with

        async def generator() -> AsyncIterator[bytes]:
            for chunk in self.stream_chunks:
                yield chunk

        return generator()


@pytest.fixture
def settings() -> Settings:
    return Settings.load_settings()


@pytest.fixture
async def async_db_session() -> AsyncIterator[AsyncSession]:
    """Create in-memory SQLite database session for persistent billing log tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_urllib_transport_request_mapping() -> None:
    """Verify UrllibTransport correctly maps standard HTTP status errors."""
    transport = UrllibTransport()

    # 401 Unauthorized -> AuthenticationError
    err_401 = urllib.error.HTTPError(
        "http://api.test", 401, "Unauthorized", cast(Any, {}), cast(Any, MagicMock())
    )
    with pytest.raises(AuthenticationError):
        transport._map_http_error(err_401)

    # 429 Too Many Requests -> RateLimitError
    err_429 = urllib.error.HTTPError(
        "http://api.test",
        429,
        "Too Many Requests",
        cast(Any, {}),
        cast(Any, MagicMock()),
    )
    with pytest.raises(RateLimitError):
        transport._map_http_error(err_429)

    # 500 Server Error -> TransportError
    err_500 = urllib.error.HTTPError(
        "http://api.test",
        500,
        "Internal Server Error",
        cast(Any, {}),
        cast(Any, MagicMock()),
    )
    with pytest.raises(TransportError):
        transport._map_http_error(err_500)


@pytest.mark.asyncio
async def test_model_providers_generation_and_streaming() -> None:
    """Verify Gemini, Claude, OpenAI, and Ollama providers send payloads and parse responses correctly."""
    # 1. Gemini
    gemini_resp = {
        "candidates": [{"content": {"parts": [{"text": "Gemini response text"}]}}]
    }
    transport = MockTransport(response_bytes=json.dumps(gemini_resp).encode("utf-8"))
    provider = GeminiProvider(transport=transport)
    res = await provider.generate("Hello Gemini")
    assert res == "Gemini response text"

    # 2. Claude
    claude_resp = {"content": [{"type": "text", "text": "Claude response text"}]}
    transport_claude = MockTransport(
        response_bytes=json.dumps(claude_resp).encode("utf-8")
    )
    provider_claude = ClaudeProvider(transport=transport_claude)
    res_claude = await provider_claude.generate("Hello Claude")
    assert res_claude == "Claude response text"

    # 3. OpenAI
    openai_resp = {
        "choices": [
            {"message": {"role": "assistant", "content": "OpenAI response text"}}
        ]
    }
    transport_openai = MockTransport(
        response_bytes=json.dumps(openai_resp).encode("utf-8")
    )
    provider_openai = OpenAIProvider(transport=transport_openai)
    res_openai = await provider_openai.generate("Hello OpenAI")
    assert res_openai == "OpenAI response text"

    # 4. Ollama (Qwen)
    qwen_resp = {"message": {"role": "assistant", "content": "Qwen response text"}}
    transport_qwen = MockTransport(response_bytes=json.dumps(qwen_resp).encode("utf-8"))
    provider_qwen = QwenProvider(transport=transport_qwen)
    res_qwen = await provider_qwen.generate("Hello Qwen")
    assert res_qwen == "Qwen response text"

    # 5. Ollama (Llama)
    llama_resp = {"message": {"role": "assistant", "content": "Llama response text"}}
    transport_llama = MockTransport(
        response_bytes=json.dumps(llama_resp).encode("utf-8")
    )
    provider_llama = LlamaProvider(transport=transport_llama)
    res_llama = await provider_llama.generate("Hello Llama")
    assert res_llama == "Llama response text"
    assert provider_llama.supports_tools() is False


@pytest.mark.asyncio
async def test_model_providers_streaming_sse() -> None:
    """Verify streaming chunks are read and yield plain text correctly."""
    # Claude SSE stream
    chunks = [
        b'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}\n',
        b'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " world"}}\n',
        b"data: [DONE]\n",
    ]
    transport = MockTransport(stream_chunks=chunks)
    provider = ClaudeProvider(transport=transport)

    stream = await provider.stream_generate("Hello Claude")
    res = []
    async for item in stream:
        res.append(item)
    assert "".join(res) == "Hello world"

    # OpenAI SSE stream
    openai_chunks = [
        b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n',
        b'data: {"choices": [{"delta": {"content": " world"}}]}\n',
        b"data: [DONE]\n",
    ]
    openai_trans = MockTransport(stream_chunks=openai_chunks)
    openai_prov = OpenAIProvider(transport=openai_trans)
    openai_stream = await openai_prov.stream_generate("Hello OpenAI")
    openai_res = []
    async for item in openai_stream:
        openai_res.append(item)
    assert "".join(openai_res) == "Hello world"

    # Gemini stream
    gemini_chunks = [
        b'{"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}',
        b'{"candidates": [{"content": {"parts": [{"text": " world"}]}}]}',
    ]
    gemini_trans = MockTransport(stream_chunks=gemini_chunks)
    gemini_prov = GeminiProvider(transport=gemini_trans)
    gemini_stream = await gemini_prov.stream_generate("Hello Gemini")
    gemini_res = []
    async for item in gemini_stream:
        gemini_res.append(item)
    assert "".join(gemini_res) == "Hello world"

    # Ollama stream
    qwen_chunks = [
        b'{"message": {"content": "Hello"}, "done": false}',
        b'{"message": {"content": " world"}, "done": true}',
    ]
    qwen_trans = MockTransport(stream_chunks=qwen_chunks)
    qwen_prov = QwenProvider(transport=qwen_trans)
    qwen_stream = await qwen_prov.stream_generate("Hello Qwen")
    qwen_res = []
    async for item in qwen_stream:
        qwen_res.append(item)
    assert "".join(qwen_res) == "Hello world"


@pytest.mark.asyncio
async def test_provider_circuit_breaker() -> None:
    """Verify provider circuit breaker changes status after failures and enters cooldown."""
    transport = MockTransport(should_fail_with=Exception("API failure"))
    provider: IModelProvider = ClaudeProvider(transport=transport)

    assert getattr(provider, "health_status") == ModelHealthStatus.ONLINE

    # First fail -> COOLDOWN
    with pytest.raises(Exception):
        await provider.generate("test")
    assert getattr(provider, "health_status") == ModelHealthStatus.COOLDOWN

    # Fail 5 times -> OFFLINE
    for _ in range(4):
        with pytest.raises(Exception):
            await provider.generate("test")
    assert getattr(provider, "health_status") == ModelHealthStatus.OFFLINE

    # success reset -> ONLINE
    provider.record_success()
    assert getattr(provider, "health_status") == ModelHealthStatus.ONLINE


@pytest.mark.asyncio
async def test_token_counter_estimation() -> None:
    """Verify TokenCounter estimates context blocks using correct multipliers."""
    counter = TokenCounter()
    text = "Hello world context check"

    # Gemini: 4 words * 1.3 = 5
    assert counter.count_tokens(text, "gemini") == 5

    # OpenAI: 4 words * 1.4 = 5
    assert counter.count_tokens(text, "openai") == 5

    # Empty text -> 0
    assert counter.count_tokens("", "gemini") == 0


@pytest.mark.asyncio
async def test_cost_governor_persistent_limits(async_db_session: AsyncSession) -> None:
    """Verify CostGovernor tallies spending inside DB and checks daily/monthly bounds."""
    settings = Settings.load_settings()
    gov = CostGovernor(settings, db_session=async_db_session)

    # Reset cache to force DB evaluation
    gov.reset_spending()

    # Log some token cost
    cost = await gov.log_usage(1000, 2000, "openai", "gpt-4o")
    # pricing gpt-4o input $0.0015 / 1k, output $0.0075 / 1k -> total cost = 1.0 * 0.0015 + 2.0 * 0.0075 = $0.0165
    assert cost == Decimal("0.0165")

    # Verify log row was persisted in DB
    stmt = select(APIBillingLog)
    res = await async_db_session.execute(stmt)
    rows = res.scalars().all()
    assert len(rows) == 1
    assert rows[0].prompt_tokens == 1000
    assert rows[0].cost == Decimal("0.0165")

    # Check budget check passes
    await gov.check_budget_limits(Decimal("0.10"))

    # Test single request per-call limit ($0.50 threshold)
    with pytest.raises(JarvisSystemError) as excinfo_system:
        await gov.check_budget_limits(Decimal("0.60"))
    assert excinfo_system.value.code == "BUDGET_PER_CALL_EXCEEDED"

    # Mock daily budget exhaustion
    gov.daily_budget = Decimal("0.01")
    with pytest.raises(BudgetExceededError) as excinfo_budget:
        await gov.check_budget_limits(Decimal("0.02"))
    assert excinfo_budget.value.code == "BUDGET_DAILY_EXHAUSTED"


@pytest.mark.asyncio
async def test_capability_registry_routing() -> None:
    """Verify registry ranks providers and filters by requirements like vision."""
    registry = ModelCapabilityRegistry()

    # Register configs
    registry.register_provider_config(
        ProviderConfig(
            provider_name="gemini",
            model_name="gemini-1.5-pro",
            base_url="https://gemini.api",
            supports_vision=True,
        )
    )
    registry.register_provider_config(
        ProviderConfig(
            provider_name="qwen",
            model_name="qwen-2.5-coder",
            base_url="http://localhost:11434/api",
            supports_vision=False,
        )
    )

    # Rank for Planning category (default claude, gemini, etc.)
    candidates = registry.get_best_providers_for_task("Planning")
    # Only registered providers are returned
    assert "gemini" in candidates
    assert "qwen" in candidates

    # Rank for Vision (should exclude Qwen since it does not support vision)
    vision_candidates = registry.get_best_providers_for_task(
        "Vision", require_vision=True
    )
    assert "gemini" in vision_candidates
    assert "qwen" not in vision_candidates


@pytest.mark.asyncio
async def test_provider_rate_limiter() -> None:
    """Verify ProviderRateLimiter checks RPM, TPM and concurrent request counters."""
    limiter = ProviderRateLimiter(
        default_rpm=2, default_tpm=1000, default_max_concurrent=2
    )

    # 1. Concurrency limit
    limiter.increment_concurrent("gemini")
    limiter.increment_concurrent("gemini")
    with pytest.raises(RateLimitError):
        limiter.check_rate_limits("gemini", 100)

    limiter.decrement_concurrent("gemini")
    limiter.check_rate_limits("gemini", 100)  # Now passes

    # 2. RPM limit
    limiter.record_request("gemini", 100)
    limiter.record_request("gemini", 100)
    with pytest.raises(RateLimitError):
        limiter.check_rate_limits("gemini", 100)

    # 3. TPM limit
    limiter.reset("gemini")
    limiter.record_request("gemini", 950)
    with pytest.raises(RateLimitError):
        limiter.check_rate_limits("gemini", 100)


@pytest.mark.asyncio
async def test_reasoning_telemetry_event_bus() -> None:
    """Verify ReasoningTelemetry formats and publishes inter-agent messages."""
    event_bus = MemoryEventBus()
    telemetry = ReasoningTelemetry(event_bus)

    events: List[InterAgentMessage] = []

    async def callback(msg: InterAgentMessage) -> None:
        events.append(msg)

    await event_bus.initialize()
    await event_bus.start()
    await event_bus.subscribe("reasoning.telemetry.provider.started", callback)

    success = await telemetry.publish_event(
        "provider.started", "claude", "claude-3-5-sonnet"
    )
    assert success is True

    # Yield control to let event bus process callback
    await asyncio.sleep(0.01)
    assert len(events) == 1
    assert events[0].action == "provider.started"
    assert events[0].body["provider_name"] == "claude"
    await event_bus.stop()


@pytest.mark.asyncio
async def test_model_router_fallbacks_and_retries(
    async_db_session: AsyncSession,
) -> None:
    """Verify ModelRouter retries failing providers and falls back to local models."""
    settings = Settings.load_settings()

    # Providers
    gemini_resp = {"candidates": [{"content": {"parts": [{"text": "Gemini answer"}]}}]}
    gemini_trans = MockTransport(response_bytes=json.dumps(gemini_resp).encode("utf-8"))
    gemini = GeminiProvider(transport=gemini_trans)

    # Qwen (local fallback)
    qwen_resp = {
        "message": {"role": "assistant", "content": "Qwen local fallback answer"}
    }
    qwen_trans = MockTransport(response_bytes=json.dumps(qwen_resp).encode("utf-8"))
    qwen = QwenProvider(transport=qwen_trans)

    # Registry
    registry = ModelCapabilityRegistry()
    registry.register_provider_config(gemini.config)
    registry.register_provider_config(qwen.config)

    limiter = ProviderRateLimiter()
    telemetry = ReasoningTelemetry()
    cost_gov = CostGovernor(settings, db_session=async_db_session)

    router = ModelRouter(
        providers=[gemini, qwen],
        registry=registry,
        rate_limiter=limiter,
        telemetry=telemetry,
        cost_gov=cost_gov,
        settings=settings,
    )

    # 1. Standard execution path
    res = await router.execute_with_retry("Planning", "Task prompt")
    assert res == "Gemini answer"

    # 2. Mock Gemini fail to trigger failover to Qwen
    gemini_trans.should_fail_with = Exception("Gemini API down")
    res_fallback = await router.execute_with_retry("Planning", "Task prompt")
    # Gemini fails, router tries fallback (Qwen)
    assert res_fallback == "Qwen local fallback answer"


@pytest.mark.asyncio
async def test_provider_health_monitor() -> None:
    """Verify ProviderHealthMonitor background check loop transitions provider status."""
    transport = MockTransport(should_fail_with=Exception("Temp error"))
    provider: IModelProvider = ClaudeProvider(transport=transport)

    monitor = ProviderHealthMonitor([provider])

    # Transition provider to OFFLINE
    provider.health_status = ModelHealthStatus.OFFLINE

    # Run check_all_providers -> still fails
    await monitor.check_all_providers()
    assert getattr(provider, "health_status") == ModelHealthStatus.OFFLINE

    # Now make it succeed
    transport.should_fail_with = None
    transport.response_bytes = b'{"content": [{"type": "text", "text": "pong"}]}'

    await monitor.check_all_providers()
    # Health check succeeds -> ONLINE
    assert getattr(provider, "health_status") == ModelHealthStatus.ONLINE

    # Verify background daemon validation loop
    await monitor.start_monitoring(interval_seconds=0.001)
    assert monitor.is_monitoring is True
    # Verify early exit branch when already monitoring
    await monitor.start_monitoring(interval_seconds=0.001)
    await asyncio.sleep(0.005)
    await monitor.stop_monitoring()
    assert monitor.is_monitoring is False


@pytest.mark.asyncio
async def test_urllib_transport_coverage() -> None:
    """Exercise all branch conditions in UrllibTransport (request and stream_request)."""
    import builtins

    transport = UrllibTransport()

    # 1. Success request
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"success-data"
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = await transport.request("POST", "http://test.api", {}, b"data")
        assert res == b"success-data"

    # 2. HTTPError
    mock_http_err = urllib.error.HTTPError(
        "http://test.api", 401, "Unauthorized", cast(Any, {}), cast(Any, MagicMock())
    )
    setattr(mock_http_err, "read", MagicMock(return_value=b"unauthorized payload"))
    with patch("urllib.request.urlopen", side_effect=mock_http_err):
        with pytest.raises(AuthenticationError):
            await transport.request("POST", "http://test.api", {}, b"data")

    # 3. URLError
    mock_url_err = urllib.error.URLError("reason string")
    with patch("urllib.request.urlopen", side_effect=mock_url_err):
        with pytest.raises(TransportError) as excinfo:
            await transport.request("POST", "http://test.api", {}, b"data")
        assert excinfo.value.code == "TRANS_001"

    # 4. TimeoutError
    with patch("urllib.request.urlopen", side_effect=builtins.TimeoutError()):
        with pytest.raises(TimeoutError) as excinfo_timeout:
            await transport.request("POST", "http://test.api", {}, b"data")
        assert excinfo_timeout.value.code == "TRANS_002"

    # 5. Generic Exception
    with patch("urllib.request.urlopen", side_effect=RuntimeError("unknown error")):
        with pytest.raises(TransportError) as excinfo_err:
            await transport.request("POST", "http://test.api", {}, b"data")
        assert excinfo_err.value.code == "TRANS_999"

    # 6. Stream request success and failure branches
    mock_stream_resp = MagicMock()
    mock_stream_resp.read.side_effect = [b"stream-chunk", b""]
    mock_stream_resp.__enter__.return_value = mock_stream_resp

    with patch("urllib.request.urlopen", return_value=mock_stream_resp):
        it = await transport.stream_request("POST", "http://test.api", {}, b"data")
        chunks = []
        async for chunk in it:
            chunks.append(chunk)
        assert chunks == [b"stream-chunk"]

    # stream request HTTPError
    with patch("urllib.request.urlopen", side_effect=mock_http_err):
        it = await transport.stream_request("POST", "http://test.api", {}, b"data")
        with pytest.raises(AuthenticationError):
            async for chunk in it:
                pass

    # stream request URLError
    with patch("urllib.request.urlopen", side_effect=mock_url_err):
        it = await transport.stream_request("POST", "http://test.api", {}, b"data")
        with pytest.raises(TransportError):
            async for chunk in it:
                pass

    # stream request TimeoutError
    with patch("urllib.request.urlopen", side_effect=builtins.TimeoutError()):
        it = await transport.stream_request("POST", "http://test.api", {}, b"data")
        with pytest.raises(TimeoutError):
            async for chunk in it:
                pass

    # stream request Generic Exception
    with patch("urllib.request.urlopen", side_effect=RuntimeError("unknown error")):
        it = await transport.stream_request("POST", "http://test.api", {}, b"data")
        with pytest.raises(TransportError):
            async for chunk in it:
                pass


@pytest.mark.asyncio
async def test_model_router_extensive_coverage(async_db_session: AsyncSession) -> None:
    """Verify router fallback branches, daily budget redirect, and rate limit telemetry."""
    settings = Settings.load_settings()

    # Providers
    gemini_resp = {"candidates": [{"content": {"parts": [{"text": "Gemini content"}]}}]}
    gemini_trans = MockTransport(response_bytes=json.dumps(gemini_resp).encode("utf-8"))
    gemini = GeminiProvider(transport=gemini_trans)

    qwen_resp = {"message": {"role": "assistant", "content": "Qwen content"}}
    qwen_trans = MockTransport(response_bytes=json.dumps(qwen_resp).encode("utf-8"))
    qwen = QwenProvider(transport=qwen_trans)

    # 1. Budget exhaustion redirect to local models only
    import time

    cost_gov = CostGovernor(settings)
    cost_gov.cached_daily_spending = Decimal("10.01")  # Daily budget breached
    cost_gov.last_cache_time = time.time()  # Force cache usage

    registry = ModelCapabilityRegistry()
    registry.register_provider_config(gemini.config)
    registry.register_provider_config(qwen.config)

    # Register an unknown candidate provider config to test line 78 in router.py
    unknown_config = ProviderConfig(
        provider_name="unknown-prov",
        model_name="unknown-model",
        base_url="http://unknown",
    )
    registry.register_provider_config(unknown_config)
    # Add suitability ranking for unknown-prov
    registry.capability_scores["Planning"]["unknown-prov"] = 100

    limiter = ProviderRateLimiter()
    telemetry = ReasoningTelemetry()

    router = ModelRouter(
        providers=[gemini, qwen],
        registry=registry,
        rate_limiter=limiter,
        telemetry=telemetry,
        cost_gov=cost_gov,
        settings=settings,
    )

    # Gemini is planning, qwen is coding/local. Because budget is exhausted, router filters out gemini.
    provider = await router.get_provider_for_task("Planning")
    assert provider.name == "qwen"  # falls back to local provider qwen

    # Test cost_gov._get_current_spending raising exception (lines 66-67 cover)
    async def mock_fail_spending() -> tuple[Decimal, Decimal]:
        raise RuntimeError("DB failed")

    cost_gov._get_current_spending = mock_fail_spending  # type: ignore[method-assign]
    # Should not raise exception
    await router.get_provider_for_task("Planning")

    # 2. Concurrency / Rate limit fallback (lines 95-102 cover)
    limiter.configure_provider("qwen", rpm=1, tpm=10, max_concurrent=0)  # Concurrency 0
    # Since Qwen has rate limit issues, it should skip it. Let's make gemini healthy and check.
    cost_gov.cached_daily_spending = Decimal("0.0")  # reset budget
    # gemini should be picked because qwen is rate-limited
    provider_picked = await router.get_provider_for_task("Planning")
    assert provider_picked.name == "gemini"

    # 3. Router retry failed exception
    gemini_trans.should_fail_with = Exception("Gemini Down")
    qwen_trans.should_fail_with = Exception("Qwen Down")
    router.max_retries = 1
    router.retry_backoffs = [0.001]

    with pytest.raises(Exception):
        await router.execute_with_retry("Planning", "test prompt")


@pytest.mark.asyncio
async def test_credential_manager_edge_cases() -> None:
    """Verify credential manager fallbacks for unknown providers."""
    from core.reasoning.credentials import CredentialManager

    cm = CredentialManager()
    # Test random provider
    key = cm.get_api_key("NON_EXISTENT_LLM_PROVIDER")
    assert key == ""


@pytest.mark.asyncio
async def test_registry_telemetry_health_monitor_edge_cases() -> None:
    """Verify registry configs, telemetry exception paths, and health monitor error handlers."""
    # 1. Registry config query
    registry = ModelCapabilityRegistry()
    config = ProviderConfig(
        provider_name="test-prov",
        model_name="test-model",
        base_url="http://test.api",
    )
    registry.register_provider_config(config)
    retrieved = registry.get_provider_config("test-prov")
    assert retrieved is not None
    assert retrieved.model_name == "test-model"

    # Test query on missing config
    assert registry.get_provider_config("missing-prov") is None

    # 2. Telemetry publish exception
    class MockFailingEventBus:
        async def publish(self, topic: str, message: Any) -> bool:
            raise RuntimeError("Bus failure")

    telemetry = ReasoningTelemetry(event_bus=cast(Any, MockFailingEventBus()))
    res = await telemetry.publish_event("action", "provider", "model")
    assert res is False

    # 3. Health monitor background loop exception
    class MockFailingProvider(ClaudeProvider):
        async def health_check(self) -> ModelHealthStatus:
            raise RuntimeError("Health check failure")

    prov = MockFailingProvider(config=config)
    monitor = ProviderHealthMonitor([prov])
    # Run loop once - should handle exception gracefully
    await monitor.start_monitoring(interval_seconds=0.001)
    await asyncio.sleep(0.005)
    await monitor.stop_monitoring()


@pytest.mark.asyncio
async def test_provider_edge_cases() -> None:
    """Verify Gemini, Claude, OpenAI, Qwen, Llama error paths for malformed JSON, empty response, and UTF-8 decoder failure."""
    # 1. Claude Malformed JSON
    transport_malformed = MockTransport(response_bytes=b"malformed json content")
    claude = ClaudeProvider(transport=transport_malformed)
    with pytest.raises(TransportError):
        await claude.generate("hello")

    # 2. Claude Empty response
    transport_empty = MockTransport(response_bytes=b"")
    claude_empty = ClaudeProvider(transport=transport_empty)
    with pytest.raises(TransportError):
        await claude_empty.generate("hello")

    # 3. Claude Malformed Stream (broken JSON chunk)
    stream_chunks = [b"data: {invalid-json}\n", b"data: [DONE]\n"]
    transport_stream = MockTransport(stream_chunks=stream_chunks)
    claude_stream = ClaudeProvider(transport=transport_stream)
    stream = await claude_stream.stream_generate("hello")
    chunks = [chunk async for chunk in stream]
    assert len(chunks) == 0  # Ignore malformed chunk without crash

    # 4. Gemini Malformed JSON
    gemini = GeminiProvider(transport=transport_malformed)
    with pytest.raises(TransportError):
        await gemini.generate("hello")

    # 5. Gemini Stream Malformed JSON
    gemini_stream_trans = MockTransport(stream_chunks=[b"{malformed}"])
    gemini_stream = GeminiProvider(transport=gemini_stream_trans)
    stream = await gemini_stream.stream_generate("hello")
    chunks = [chunk async for chunk in stream]
    assert len(chunks) == 0

    # 6. OpenAI Malformed JSON
    openai = OpenAIProvider(transport=transport_malformed)
    with pytest.raises(TransportError):
        await openai.generate("hello")

    # 7. OpenAI Stream Malformed JSON
    openai_stream_trans = MockTransport(stream_chunks=[b"data: {malformed}\n"])
    openai_stream = OpenAIProvider(transport=openai_stream_trans)
    stream = await openai_stream.stream_generate("hello")
    chunks = [chunk async for chunk in stream]
    assert len(chunks) == 0

    # 8. Qwen Malformed JSON
    qwen = QwenProvider(transport=transport_malformed)
    with pytest.raises(TransportError):
        await qwen.generate("hello")

    # 9. Qwen Stream Malformed JSON
    qwen_stream_trans = MockTransport(stream_chunks=[b"{malformed}\n"])
    qwen_stream = QwenProvider(transport=qwen_stream_trans)
    stream = await qwen_stream.stream_generate("hello")
    chunks = [chunk async for chunk in stream]
    assert len(chunks) == 0

    # 10. Llama Malformed JSON
    llama = LlamaProvider(transport=transport_malformed)
    with pytest.raises(TransportError):
        await llama.generate("hello")

    # 11. Llama Stream Malformed JSON
    llama_stream_trans = MockTransport(stream_chunks=[b"{malformed}\n"])
    llama_stream = LlamaProvider(transport=llama_stream_trans)
    stream = await llama_stream.stream_generate("hello")
    chunks = [chunk async for chunk in stream]
    assert len(chunks) == 0
