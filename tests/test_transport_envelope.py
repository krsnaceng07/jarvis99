"""
PHASE: 45 (M6.4.B.1 — Envelope)
STATUS: TEST
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (v1.3 — §6.4 D-5)
    docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md

Envelope v1 codec exhaustive test suite (M6.4.B.1).

Coverage target: ≥ 90% on ``core/mission/transports/envelope.py``.
Total tests: 24 (exceeds the ≥10 floor).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import msgpack
import pytest
import zstandard as zstd
from pydantic import ValidationError

from core.mission.transports.envelope import (
    ENVELOPE_VERSION_V1,
    PAYLOAD_TYPE_TASK_ASSIGNMENT,
    SUPPORTED_ENVELOPE_VERSIONS,
    EnvelopeV1,
    EnvelopeV1Dto,
    TransportEnvelope,
    UnsupportedEnvelopeVersionError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRODUCER: str = "router:test"
_PAYLOAD_TYPE: str = "test.payload"
_PAYLOAD_BYTES: bytes = b"hello-envelope" * 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_envelope(
    *,
    payload_type: str = _PAYLOAD_TYPE,
    payload_bytes: bytes = _PAYLOAD_BYTES,
    producer_id: str = _PRODUCER,
    idempotency_key: UUID | None = None,
    created_at: str | None = None,
) -> EnvelopeV1:
    """Build a fresh EnvelopeV1 for a single test.

    Defaults: caller can override individual fields to exercise edge cases.
    """
    kwargs: dict[str, Any] = {
        "payload_type": payload_type,
        "payload_bytes": payload_bytes,
        "producer_id": producer_id,
    }
    if idempotency_key is not None:
        kwargs["idempotency_key"] = idempotency_key
    if created_at is not None:
        kwargs["created_at"] = created_at
    return EnvelopeV1(**kwargs)


# ===========================================================================
# 1. Version constants (D-5 contract)
# ===========================================================================


class TestEnvelopeVersionConstants:
    """D-5 invariant: the version pin is FROZEN at 1."""

    def test_envelope_version_v1_is_one(self) -> None:
        assert ENVELOPE_VERSION_V1 == 1

    def test_supported_versions_contains_v1(self) -> None:
        assert ENVELOPE_VERSION_V1 in SUPPORTED_ENVELOPE_VERSIONS
        assert SUPPORTED_ENVELOPE_VERSIONS == (1,)

    def test_default_payload_type_is_task_assignment(self) -> None:
        """The first mission-domain use case is task assignment."""
        assert PAYLOAD_TYPE_TASK_ASSIGNMENT == "mission.task.assignment"


# ===========================================================================
# 2. Construction + invariants
# ===========================================================================


class TestConstruction:
    """All required fields; defaults for optional fields."""

    def test_required_fields_only(self) -> None:
        env = _make_envelope()
        assert env.payload_type == _PAYLOAD_TYPE
        assert env.payload_bytes == _PAYLOAD_BYTES
        assert env.producer_id == _PRODUCER

    def test_envelope_version_pinned_to_one(self) -> None:
        env = _make_envelope()
        assert env.envelope_version == 1

    def test_idempotency_key_defaults_to_uuid4(self) -> None:
        a = _make_envelope()
        b = _make_envelope()
        assert isinstance(a.idempotency_key, UUID)
        assert isinstance(b.idempotency_key, UUID)
        # uuid4 collision is statistically impossible.
        assert a.idempotency_key != b.idempotency_key

    def test_idempotency_key_explicit(self) -> None:
        explicit = uuid4()
        env = _make_envelope(idempotency_key=explicit)
        assert env.idempotency_key == explicit

    def test_created_at_defaults_to_iso8601_utc(self) -> None:
        env = _make_envelope()
        # Must parse as ISO-8601 with timezone info.
        parsed = datetime.fromisoformat(env.created_at)
        assert parsed.tzinfo is not None
        # Should be UTC-ish (offset may be 0 or +00:00).
        assert parsed.utcoffset() is not None

    def test_created_at_explicit(self) -> None:
        explicit = "2026-07-09T05:30:00+05:45"
        env = _make_envelope(created_at=explicit)
        assert env.created_at == explicit

    def test_payload_bytes_accepts_bytearray(self) -> None:
        env = _make_envelope(payload_bytes=bytearray(b"abc"))  # type: ignore[arg-type]
        assert env.payload_bytes == b"abc"

    def test_empty_payload_bytes_allowed(self) -> None:
        env = _make_envelope(payload_bytes=b"")
        assert env.payload_bytes == b""

    def test_equality_and_hash(self) -> None:
        key = uuid4()
        ts = "2026-07-09T05:30:00+05:45"
        a = _make_envelope(idempotency_key=key, created_at=ts)
        b = _make_envelope(idempotency_key=key, created_at=ts)
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality_on_payload(self) -> None:
        a = _make_envelope(payload_bytes=b"one")
        b = _make_envelope(payload_bytes=b"two")
        assert a != b

    def test_repr_does_not_leak_payload_bytes(self) -> None:
        """Defensive: repr() should NOT contain the raw payload — payload
        bytes may carry mission secrets in future use cases."""
        env = _make_envelope(payload_bytes=b"supersecret")
        r = repr(env)
        assert "supersecret" not in r
        assert "payload_bytes_len=" in r


# ===========================================================================
# 3. Construction-time type checks
# ===========================================================================


class TestConstructionTypeChecks:
    """Constructor MUST reject bad inputs loudly (no silent defaults)."""

    def test_empty_payload_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="payload_type"):
            _make_envelope(payload_type="")

    def test_non_str_payload_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="payload_type"):
            _make_envelope(payload_type=123)  # type: ignore[arg-type]

    def test_non_bytes_payload_rejected(self) -> None:
        with pytest.raises(TypeError, match="payload_bytes"):
            _make_envelope(payload_bytes="not bytes")  # type: ignore[arg-type]

    def test_empty_producer_id_rejected(self) -> None:
        with pytest.raises(TypeError, match="producer_id"):
            _make_envelope(producer_id="")

    def test_non_str_producer_id_rejected(self) -> None:
        with pytest.raises(TypeError, match="producer_id"):
            _make_envelope(producer_id=b"router")  # type: ignore[arg-type]


# ===========================================================================
# 4. Codec — pack / unpack round-trip
# ===========================================================================


class TestCodecRoundTrip:
    """pack → unpack must reproduce the envelope exactly."""

    def test_round_trip_simple(self) -> None:
        env = _make_envelope()
        wire = env.pack()
        assert isinstance(wire, bytes)
        decoded = EnvelopeV1.unpack(wire)
        assert decoded == env

    def test_round_trip_with_explicit_key_and_timestamp(self) -> None:
        key = uuid4()
        ts = "2026-07-09T05:30:00+05:45"
        env = _make_envelope(idempotency_key=key, created_at=ts)
        decoded = EnvelopeV1.unpack(env.pack())
        assert decoded == env
        assert decoded.idempotency_key == key
        assert decoded.created_at == ts

    def test_round_trip_empty_payload(self) -> None:
        env = _make_envelope(payload_bytes=b"")
        decoded = EnvelopeV1.unpack(env.pack())
        assert decoded.payload_bytes == b""

    def test_round_trip_large_payload(self) -> None:
        """1 MB payload — exercises compression + msgpack."""
        big = b"x" * (1024 * 1024)
        env = _make_envelope(payload_bytes=big)
        decoded = EnvelopeV1.unpack(env.pack())
        assert decoded.payload_bytes == big

    def test_pack_returns_bytes(self) -> None:
        env = _make_envelope()
        assert isinstance(env.pack(), bytes)

    def test_unpack_non_bytes_rejected(self) -> None:
        with pytest.raises(TypeError, match="raw must be bytes"):
            EnvelopeV1.unpack("not bytes")  # type: ignore[arg-type]

    def test_unpack_garbage_rejected(self) -> None:
        """Random bytes — zstd will fail to decompress."""
        with pytest.raises(Exception):  # zstd.ZstdError
            EnvelopeV1.unpack(b"\x00\x01\x02 not a real envelope")

    def test_unpack_non_dict_payload_rejected(self) -> None:
        """Encode a list as the msgpack body — codec must reject."""
        bad_wire = zstd.ZstdCompressor().compress(msgpack.packb([1, 2, 3]))
        with pytest.raises(ValueError, match="not a dict"):
            EnvelopeV1.unpack(bad_wire)


# ===========================================================================
# 5. Versioning — D-5 forward-compat (extra="ignore") + reject unknown ver
# ===========================================================================


class TestD5Versioning:
    """D-5: unknown envelope_version → UnsupportedEnvelopeVersionError."""

    def _encode_wire_with_version(self, version: int) -> bytes:
        """Build a wire-format envelope with a hand-set version field."""
        dto = EnvelopeV1Dto(
            envelope_version=version,
            payload_type=_PAYLOAD_TYPE,
            payload_bytes=_PAYLOAD_BYTES,
            producer_id=_PRODUCER,
        )
        as_dict = dto.model_dump(mode="json")
        # Force the version to whatever the test wants, even if the DTO
        # would normally reject it. This simulates a wire envelope from
        # an unknown future codec.
        as_dict["envelope_version"] = version
        return zstd.ZstdCompressor().compress(msgpack.packb(as_dict))

    def test_unknown_version_rejected(self) -> None:
        wire = self._encode_wire_with_version(version=999)
        with pytest.raises(UnsupportedEnvelopeVersionError, match="999"):
            EnvelopeV1.unpack(wire)

    def test_v2_rejected(self) -> None:
        """Forward-compat: a v2 envelope must NOT silently decode as v1."""
        wire = self._encode_wire_with_version(version=2)
        with pytest.raises(UnsupportedEnvelopeVersionError, match="2"):
            EnvelopeV1.unpack(wire)

    def test_unknown_optional_fields_ignored_on_unpack(self) -> None:
        """D-5: extra="ignore" tolerates OPTIONAL fields a future codec adds."""
        dto = EnvelopeV1Dto(
            payload_type=_PAYLOAD_TYPE,
            payload_bytes=_PAYLOAD_BYTES,
            producer_id=_PRODUCER,
        )
        as_dict = dto.model_dump(mode="json")
        # Simulate a future codec that adds OPTIONAL fields.
        as_dict["future_optional_field"] = "should be ignored"
        as_dict["trace_id"] = "abc-123"
        wire = zstd.ZstdCompressor().compress(msgpack.packb(as_dict))
        decoded = EnvelopeV1.unpack(wire)
        # The unknown fields are silently dropped; the rest round-trips.
        assert decoded.payload_type == _PAYLOAD_TYPE
        assert decoded.payload_bytes == _PAYLOAD_BYTES


# ===========================================================================
# 6. DTO validation — required fields must be present
# ===========================================================================


class TestDtoValidation:
    """The Pydantic DTO enforces required-field presence."""

    def test_missing_payload_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EnvelopeV1Dto(payload_bytes=_PAYLOAD_BYTES, producer_id=_PRODUCER)  # type: ignore[call-arg]

    def test_missing_payload_bytes_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EnvelopeV1Dto(payload_type=_PAYLOAD_TYPE, producer_id=_PRODUCER)  # type: ignore[call-arg]

    def test_missing_producer_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EnvelopeV1Dto(  # type: ignore[call-arg]
                payload_type=_PAYLOAD_TYPE,
                payload_bytes=_PAYLOAD_BYTES,
            )

    def test_dto_is_frozen(self) -> None:
        """Frozen Pydantic — fields cannot be mutated post-construction."""
        env = _make_envelope()
        with pytest.raises(ValidationError):
            env._dto.payload_type = "mutated"


# ===========================================================================
# 7. Protocol surface — runtime_checkable isinstance
# ===========================================================================


class TestProtocolSurface:
    """The codec exposes the ``TransportEnvelope`` Protocol surface."""

    def test_envelope_v1_isinstance_of_protocol(self) -> None:
        env = _make_envelope()
        # ``runtime_checkable`` Protocols accept ``isinstance`` for
        # duck-typed classes that expose the right attribute shape.
        assert isinstance(env, TransportEnvelope)

    def test_envelope_exposes_all_protocol_properties(self) -> None:
        env = _make_envelope()
        # Required properties per Protocol.
        assert isinstance(env.envelope_version, int)
        assert isinstance(env.idempotency_key, UUID)
        assert isinstance(env.payload_type, str)
        # Required method.
        assert callable(env.pack)
        # Class method.
        assert callable(EnvelopeV1.unpack)


# ===========================================================================
# 8. validate() — placeholder sanity check
# ===========================================================================


class TestValidate:
    """validate() is a structural pre-send hook; currently no-op."""

    def test_validate_returns_none(self) -> None:
        env = _make_envelope()
        env.validate()  # no-op today (returns None); just must not raise  # type: ignore[func-returns-value]


# ===========================================================================
# 9. Wire-format size sanity (compressibility check)
# ===========================================================================


class TestWireSize:
    """Highly repetitive payloads should compress well."""

    def test_compression_reduces_repetitive_payload(self) -> None:
        """A 64 KB payload of repeated bytes should compress to < 1 KB."""
        big = b"x" * (64 * 1024)
        env = _make_envelope(payload_bytes=big)
        wire = env.pack()
        # zstd is conservative; we assert < 1 KB (way under the 64 KB raw).
        assert len(wire) < 1024, (
            f"Compressed wire size unexpectedly large: {len(wire)} bytes"
        )

    def test_json_dump_payload_has_correct_shape(self) -> None:
        """Sanity: model_dump(mode='json') includes all 6 fields and is JSON-clean."""
        env = _make_envelope()
        as_dict = env._dto.model_dump(mode="json")
        # JSON-clean (re-parse without error).
        parsed = json.loads(json.dumps(as_dict))
        assert set(parsed.keys()) >= {
            "envelope_version",
            "payload_type",
            "payload_bytes",
            "idempotency_key",
            "producer_id",
            "created_at",
        }
        assert parsed["envelope_version"] == 1
