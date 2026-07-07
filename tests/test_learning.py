"""JARVIS OS - Learning Engine Unit & Integration Tests.

Verifies domain trust allowlists, HTML parser extractions, context summaries, graph entity mappings,
stale node invalidations, refresh pipelines, and REST API route handlers.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import Settings
from core.events.memory_bus import MemoryEventBus
from core.exceptions import JarvisAgentError
from core.learning.extractor import EntityExtractor
from core.learning.routes import learning_router, set_learning_service
from core.learning.scraper import DocumentScraper, HTMLContentExtractor
from core.learning.service import LearningService
from core.learning.summarizer import ContextSummarizer
from core.memory.database import db_manager
from core.memory.embeddings import MockEmbeddingGenerator
from core.memory.graph import PostgresKnowledgeGraphRepository
from core.memory.interfaces import MemoryNode
from core.memory.models import Base
from core.memory.repository import PostgresMemoryRepository
from core.memory.service import MemoryService
from core.memory.vector_store import InMemoryVectorRepository


def test_html_content_extractor() -> None:
    """Verify HTMLContentExtractor cleans tags and preserves code/pre formats."""
    html = """
    <html>
        <head><style>body { color: red; }</style></head>
        <body>
            <nav>Menu item</nav>
            <h1>Playwright Introduction</h1>
            <p>Playwright enables reliable end-to-end testing.</p>
            <pre><code>import playwright</code></pre>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    """
    extractor = HTMLContentExtractor()
    extractor.feed(html)
    payload = extractor.get_clean_payload()

    assert "Playwright Introduction" in payload
    assert "Menu item" not in payload
    assert "Copyright 2026" not in payload
    assert "import playwright" in payload


def test_scraper_url_validation() -> None:
    """Verify scraper gates untrusted domains and parses valid targets."""
    scraper = DocumentScraper()

    # Allowed
    assert scraper.validate_url("https://playwright.dev/docs/intro") == "playwright.dev"
    assert scraper.validate_url("https://python.org/downloads") == "python.org"
    assert scraper.validate_url("http://github.com/microsoft") == "github.com"

    # Blocked
    with pytest.raises(JarvisAgentError) as excinfo:
        scraper.validate_url("https://malicious-site.com/hack")
    assert excinfo.value.code == "AGENT_002"
    assert "Unauthorized domain block" in excinfo.value.message


@pytest.mark.asyncio
async def test_context_summarizer() -> None:
    """Verify summarizer retains technical code definitions and overview context."""
    text = """
    Playwright library allows scraping.
    It provides click actions.
    def click_element(selector):
        print("Clicking")
    ```python
    import playwright
    ```
    An error occurred. Exception raised.
    """
    summarizer = ContextSummarizer()
    summary = await summarizer.summarize(text)

    assert "Technical Overview" in summary
    assert "click_element" in summary
    assert "import playwright" in summary


@pytest.mark.asyncio
async def test_entity_extractor() -> None:
    """Verify EntityExtractor resolves nodes and relationship maps."""
    text = "We use Playwright and browser options to perform scraping on website APIs."
    extractor = EntityExtractor()

    # Entities
    entities = await extractor.extract_entities(text)
    entity_names = {e.name.lower() for e in entities}
    assert "playwright" in entity_names
    assert "browser" in entity_names
    assert "scraping" in entity_names
    assert "api" in entity_names

    # Relations
    relations = await extractor.extract_relations(entities, text)
    rel_types = {r.relation_type for r in relations}
    assert "depends_on" in rel_types
    assert "references" in rel_types


@pytest.mark.asyncio
async def test_learning_service_ingest_and_watchdog() -> None:
    """Verify end-to-end URL ingestion and 30-day invalidation watchdog."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    async with db_manager.session() as session:
        memory_repo = PostgresMemoryRepository(session)
        vector_repo = InMemoryVectorRepository()
        graph_repo = PostgresKnowledgeGraphRepository(session)
        emb_gen = MockEmbeddingGenerator(dimensions=3)

        memory_service = MemoryService(
            settings, memory_repo, vector_repo, graph_repo, emb_gen, event_bus
        )

        # Mock http response
        mock_html = b"<html><body><h1>Playwright docs</h1><pre>def test_api(): pass</pre></body></html>"
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock_open.return_value.__enter__.return_value
            mock_resp.read.return_value = mock_html

            service = LearningService(memory_service)
            chunk_id = await service.ingest_url("https://playwright.dev/docs/intro")
            await session.commit()

            # Verify chunk is saved
            chunk = await memory_repo.get_chunk(chunk_id)
            assert chunk is not None
            assert (
                chunk.metadata.get("source_url") == "https://playwright.dev/docs/intro"
            )

            # Check stale watchdog (should be empty now)
            stale = await service.check_stale_nodes()
            assert len(stale) == 0

            # Force expire the chunk metadata manually
            expired_time = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
            await memory_repo.update_chunk(
                chunk_id,
                chunk.version,
                {
                    "metadata": {
                        "source_url": "https://playwright.dev/docs/intro",
                        "valid_until": expired_time,
                    }
                },
            )
            await session.commit()

            # Watchdog should flag the stale chunk
            stale_expired = await service.check_stale_nodes()
            assert len(stale_expired) == 1
            assert stale_expired[0]["chunk_id"] == chunk_id

            # Refresh expired node
            await service.refresh_node(chunk_id)
            await session.commit()

            refreshed_chunk = await memory_repo.get_chunk(chunk_id)
            assert refreshed_chunk is not None
            # valid_until should be pushed to future
            fut_str = refreshed_chunk.metadata.get("valid_until")
            assert fut_str is not None
            assert datetime.fromisoformat(fut_str) > datetime.now(timezone.utc)

    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()


