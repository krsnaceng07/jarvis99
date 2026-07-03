"""JARVIS OS - Tests for Phase 19 M5.0 Memory Config integration.

Tests verifying that MemoryScoringConfig and MemoryRetentionConfig
match the frozen Phase 19 spec §3.1 and §8.4 contracts.

Frozen contract: Phase 19 spec §3.1 (scoring formula) and §8.4 (config schema).
"""

from __future__ import annotations

import pytest

from core.config import (
    MemoryConfig,
    MemoryRetentionConfig,
    MemoryScoringConfig,
)


class TestMemoryScoringConfigSpecContract:
    """Verify MemoryScoringConfig implements spec §3.1 frozen formula."""

    def test_all_seven_weights_present(self) -> None:
        """All 7 spec §3.1 weights must exist."""
        config = MemoryScoringConfig()
        # Frozen formula requires 7 weights
        for weight in [
            "w_recency",
            "w_semantic",
            "w_confidence",
            "w_importance",
            "w_frequency",
            "w_trust",
            "w_pin",
        ]:
            assert hasattr(config, weight), f"Missing weight: {weight}"

    def test_default_weights_in_range(self) -> None:
        """All default weights must be in [0.0, 1.0]."""
        config = MemoryScoringConfig()
        for weight in [
            "w_recency",
            "w_semantic",
            "w_confidence",
            "w_importance",
            "w_frequency",
            "w_trust",
            "w_pin",
        ]:
            value = getattr(config, weight)
            assert 0.0 <= value <= 1.0, f"{weight}={value} out of [0,1]"

    def test_default_weights_match_spec_section_3_2(self) -> None:
        """Defaults should match spec §3.2 (frozen defaults).

        Spec §3.2 default: 0.25, 0.20, 0.20, 0.15, 0.10, 0.05, 0.05
        (recency, semantic, confidence, importance, frequency, trust, pin)
        """
        config = MemoryScoringConfig()
        assert config.w_recency == 0.25
        assert config.w_semantic == 0.20
        assert config.w_confidence == 0.20
        assert config.w_importance == 0.15
        assert config.w_frequency == 0.10
        assert config.w_trust == 0.05
        assert config.w_pin == 0.05

    def test_weights_sum_to_one(self) -> None:
        """Default weights should sum to 1.0 (per spec §3.2 normalization)."""
        config = MemoryScoringConfig()
        total = (
            config.w_recency
            + config.w_semantic
            + config.w_confidence
            + config.w_importance
            + config.w_frequency
            + config.w_trust
            + config.w_pin
        )
        assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"

    def test_lambda_decay_default(self) -> None:
        """Default lambda_decay = 0.05 per spec §3.2."""
        config = MemoryScoringConfig()
        assert config.lambda_decay == 0.05

    def test_max_access_count_default(self) -> None:
        """Default max_access_count = 1000 per spec §3.2."""
        config = MemoryScoringConfig()
        assert config.max_access_count == 1000

    def test_weight_out_of_range_rejected(self) -> None:
        """Weights must be in [0.0, 1.0]."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            MemoryScoringConfig(w_recency=1.5)
        with pytest.raises(Exception):
            MemoryScoringConfig(w_semantic=-0.1)

    def test_max_access_count_must_be_positive(self) -> None:
        """max_access_count must be >= 1."""
        with pytest.raises(Exception):
            MemoryScoringConfig(max_access_count=0)

    def test_custom_weights_accepted(self) -> None:
        """Custom weights in valid range are accepted."""
        config = MemoryScoringConfig(
            w_recency=0.5,
            w_semantic=0.0,
            w_confidence=0.5,
            w_importance=0.0,
            w_frequency=0.0,
            w_trust=0.0,
            w_pin=0.0,
        )
        assert config.w_recency == 0.5
        assert config.w_semantic == 0.0


class TestMemoryRetentionConfigSpecContract:
    """Verify MemoryRetentionConfig implements spec §8.4 frozen schema."""

    def test_all_retention_fields_present(self) -> None:
        """All spec §8.4 retention fields must exist."""
        config = MemoryRetentionConfig()
        for field in [
            "l1_ttl_minutes",
            "l1_max_items",
            "l2_ttl_hours",
            "l2_max_items",
            "l2_promotion_threshold",
            "l3_decay_threshold",
            "archive_retention_days",
            "promotion_throttle_seconds",
        ]:
            assert hasattr(config, field), f"Missing field: {field}"

    def test_l1_defaults(self) -> None:
        """L1 (working memory) defaults per spec §8.4."""
        config = MemoryRetentionConfig()
        assert config.l1_ttl_minutes == 10
        assert config.l1_max_items == 50

    def test_l2_defaults(self) -> None:
        """L2 (session memory) defaults per spec §8.4."""
        config = MemoryRetentionConfig()
        assert config.l2_ttl_hours == 24
        assert config.l2_max_items == 200

    def test_thresholds(self) -> None:
        """Promotion and decay thresholds."""
        config = MemoryRetentionConfig()
        assert config.l2_promotion_threshold == 0.7
        assert config.l3_decay_threshold == 0.2

    def test_archive_and_throttle(self) -> None:
        """Archive retention and promotion throttle."""
        config = MemoryRetentionConfig()
        assert config.archive_retention_days == 30
        assert config.promotion_throttle_seconds == 60


class TestMemoryConfigContainer:
    """Verify MemoryConfig container aggregates sub-configs."""

    def test_memory_config_has_all_subconfigs(self) -> None:
        """MemoryConfig must contain scoring and retention."""
        config = MemoryConfig()
        assert isinstance(config.scoring, MemoryScoringConfig)
        assert isinstance(config.retention, MemoryRetentionConfig)

    def test_settings_loads_memory_config(self) -> None:
        """Settings must expose memory as MemoryConfig instance."""
        from core.config import Settings

        settings = Settings()
        assert isinstance(settings.memory, MemoryConfig)
        assert isinstance(settings.memory.scoring, MemoryScoringConfig)
        assert isinstance(settings.memory.retention, MemoryRetentionConfig)

    def test_nested_config_override(self) -> None:
        """Nested config fields can be overridden individually."""
        config = MemoryConfig(
            scoring=MemoryScoringConfig(w_recency=0.5),
            retention=MemoryRetentionConfig(l1_max_items=100),
        )
        assert config.scoring.w_recency == 0.5
        assert config.retention.l1_max_items == 100
        # Other fields keep defaults
        assert config.scoring.w_semantic == 0.20
        assert config.retention.l2_ttl_hours == 24
