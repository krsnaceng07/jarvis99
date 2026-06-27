"""JARVIS OS - Personal Memory Subsystem Tests.

Verifies schema creation, PersonalMemoryRepository CRUD, and MemoryIntelligenceService orchestration.
"""

from typing import Any
from uuid import UUID, uuid4

import pytest

from core.config import Settings
from core.exceptions import JarvisSystemError
from core.memory.database import db_manager
from core.memory.intelligence import MemoryIntelligenceService
from core.memory.models import Base
from core.memory.personal import PersonalMemory  # Registers table with Base
from core.memory.repository import PersonalMemoryRepository


@pytest.fixture
async def db_session() -> Any:
    """Provides a transactional database session over an in-memory SQLite setup."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    # Create all tables (including PersonalMemory table)
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    async with db_manager.session() as session:
        yield session

    await db_manager.close()


@pytest.mark.asyncio
async def test_personal_memory_crud_operations(db_session: Any) -> None:
    """Verify standard repository CRUD functions work correctly."""
    repo = PersonalMemoryRepository(db_session)
    mem_uuid = uuid4()

    memory = PersonalMemory(
        id=str(uuid4()),
        memory_id=str(mem_uuid),
        fact="User likes Python",
        tier=2,
        namespace="user",
        lock_level="NORMAL",
        version=1,
        is_active=True,
        is_deleted=False,
    )

    # 1. Create
    await repo.add_memory(memory)

    # 2. Retrieve
    retrieved = await repo.get_memory(mem_uuid)
    assert retrieved is not None
    assert retrieved.fact == "User likes Python"
    assert retrieved.version == 1

    # 3. Confirm increment
    confirmed = await repo.confirm(mem_uuid)
    assert confirmed is True
    updated = await repo.get_memory(mem_uuid)
    assert updated is not None
    assert updated.frequency == 2
    assert updated.importance == 55

    # 4. Soft Delete
    deleted = await repo.forget(mem_uuid)
    assert deleted is True

    # Retrieve active should return None (filtered)
    assert await repo.get_memory(mem_uuid) is None

    # Retrieve versions should return the soft deleted record
    versions = await repo.get_versions(mem_uuid)
    assert len(versions) == 1
    assert versions[0].is_deleted is True

    # 5. Hard Purge
    purged = await repo.purge(mem_uuid)
    assert purged is True
    assert len(await repo.get_versions(mem_uuid)) == 0


@pytest.mark.asyncio
async def test_memory_intelligence_conflict_resolution(db_session: Any) -> None:
    """Verify MemoryIntelligenceService handles stable memory UUID version updates."""
    settings = Settings.load_settings()
    repo = PersonalMemoryRepository(db_session)
    service = MemoryIntelligenceService(repo, settings)

    # Add initial memory
    parent_id = await service.add_or_update_memory(
        fact="Krishna lives in Kathmandu",
        tier=1,
        namespace="user",
        aliases=["Kathmandu"],
    )

    # Add duplicate statement (same fact)
    dup_id = await service.add_or_update_memory(
        fact="Krishna lives in Kathmandu",
        tier=1,
        namespace="user",
    )
    assert parent_id == dup_id  # Should update under the same stable ID

    # Add alias-matching memory update
    alias_id = await service.add_or_update_memory(
        fact="Krishna lives in Lalitpur",
        tier=1,
        namespace="user",
        aliases=["Kathmandu"],
    )
    assert parent_id == alias_id

    # Verify versions
    versions = await repo.get_versions(parent_id)
    assert len(versions) == 3
    assert versions[2].is_active is True
    assert versions[2].version == 3

    # Error handling on non-existent memory IDs
    fake_id = uuid4()
    assert await service.confirm_memory(fake_id) is False
    assert await service.forget_memory(fake_id) is False
    assert await service.purge_memory(fake_id) is False


@pytest.mark.asyncio
async def test_memory_intelligence_lock_levels(db_session: Any) -> None:
    """Verify lock level policies reject modifications of Pinned or Locked facts."""
    settings = Settings.load_settings()
    repo = PersonalMemoryRepository(db_session)
    service = MemoryIntelligenceService(repo, settings)

    # 1. Pinned update blockage
    pinned_id = await service.add_or_update_memory(
        fact="Favorite language is Python",
        tier=2,
        namespace="user",
        lock_level="PINNED",
    )
    assert isinstance(pinned_id, UUID)

    # Normal update attempt should raise error
    with pytest.raises(JarvisSystemError) as exc_info:
        await service.add_or_update_memory(
            fact="Favorite language is Python",
            tier=2,
            namespace="user",
            lock_level="NORMAL",
        )
    assert exc_info.value.code == "MEMORY_002"

    # Explicit pinned update should succeed
    await service.add_or_update_memory(
        fact="Favorite language is Python",
        tier=2,
        namespace="user",
        lock_level="PINNED",
    )

    # 2. System Locked update blockage
    sys_id = await service.add_or_update_memory(
        fact="Core OS rules",
        tier=0,
        namespace="system",
        lock_level="SYSTEM_LOCKED",
    )
    assert isinstance(sys_id, UUID)

    # Any update attempt should raise error
    with pytest.raises(JarvisSystemError) as exc_info_sys:
        await service.add_or_update_memory(
            fact="Core OS rules",
            tier=0,
            namespace="system",
            lock_level="PINNED",
        )
    assert exc_info_sys.value.code == "MEMORY_001"


@pytest.mark.asyncio
async def test_retrieval_priority_and_budgets(db_session: Any) -> None:
    """Verify memories are sorted by priority and limited by configured budgets."""
    settings = Settings.load_settings()
    # Configure custom limits for testing
    settings.memory.retrieval.tier1_limit = 1
    settings.memory.retrieval.tier2_limit = 1

    repo = PersonalMemoryRepository(db_session)
    service = MemoryIntelligenceService(repo, settings)

    # Insert items
    await service.add_or_update_memory(
        "Pinned rule", tier=0, namespace="user", lock_level="PINNED"
    )
    await service.add_or_update_memory("Identity 1", tier=1, namespace="user")
    await service.add_or_update_memory("Identity 2", tier=1, namespace="user")
    await service.add_or_update_memory("Preference 1", tier=2, namespace="user")
    await service.add_or_update_memory("Preference 2", tier=2, namespace="user")

    retrieved = await service.retrieve_memories(query="test", namespace="user")

    # Expect: Pinned rule, Identity 2 (limit 1), Preference 2 (limit 1)
    # The order will align to: Pinned -> Identity -> Preferences
    assert len(retrieved) == 3
    assert retrieved[0].fact == "Pinned rule"
    assert retrieved[1].tier == 1
    assert retrieved[2].tier == 2


@pytest.mark.asyncio
async def test_auto_classification_heuristics(db_session: Any) -> None:
    """Verify rule-based classifications extract facts and skip transient noise."""
    settings = Settings.load_settings()
    repo = PersonalMemoryRepository(db_session)
    service = MemoryIntelligenceService(repo, settings)

    # 1. Identity
    id_saved = await service.auto_classify_and_save("My name is Krishna Kumar")
    assert id_saved is not None
    mem = await repo.get_memory(id_saved)
    assert mem is not None
    assert mem.fact == "User name is Krishna Kumar"
    assert mem.tier == 1

    # 2. Preference
    pref_saved = await service.auto_classify_and_save("I love coding in Rust")
    assert pref_saved is not None
    mem_pref = await repo.get_memory(pref_saved)
    assert mem_pref is not None
    assert mem_pref.fact == "User prefers Rust"
    assert mem_pref.tier == 2

    # 3. Project
    proj_saved = await service.auto_classify_and_save("I am building Jarvis OS")
    assert proj_saved is not None
    mem_proj = await repo.get_memory(proj_saved)
    assert mem_proj is not None
    assert mem_proj.fact == "User project is Jarvis OS"
    assert mem_proj.tier == 3

    # 4. Pinned Rule
    rule_saved = await service.auto_classify_and_save("Always answer in Nepali")
    assert rule_saved is not None
    mem_rule = await repo.get_memory(rule_saved)
    assert mem_rule is not None
    assert mem_rule.fact == "Instruction: answer in Nepali"
    assert mem_rule.tier == 0
    assert mem_rule.lock_level == "PINNED"

    # 5. Noise exclusions (should not save)
    assert await service.auto_classify_and_save("Hello there") is None
    assert await service.auto_classify_and_save("Today I am tired") is None
    assert await service.auto_classify_and_save("what is my name?") is None

    # 6. Disable switch override
    settings.memory.disable_auto_memory = True
    assert await service.auto_classify_and_save("My name is Krishna Kumar") is None
    settings.memory.disable_auto_memory = False

    # 7. Low confidence exclusion
    import re

    service.rules.append(
        (
            re.compile(r"weak rule"),
            lambda m: "weak fact",
            4,
            "temp",
            0.85,
        )
    )
    assert await service.auto_classify_and_save("weak rule") is None
