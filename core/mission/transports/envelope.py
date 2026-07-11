"""
PHASE: 45 (M6.4.B.1 — Envelope)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (v1.3 — §6.4 D-5)
    docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md                  (CR-4, APPROVED 2026-07-09)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.B — Envelope v1 wire format)

AUTHORITATIVE:
    NO

``TransportEnvelope`` — versioned wire-format envelope for cross-node
mission task delivery.

**D-5 invariant (spec §6.4 / CR-4):**

    All remote messages travel in a versioned transport envelope
    independent of mission DTOs. Older readers tolerate unknown OPTIONAL
    fields (``extra="ignore"`` discipline). Adding REQUIRED fields,
    renaming, or removing any field requires a fresh CR per AGENTS.md §8.

The envelope is the **wire-format layer** between the leader's transport
call (``MissionTransport.publish``) and the receiver's transport call
(``MissionTransport.subscribe``). It is intentionally distinct from the
M6.1.A actor-side **event envelope** (``core/runtime/mission_events.py``):

* **Event envelope** (M6.1.A, FROZEN 2026-07-08): 8 fields carrying a
  mission lifecycle event through the in-process ``MissionActor``
  write-through. Frozen in ``docs/mission_state_machine.md``.
* **Transport envelope** (this module, M6.4.B.1, FROZEN at this gate):
  6 fields carrying an opaque payload through the cross-node
  ``MissionTransport`` (Redis pub/sub + leases).

The two are deliberately separate: the event envelope is owned by the
mission lifecycle (any change is a STOP condition per spec §9); the
transport envelope is owned by the wire format (D-5 freeze).

**Why a Protocol here (rather than a concrete base class):**

* Type-check only — implementations can be swapped (a future EnvelopeV2
  is an additive module, not a Protocol change).
* Preserves the "versioned" promise of D-5: future readers see
  ``EnvelopeV1`` until a fresh codec lands.

**Wire format (v1):**

```
EnvelopeV1Dto (Pydantic, extra="ignore", frozen=True)
    ↓ model_dump()           (Python mode, NOT mode="json" — see pack() note)
dict
    ↓ coerce UUID → str
dict
    ↓ msgpack.packb
bytes
    ↓ zstd.compress
bytes   ← publish() to MissionTransport
```

Reverse on the receive side. ``idempotency_key`` defaults to ``uuid4``;
mission-domain callers MUST set it equal to ``wave_run_id`` (D-4
invariant).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from uuid import UUID, uuid4

import msgpack
import zstandard as zstd
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("jarvis.core.mission.transports.envelope")


# ---------------------------------------------------------------------------
# Constants — envelope versioning (D-5)
# ---------------------------------------------------------------------------

ENVELOPE_VERSION_V1: int = 1
"""The current envelope version. Pinned; bump on a fresh codec."""

SUPPORTED_ENVELOPE_VERSIONS: tuple[int, ...] = (ENVELOPE_VERSION_V1,)
"""Tuple of envelope versions this codec accepts on unpack()."""

# Default payload_type for the first mission-domain use case
# (DistributedRouter assigning a wave to a remote worker).
PAYLOAD_TYPE_TASK_ASSIGNMENT: str = "mission.task.assignment"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class UnsupportedEnvelopeVersionError(Exception):
    """Raised when an envelope arrives with a version this codec cannot read.

    Per D-5: future envelope versions require a new codec; the receiver
    MUST reject unknown versions rather than silently mis-interpreting
    them. Adding a new supported version is a fresh codec implementation
    (additive, no Protocol change).
    """


# ---------------------------------------------------------------------------
# Pydantic DTO — wire-format shape (frozen, extra="ignore")
# ---------------------------------------------------------------------------


class EnvelopeV1Dto(BaseModel):
    """Wire-format DTO for envelope v1.

    Six fields, in this order, with these names and these types:

    =================  ===========  ============================================
    Field              Type         Notes
    =================  ===========  ============================================
    envelope_version   int          Pinned to 1; bump on a fresh codec.
    payload_type       str          Discriminator (e.g. "mission.task.assignment").
    payload_bytes      bytes        msgpack+zstd of payload-specific data.
    idempotency_key    UUID         D-4 key; mission-domain == wave_run_id.
    producer_id        str          Opaque producer (e.g. "worker:<worker_id>").
    created_at         str          ISO-8601 UTC of publish time.
    =================  ===========  ============================================

    Forward-compat (``extra="ignore"``): adding OPTIONAL fields in future
    minor versions is non-breaking. Removing or renaming any field
    requires a fresh CR per AGENTS.md §8.

    The model is ``frozen=True`` so a constructed envelope cannot be
    mutated (D-5 wire-format immutability — an envelope in flight must
    not change shape mid-transit).
    """

    model_config = ConfigDict(frozen=True, extra="ignore")

    envelope_version: int = Field(
        default=ENVELOPE_VERSION_V1,
        frozen=True,
        description="Envelope schema version. Currently 1.",
    )
    payload_type: str = Field(
        ...,
        description="Opaque discriminator (e.g. 'mission.task.assignment').",
    )
    payload_bytes: bytes = Field(
        ...,
        description="msgpack+zstd of the payload-specific data.",
    )
    idempotency_key: UUID = Field(
        default_factory=uuid4,
        description=(
            "Idempotency key (D-4 invariant). For mission-domain "
            "messages, MUST equal wave_run_id."
        ),
    )
    producer_id: str = Field(
        ...,
        description=(
            "Opaque producer identifier (e.g. 'worker:<worker_id>', "
            "'router', 'replay:<route_id>')."
        ),
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 UTC of publish time.",
    )


# ---------------------------------------------------------------------------
# Codec Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TransportEnvelope(Protocol):
    """Codec interface for envelope wire format (D-5).

    Implementations are responsible for:

    * ``pack()`` — bytes for the wire.
    * ``unpack(raw)`` — bytes from the wire → ``TransportEnvelope``.
    * ``validate()`` — structural sanity check before sending.

    D-5 invariant: this Protocol is the only thing the rest of the
    codebase imports. Adding a v2 codec is an additive module — not a
    Protocol change.
    """

    @property
    def envelope_version(self) -> int:
        """The envelope's version (currently always 1)."""
        ...

    @property
    def idempotency_key(self) -> UUID:
        """The D-4 idempotency key (mission-domain: ``wave_run_id``)."""
        ...

    @property
    def payload_type(self) -> str:
        """The payload discriminator."""
        ...

    def pack(self) -> bytes:
        """Serialize for the wire. Returns opaque bytes."""
        ...

    @classmethod
    def unpack(cls, raw: bytes) -> "TransportEnvelope":
        """Deserialize from the wire.

        Raises ``UnsupportedEnvelopeVersionError`` if the wire bytes
        encode an unsupported version.
        """
        ...