def test_learning_api_routes() -> None:
    """Verify REST endpoints /ingest, /query, and /status."""
    app = FastAPI()
    app.include_router(learning_router)
    client = TestClient(app)

    # 1. Test offline 503 error
    set_learning_service(None)
    response = client.post(
        "/api/v1/learning/ingest", json={"url": "https://python.org"}
    )
    assert response.status_code == 503

    # 2. Mock service endpoints
    mock_service = AsyncMock()
    mock_service.ingest_url.return_value = uuid4()
    mock_service.check_stale_nodes.return_value = []
    mock_service.memory_service.retrieve.return_value = [
        MemoryNode(content="Search result", metadata={})
    ]
    # Correct mock session attributes to satisfy routes.py query operations
    from unittest.mock import MagicMock

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []

    mock_repo = AsyncMock()
    mock_repo.session.execute.return_value = mock_res
    mock_service.memory_service.memory_repo = mock_repo
    set_learning_service(mock_service)

    # Ingest API
    ing_res = client.post("/api/v1/learning/ingest", json={"url": "https://python.org"})
    assert ing_res.status_code == 200
    assert ing_res.json()["status"] == "SUCCESS"

    # Query API
    query_res = client.get("/api/v1/learning/query?q=playwright")
    assert query_res.status_code == 200
    assert len(query_res.json()) == 1

    # Status API
    status_res = client.get("/api/v1/learning/status")
    assert status_res.status_code == 200
    assert status_res.json()["cluster_status"] == "HEALTHY"


def test_scraper_extra_coverage() -> None:
    """Verify extra edge cases in DocumentScraper validation."""
    scraper = DocumentScraper()

    # Port suffix handling
    assert scraper.validate_url("https://python.org:8080/downloads") == "python.org"

    # Invalid netloc/scheme
    with pytest.raises(JarvisAgentError):
        scraper.validate_url("invalid-url-string")

    # Generic parsing failure (raising generic Exception inside urlparse)
    with patch("urllib.parse.urlparse", side_effect=Exception("parse error")):
        with pytest.raises(JarvisAgentError):
            scraper.validate_url("https://python.org")


