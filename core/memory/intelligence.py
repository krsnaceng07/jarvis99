"""JARVIS OS - Memory Intelligence Layer.

Coordinates conflict resolution, priority retrieval budgets, auto-save heuristic classification, and memory lock policies.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from core.config import Settings
from core.exceptions import JarvisSystemError
from core.memory.personal import PersonalMemory
from core.memory.repository import PersonalMemoryRepository


class MemoryIntelligenceService:
    """Orchestrates tiered retrieval priority, version conflicts, and rule-based memory auto-classification."""

    def __init__(self, repo: PersonalMemoryRepository, settings: Settings) -> None:
        """Initialize service with repository and settings container.

        Args:
            repo: PersonalMemoryRepository instance.
            settings: Settings configuration instance.
        """
        self.repo = repo
        self.settings = settings

        # Standard noise patterns to prevent auto-saving transient inputs
        self.noise_patterns = [
            re.compile(
                r"^\s*(hello|hi|hey|good\s+morning|good\s+evening)\b", re.IGNORECASE
            ),
            re.compile(
                r"\b(tired|sleepy|bored|lol|haha|lmao|ok|okay|yes|no)\b", re.IGNORECASE
            ),
            re.compile(
                r"^\s*(what|how|why|who|where|when)\b", re.IGNORECASE
            ),  # ignore questions
        ]

        # Rule-based classifiers: pattern -> (fact_extractor, tier, category, default_confidence)
        self.rules = [
            (
                re.compile(r"\bmy\s+name\s+is\s+([a-zA-Z\s]+)", re.IGNORECASE),
                lambda m: f"User name is {m.group(1).strip()}",
                1,  # Tier 1 (Identity)
                "identity",
                1.0,
            ),
            (
                re.compile(r"\bcall\s+me\s+([a-zA-Z\s]+)", re.IGNORECASE),
                lambda m: f"User prefers name {m.group(1).strip()}",
                1,  # Tier 1 (Identity)
                "identity",
                1.0,
            ),
            (
                re.compile(
                    r"\b(i\s+favorite\s+language\s+is|i\s+love\s+coding\s+in|i\s+use)\s+([a-zA-Z0-9\+\#\s\-\.]+)",
                    re.IGNORECASE,
                ),
                lambda m: f"User prefers {m.group(2).strip()}",
                2,  # Tier 2 (Preferences)
                "preference",
                0.95,
            ),
            (
                re.compile(
                    r"\b(i\s+am\s+building|project\s+is|working\s+on)\s+([a-zA-Z0-9\s\-\.]+)",
                    re.IGNORECASE,
                ),
                lambda m: f"User project is {m.group(2).strip()}",
                3,  # Tier 3 (Projects)
                "project",
                0.92,
            ),
            (
                re.compile(
                    r"\b(remember|always|never\s+forget)\s+([a-zA-Z0-9\s\-\.\,\'\"]+)",
                    re.IGNORECASE,
                ),
                lambda m: f"Instruction: {m.group(2).strip()}",
                0,  # Tier 0 (Pinned)
                "rule",
                1.0,
            ),
        ]

    async def add_or_update_memory(
        self,
        fact: str,
        tier: int,
        namespace: str,
        lock_level: str = "NORMAL",
        confidence: float = 1.0,
        importance: int = 50,
        importance_reason: Optional[str] = None,
        aliases: Optional[List[str]] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        embedding_model: Optional[str] = None,
        embedding_version: Optional[str] = None,
        source: Optional[str] = None,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> UUID:
        """Insert a new personal memory or version-update an existing memory fact under conflict rules.

        Args:
            fact: Fact description statement.
            tier: Prioritization tier level (0-4).
            namespace: Namespace partition string.
            lock_level: Lock level (NORMAL, PINNED, SYSTEM_LOCKED).
            confidence: Float confidence rating (0-1).
            importance: Integer importance rating (0-100).
            importance_reason: Category string.
            aliases: Synonyms or tag aliases list.
            extra_metadata: JSON dictionary extensions.
            embedding_model: Vector embedding model tag.
            embedding_version: Vector embedding version tag.
            source: Provenance source category.
            conversation_id: Associated conversation UUID.
            message_id: Associated message UUID.
            created_by: Associated creator ID.

        Returns:
            UUID: Parent stable memory_id.
        """
        # Exclude deleted records to check active matches
        active_memories = await self.repo.get_memories(
            namespace=namespace, active_only=True
        )
        matched_memory: Optional[PersonalMemory] = None

        # Check for semantic duplicate or alias matches
        for mem in active_memories:
            # Match fact exactly or check alias overlaps
            if mem.fact.strip().lower() == fact.strip().lower():
                matched_memory = mem
                break
            if aliases and mem.aliases:
                shared = set(aliases) & set(mem.aliases)
                if shared:
                    matched_memory = mem
                    break

        if matched_memory:
            # Apply Lock Level Enforcements
            if matched_memory.lock_level == "SYSTEM_LOCKED":
                raise JarvisSystemError(
                    code="MEMORY_001",
                    message="Cannot update a system locked personal memory fact.",
                )
            if matched_memory.lock_level == "PINNED" and lock_level != "PINNED":
                raise JarvisSystemError(
                    code="MEMORY_002",
                    message="Pinned memory facts require explicit PINNED level parameters to override.",
                )

            # Carry forward previous metadata and aliases
            if not aliases:
                aliases = getattr(matched_memory, "aliases", None)
            if not extra_metadata:
                extra_metadata = getattr(matched_memory, "extra_metadata", None)
            if not embedding_model:
                embedding_model = getattr(matched_memory, "embedding_model", None)
            if not embedding_version:
                embedding_version = getattr(matched_memory, "embedding_version", None)

            # Deactivate previous active version record
            setattr(matched_memory, "is_active", False)
            self.repo.session.add(matched_memory)

            # Insert new version record under identical parent stable memory_id
            parent_id = UUID(str(matched_memory.memory_id))
            new_version_num = int(matched_memory.version) + 1
        else:
            parent_id = uuid4()
            new_version_num = 1

        # Instantiate PersonalMemory record
        new_memory = PersonalMemory(
            id=str(uuid4()),
            memory_id=str(parent_id),
            fact=fact,
            tier=tier,
            namespace=namespace,
            lock_level=lock_level,
            version=new_version_num,
            is_active=True,
            is_deleted=False,
            pinned=(lock_level == "PINNED" or lock_level == "SYSTEM_LOCKED"),
            archived=False,
            confidence=confidence,
            frequency=1 if not matched_memory else (matched_memory.frequency or 0) + 1,
            importance=importance,
            importance_reason=importance_reason,
            aliases=aliases,
            extra_metadata=extra_metadata,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            sync_version=(
                0 if not matched_memory else (matched_memory.sync_version or 0) + 1
            ),
            sync_status="PENDING",
            source=source,
            conversation_id=str(conversation_id) if conversation_id else None,
            message_id=str(message_id) if message_id else None,
            created_by=str(created_by) if created_by else None,
            last_confirmed_at=datetime.now(timezone.utc),
            created_at=(
                datetime.now(timezone.utc)
                if not matched_memory
                else matched_memory.created_at
            ),
            updated_at=datetime.now(timezone.utc),
            last_accessed=datetime.now(timezone.utc),
        )

        await self.repo.add_memory(new_memory)
        return parent_id

    async def confirm_memory(self, memory_id: UUID) -> bool:
        """Confirm memory validity, updating stamps.

        Args:
            memory_id: Stable parent memory ID.

        Returns:
            True if matched and updated, False otherwise.
        """
        return await self.repo.confirm(memory_id)

    async def forget_memory(self, memory_id: UUID) -> bool:
        """Soft-delete memory, setting is_deleted=True.

        Args:
            memory_id: Stable parent memory ID.

        Returns:
            True if matched and soft-deleted, False otherwise.
        """
        return await self.repo.forget(memory_id)

    async def purge_memory(self, memory_id: UUID) -> bool:
        """Hard-delete memory, removing database rows.

        Args:
            memory_id: Stable parent memory ID.

        Returns:
            True if matched and deleted, False otherwise.
        """
        return await self.repo.purge(memory_id)

    async def retrieve_memories(
        self,
        query: str,
        namespace: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> List[PersonalMemory]:
        """Fetch priority-retrieved, budget-limited memories.

        Retrieval follows: Pinned → System Namespace → Conversation Namespace → Exact Match → Identity → Preferences → Projects → Semantic Search.

        Args:
            query: User text query.
            namespace: Target namespace partition.
            conversation_id: Optional active conversation ID.

        Returns:
            List of validated PersonalMemory records within budget limits.
        """
        # Load configurable limits from settings
        cfg_retrieval = self.settings.memory.retrieval
        limits = {
            0: 9999,  # Unlimited
            1: cfg_retrieval.tier1_limit,
            2: cfg_retrieval.tier2_limit,
            3: cfg_retrieval.tier3_limit,
            4: cfg_retrieval.tier4_limit,
        }

        # Fetch all active personal memories
        all_memories = await self.repo.get_memories(
            namespace=namespace, active_only=True
        )

        # Categorize candidate pools
        pinned_pool = [m for m in all_memories if m.tier == 0]
        system_pool = [m for m in all_memories if m.namespace == "system"]
        conversation_pool = [
            m
            for m in all_memories
            if conversation_id and m.conversation_id == str(conversation_id)
        ]
        exact_pool = [
            m for m in all_memories if query.strip().lower() in m.fact.lower()
        ]

        identity_pool = [m for m in all_memories if m.tier == 1]
        preference_pool = [m for m in all_memories if m.tier == 2]
        project_pool = [m for m in all_memories if m.tier == 3]

        # Combine pools ensuring priority sorting order
        merged_candidates: List[PersonalMemory] = []
        seen_ids = set()

        def add_unique_candidates(pool: List[PersonalMemory], limit: int) -> None:
            added = 0
            for item in pool:
                if item.id not in seen_ids:
                    # Update last_accessed timestamp
                    setattr(item, "last_accessed", datetime.now(timezone.utc))
                    self.repo.session.add(item)

                    merged_candidates.append(item)
                    seen_ids.add(item.id)
                    added += 1
                    if added >= limit:
                        break

        # Process stages
        add_unique_candidates(pinned_pool, limits[0])
        add_unique_candidates(system_pool, limits[4])
        add_unique_candidates(conversation_pool, limits[4])
        add_unique_candidates(exact_pool, limits[4])

        add_unique_candidates(identity_pool, limits[1])
        add_unique_candidates(preference_pool, limits[2])
        add_unique_candidates(project_pool, limits[3])

        # Flush access time changes
        await self.repo.session.flush()

        return merged_candidates

    async def auto_classify_and_save(
        self,
        input_text: str,
        namespace: str = "user",
        conversation_id: Optional[str] = None,
    ) -> Optional[UUID]:
        """Classify input text using heuristics, saving facts exceeding the 0.90 threshold.

        Args:
            input_text: Raw statement.
            namespace: Target namespace partition.
            conversation_id: Associated conversation ID.

        Returns:
            Optional[UUID]: Parent stable memory ID if saved, None otherwise.
        """
        # Check system configuration switch
        if self.settings.memory.disable_auto_memory:
            return None

        # Check noise exclusions
        for pattern in self.noise_patterns:
            if pattern.search(input_text):
                return None

        # Process rules
        for pattern, fact_extractor, tier, category, default_confidence in self.rules:
            match = pattern.search(input_text)
            if match:
                extracted_fact = fact_extractor(match)  # type: ignore[no-untyped-call]

                # Confidence check: require >= 0.90
                if default_confidence < 0.90:
                    continue

                # Save memory
                return await self.add_or_update_memory(
                    fact=extracted_fact,
                    tier=tier,
                    namespace=namespace,
                    lock_level="PINNED" if tier == 0 else "NORMAL",
                    confidence=default_confidence,
                    importance=100 if tier == 0 else 50,
                    importance_reason="EXPLICIT_USER" if tier == 0 else "SYSTEM",
                    conversation_id=conversation_id,
                    source="chat",
                )

        return None
