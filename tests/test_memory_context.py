"""
PHASE: 20
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 20 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from datetime import datetime, timezone
from uuid import uuid4

from core.memory.dto import (
    MemoryMetadata,
    MemoryProvenance,
    MemoryRecord,
    MemoryTrustLevel,
    MemoryVisibility,
)
from core.memory.memory_context import MemoryContextBuilder


def create_record(content: str) -> MemoryRecord:
    from core.memory.dto import MemoryType

    now = datetime.now(timezone.utc)
    return MemoryRecord(
        memory_id=uuid4(),
        memory_type=MemoryType.FACT,
        owner_id=uuid4(),
        visibility=MemoryVisibility.PRIVATE,
        trust_level=MemoryTrustLevel.USER_IMPLICIT,
        confidence=1.0,
        importance=0.5,
        created_at=now,
        updated_at=now,
        content=content,
        content_hash=str(uuid4()),
        version=1,
        provenance=MemoryProvenance(origin="user", created_by="agent"),
        metadata=MemoryMetadata(importance=0.5, token_count=len(content.split())),
    )


def test_build_context_package() -> None:
    builder = MemoryContextBuilder(default_max_tokens=1000)

    goal = "Test context building capability"
    history = [
        create_record("hello standard convo message"),
        create_record("how are you doing today?"),
    ]
    personal = [
        create_record("User likes blue colors"),
        create_record("User lives in Washington"),
    ]
    knowledge = [
        create_record("Washington is a state"),
        create_record("Blue is a cool color"),
    ]

    res = builder.build_context_package(
        current_goal=goal,
        conversation_history=history,
        personal_memories=personal,
        knowledge_nodes=knowledge,
    )

    assert "### CURRENT GOAL" in res["context_string"]
    assert "### CONVERSATION HISTORY" in res["context_string"]
    assert "### USER PREFERENCES & FACTS" in res["context_string"]
    assert "### RELATIONAL KNOWLEDGE" in res["context_string"]
    assert res["tokens_used"] > 0
    assert res["budget_limit"] == 1000


def test_build_context_package_budget_caps() -> None:
    # Use small default_max_tokens = 50 to easily exceed thresholds
    builder = MemoryContextBuilder(default_max_tokens=50)

    # 40% history limit is 20 tokens. Each history item has 100+ tokens.
    history = [
        create_record(
            "convo message that is very very very long and exceeds history token budget limit easily "
            * 10
        ),
        create_record(
            "another extremely long convo message to trigger the history branch cap "
            * 10
        ),
    ]
    # 30% personal limit is 15 tokens.
    personal = [
        create_record(
            "personal fact that is very very very long and exceeds personal token budget limit easily "
            * 10
        ),
    ]
    # Remaining budget. We want the first item to fit, but the second item to be skipped (triggering line 81).
    # Remaining budget is 50. First item has ~2 tokens. Second has 100+ tokens.
    knowledge = [
        create_record("fits budget"),
        create_record(
            "knowledge fact that is very very very long and exceeds remaining budget limit easily "
            * 10
        ),
    ]

    res = builder.build_context_package(
        current_goal=None,
        conversation_history=history,
        personal_memories=personal,
        knowledge_nodes=knowledge,
    )

    assert res["budget_limit"] == 50
    # verify that history and personal were truncated / capped to 0, and knowledge only included the first item
    assert res["breakdown"]["conversation"] == 0
    assert res["breakdown"]["personal"] == 0
    assert res["breakdown"]["knowledge"] == 2