@pytest.mark.asyncio
async def test_extractor_extra_relations() -> None:
    """Verify docker/sandbox and postgresql/database extraction rules."""
    extractor = EntityExtractor()
    text = "Deploy postgresql database inside docker sandbox environment."
    entities = await extractor.extract_entities(text)
    relations = await extractor.extract_relations(entities, text)

    rel_types = {r.relation_type for r in relations}
    assert "depends_on" in rel_types
    assert "part_of" in rel_types


@pytest.mark.asyncio
async def test_learning_service_failure_paths() -> None:
    """Verify refresh and parsing watchdog edge cases."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    async with db_manager.session() as session:
        memory_repo = PostgresMemoryRepository(session)
        vector_repo = InMemoryVectorRepository()
        graph_repo = PostgresKnowledgeGraphRepository(session)
        emb_gen = MockEmbeddingGenerator(dimensions=3)

        memory_service = MemoryService(
            settings, memory_repo, vector_repo, graph_repo, emb_gen, event_bus
        )

        service = LearningService(memory_service)

        # 1. Refreshing non-existent chunk
        with pytest.raises(JarvisAgentError):
            await service.refresh_node(uuid4())

        # 2. Refreshing chunk with no source URL
        node = MemoryNode(id=uuid4(), content="No source url content", metadata={})
        chunk_id = await memory_service.store(node)
        await session.commit()
        with pytest.raises(JarvisAgentError):
            await service.refresh_node(chunk_id)

        # 3. Invalid datetime format inside check_stale_nodes
        # Force invalid format
        chunk = await memory_repo.get_chunk(chunk_id)
        assert chunk is not None
        await memory_repo.update_chunk(
            chunk_id,
            chunk.version,
            {"metadata": {"valid_until": "bad-datetime-format"}},
        )
        await session.commit()

        # Should not raise exception, just skip it
        stale = await service.check_stale_nodes()
        assert len(stale) == 0

    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()


def test_learning_routes_offline_and_errors() -> None:
    """Verify route error returns for query and status when offline, and exception handling."""
    app = FastAPI()
    app.include_router(learning_router)

    with TestClient(app) as client:
        # Offline check
        set_learning_service(None)
        assert client.get("/api/v1/learning/query?q=test").status_code == 503
        assert client.get("/api/v1/learning/status").status_code == 503

        # Exception mapping
        mock_service = MagicMock()

        async def raise_ingest(url: str, chunk_id: UUID | None = None) -> UUID:
            raise Exception("General Ingest Failure")

        async def raise_query(query: object) -> list[object]:
            raise Exception("General Query Failure")

        async def raise_status() -> list[object]:
            raise Exception("General Status Failure")

        mock_service.ingest_url = raise_ingest
        mock_service.memory_service = SimpleNamespace(retrieve=raise_query)
        mock_service.check_stale_nodes = raise_status
        set_learning_service(mock_service)

        # Ingest 400 response
        assert (
            client.post(
                "/api/v1/learning/ingest", json={"url": "https://python.org"}
            ).status_code
            == 400
        )

        # Query 500 response
        assert client.get("/api/v1/learning/query?q=test").status_code == 500

        # Status 500 response
        assert client.get("/api/v1/learning/status").status_code == 500


@pytest.mark.asyncio
async def test_scraper_http_error() -> None:
    """Verify scraping failure raising JarvisAgentError on urllib HTTPError."""
    scraper = DocumentScraper()

    # urllib HTTPError mock
    from io import BytesIO

    # Mock HTTPError object
    from typing import Any, cast
    from urllib.error import HTTPError

    mock_err = HTTPError(
        "https://python.org", 404, "Not Found", cast(Any, {}), BytesIO(b"")
    )
    with patch("urllib.request.urlopen", side_effect=mock_err):
        with pytest.raises(JarvisAgentError) as excinfo:
            await scraper.scrape_url("https://python.org")
        assert excinfo.value.code == "AGENT_002"
        assert "HTTP request failed" in excinfo.value.message


def test_scraper_ssrf_attacks() -> None:
    """Verify scraper actively blocks loopback, private ranges, and non-HTTP schemes."""
    scraper = DocumentScraper()

    # Schemes
    for bad_url in (
        "file:///etc/passwd",
        "ftp://github.com",
        "smb://python.org",
        "javascript:alert(1)",
    ):
        with pytest.raises(JarvisAgentError) as excinfo:
            scraper.validate_url(bad_url)
        assert any(
            msg in excinfo.value.message
            for msg in ("Unauthorized scheme", "Invalid URL structure")
        )

    # Hostnames resolving to loopback/private
    # We can mock socket.getaddrinfo to return local IPs
    with patch(
        "socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 80))]
    ):
        with pytest.raises(JarvisAgentError) as excinfo:
            scraper.validate_url("https://github.com")
        assert "SSRF Prevention" in excinfo.value.message

    with patch(
        "socket.getaddrinfo",
        return_value=[(None, None, None, None, ("192.168.1.5", 80))],
    ):
        with pytest.raises(JarvisAgentError) as excinfo:
            scraper.validate_url("https://github.com")
        assert "SSRF Prevention" in excinfo.value.message


@pytest.mark.asyncio
async def test_graph_node_deduplication_integration() -> None:
    """Verify that multiple ingestions of identical entity names do not create duplicate nodes."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    event_bus = MemoryEventBus()
    await event_bus.initialize()
    await event_bus.start()

    async with db_manager.session() as session:
        memory_repo = PostgresMemoryRepository(session)
        vector_repo = InMemoryVectorRepository()
        graph_repo = PostgresKnowledgeGraphRepository(session)
        emb_gen = MockEmbeddingGenerator(dimensions=3)

        memory_service = MemoryService(
            settings, memory_repo, vector_repo, graph_repo, emb_gen, event_bus
        )

        mock_html = b"<html><body><h1>Playwright Python documentation</h1><pre>import playwright</pre></body></html>"
        with patch("urllib.request.urlopen") as mock_open:
            mock_resp = mock_open.return_value.__enter__.return_value
            mock_resp.read.return_value = mock_html

            service = LearningService(memory_service)

            # Ingest once
            await service.ingest_url("https://playwright.dev/docs/intro")
            await session.commit()

            # Ingest second time for same URL (should parse identical concepts: Playwright, Python)
            await service.ingest_url("https://playwright.dev/docs/intro")
            await session.commit()

            from sqlalchemy import select

            from core.memory.graph import GraphNode

            stmt = select(GraphNode).where(GraphNode.name == "Playwright")
            res = await session.execute(stmt)
            nodes = res.scalars().all()
            assert len(nodes) == 1

    await event_bus.stop()
    await event_bus.shutdown()
    await db_manager.close()