# ---------------------------------------------------------------------------
# v1 codec — msgpack + zstd
# ---------------------------------------------------------------------------


class EnvelopeV1:
    """v1 envelope codec — msgpack+zstd of ``EnvelopeV1Dto``.

    Wire format: ``EnvelopeV1Dto.model_dump(mode="json")`` → ``msgpack.packb`` →
    ``zstd.compress``. Reverse on the receive side.

    Why msgpack + zstd:

    * **msgpack**: compact binary serialization; preserves ``bytes`` and
      ``UUID`` (via ``mode="json"`` str coercion) without ambiguity.
      Already used by M6.1.A's actor-side serializer (``A-4 invariant``).
    * **zstd**: high-ratio compression — small envelopes compress to a
      handful of bytes; large envelopes stay small on the wire.
      Already a dependency (``pyproject.toml``: ``zstandard>=0.23.0``).
    """

    __slots__ = ("_dto",)

    def __init__(
        self,
        *,
        payload_type: str,
        payload_bytes: "bytes | bytearray",
        producer_id: str,
        idempotency_key: Optional[UUID] = None,
        created_at: Optional[str] = None,
    ) -> None:
        """Construct a v1 envelope.

        Args:
            payload_type: Discriminator (e.g. ``"mission.task.assignment"``).
                MUST be a non-empty string.
            payload_bytes: msgpack+zstd of the payload-specific data.
                MUST be ``bytes``.
            producer_id: Opaque producer identifier (e.g.
                ``"worker:<worker_id>"``). MUST be a non-empty string.
            idempotency_key: For D-4. Defaults to ``uuid4()`` if ``None``.
                Mission-domain callers MUST pass ``wave_run_id`` explicitly.
            created_at: ISO-8601 UTC. Defaults to "now" (UTC) if ``None``.

        Raises:
            TypeError: on wrong types or empty strings.
            pydantic.ValidationError: on schema mismatch.
        """
        if not isinstance(payload_type, str) or not payload_type:
            raise TypeError(
                f"payload_type must be a non-empty str (got {payload_type!r})."
            )
        if not isinstance(payload_bytes, (bytes, bytearray)):
            raise TypeError(
                f"payload_bytes must be bytes (got {type(payload_bytes).__name__})."
            )
        if not isinstance(producer_id, str) or not producer_id:
            raise TypeError(
                f"producer_id must be a non-empty str (got {producer_id!r})."
            )

        kwargs: Dict[str, Any] = {
            "payload_type": payload_type,
            "payload_bytes": bytes(payload_bytes),
            "producer_id": producer_id,
        }
        if idempotency_key is not None:
            kwargs["idempotency_key"] = idempotency_key
        if created_at is not None:
            kwargs["created_at"] = created_at

        # Pydantic validates types + extra="ignore" forward-compat.
        self._dto: EnvelopeV1Dto = EnvelopeV1Dto(**kwargs)

    # ----- Properties exposing the underlying DTO ------------------------

    @property
    def envelope_version(self) -> int:
        return self._dto.envelope_version

    @property
    def idempotency_key(self) -> UUID:
        return self._dto.idempotency_key

    @property
    def payload_type(self) -> str:
        return self._dto.payload_type

    @property
    def payload_bytes(self) -> bytes:
        return self._dto.payload_bytes

    @property
    def producer_id(self) -> str:
        return self._dto.producer_id

    @property
    def created_at(self) -> str:
        return self._dto.created_at

    # ----- Codec ---------------------------------------------------------

    def pack(self) -> bytes:
        """Serialize for the wire.

        Order: ``model_dump()`` → coerce ``UUID`` → ``str`` →
        ``msgpack.packb`` → ``zstd.compress``. Returns opaque bytes
        safe to publish via ``MissionTransport``.

        Implementation note: the v1 codec uses
        ``model_dump()`` (Python mode), not ``model_dump(mode="json")``.
        Reason: pydantic v2.13's ``mode="json"`` for ``bytes`` fields
        tries to UTF-8 decode the bytes (instead of base64-encoding),
        which raises ``UnicodeDecodeError`` on any non-UTF-8 payload
        (msgpack bytes are never valid UTF-8). Python mode keeps
        ``bytes`` as ``bytes`` and ``UUID`` as ``UUID``; the explicit
        coercion below maps ``UUID`` → ``str`` so msgpack can
        serialize it. The round-trip on ``unpack`` is symmetric:
        ``model_validate`` accepts ``str`` for a ``UUID`` field.
        """
        as_dict = self._dto.model_dump()
        # Coerce UUID → str so msgpack can serialize it.
        as_dict["idempotency_key"] = str(as_dict["idempotency_key"])
        packed = msgpack.packb(as_dict, use_bin_type=True)
        compressed = zstd.ZstdCompressor().compress(packed)
        return compressed

    @classmethod
    def unpack(cls, raw: bytes) -> "EnvelopeV1":
        """Deserialize from the wire.

        Inverse of ``pack()``: ``zstd.decompress`` → ``msgpack.unpackb`` →
        ``EnvelopeV1Dto.model_validate`` → ``EnvelopeV1``.

        Raises:
            TypeError: if ``raw`` is not bytes.
            UnsupportedEnvelopeVersionError: if ``envelope_version != 1``.
            pydantic.ValidationError: if required fields are missing.
            ValueError: if the decoded payload is not a dict.
        """
        if not isinstance(raw, (bytes, bytearray)):
            raise TypeError(f"raw must be bytes (got {type(raw).__name__}).")
        decompressed = zstd.ZstdDecompressor().decompress(bytes(raw))
        as_dict = msgpack.unpackb(decompressed, raw=False)
        if not isinstance(as_dict, dict):
            raise ValueError(
                f"Decoded envelope is not a dict (got {type(as_dict).__name__})."
            )

        # Version gate (D-5).
        version = as_dict.get("envelope_version")
        if version != ENVELOPE_VERSION_V1:
            raise UnsupportedEnvelopeVersionError(
                f"Unsupported envelope version: {version!r}. "
                f"Supported: {SUPPORTED_ENVELOPE_VERSIONS}. "
                f"Upgrade the codec to support this version."
            )

        # Validate via Pydantic (extra="ignore" tolerates unknown fields).
        dto = EnvelopeV1Dto.model_validate(as_dict)

        # Reconstruct the EnvelopeV1. Pass everything explicitly so the
        # default-factories don't fire (DTO has the canonical values).
        return cls(
            payload_type=dto.payload_type,
            payload_bytes=dto.payload_bytes,
            idempotency_key=dto.idempotency_key,
            producer_id=dto.producer_id,
            created_at=dto.created_at,
        )

    # ----- Validation ---------------------------------------------------

    def validate(self) -> None:
        """Structural sanity check before sending.

        Currently a no-op — Pydantic already validates at construction.
        Reserved for future codecs that need pre-send assertions
        (e.g. envelope size limits, producer_id format).
        """

    # ----- Equality / hashing / repr -------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EnvelopeV1):
            return NotImplemented
        return (
            self._dto.envelope_version == other._dto.envelope_version
            and self._dto.payload_type == other._dto.payload_type
            and self._dto.payload_bytes == other._dto.payload_bytes
            and self._dto.idempotency_key == other._dto.idempotency_key
            and self._dto.producer_id == other._dto.producer_id
            and self._dto.created_at == other._dto.created_at
        )

    def __hash__(self) -> int:
        return hash(
            (
                self._dto.envelope_version,
                self._dto.payload_type,
                self._dto.payload_bytes,
                self._dto.idempotency_key,
                self._dto.producer_id,
                self._dto.created_at,
            )
        )

    def __repr__(self) -> str:
        return (
            f"EnvelopeV1(envelope_version={self._dto.envelope_version}, "
            f"payload_type={self._dto.payload_type!r}, "
            f"idempotency_key={self._dto.idempotency_key}, "
            f"producer_id={self._dto.producer_id!r}, "
            f"payload_bytes_len={len(self._dto.payload_bytes)}, "
            f"created_at={self._dto.created_at!r})"
        )


__all__ = [
    "ENVELOPE_VERSION_V1",
    "EnvelopeV1",
    "EnvelopeV1Dto",
    "PAYLOAD_TYPE_TASK_ASSIGNMENT",
    "SUPPORTED_ENVELOPE_VERSIONS",
    "TransportEnvelope",
    "UnsupportedEnvelopeVersionError",
]