def test_learning_api_background_tasks() -> None:
    """Verify REST API supports non-blocking background tasks ingestion."""
    app = FastAPI()
    app.include_router(learning_router)
    client = TestClient(app)

    mock_service = AsyncMock()
    set_learning_service(mock_service)

    # Ingest in background
    ing_res = client.post(
        "/api/v1/learning/ingest?background=true", json={"url": "https://python.org"}
    )
    assert ing_res.status_code == 200
    assert ing_res.json()["status"] == "PROCESSING"

    # Verify mock_service.ingest_url was called (since TestClient runs background tasks immediately inline)
    # and check that it was scheduled with the pre-allocated chunk UUID from response
    chunk_id = ing_res.json()["chunk_id"]
    mock_service.ingest_url.assert_called_once_with(
        "https://python.org", UUID(chunk_id)
    )


def test_malformed_html_and_unicode_parsing() -> None:
    """Verify HTML parser cleans malformed structures and handles unicode safely."""
    # Malformed HTML tags and complex Unicode chars (Nepali, Emoji)
    html = "<html><head><script>alert('xss')</script></head><body>Unclosed tag <div><b>नमस्ते 🚀<pre><code>x = 10</code></pre>"
    extractor = HTMLContentExtractor()
    extractor.feed(html)
    payload = extractor.get_clean_payload()

    assert "alert('xss')" not in payload
    assert "नमस्ते 🚀" in payload
    assert "x = 10" in payload
