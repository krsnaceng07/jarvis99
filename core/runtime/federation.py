"""
PHASE: 31
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/93_PHASE_31_FEDERATION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage, LifecycleInterface

logger = logging.getLogger(__name__)


class FederationManager(LifecycleInterface):
    """Manages secure inter-node federation, routing, and peer discovery."""

    def __init__(
        self,
        settings: Any,
        vault_manager: Any,
        event_bus: Optional[EventBusInterface] = None,
    ) -> None:
        self.settings = settings
        self.vault_manager = vault_manager
        self.event_bus = event_bus
        self.node_id = getattr(settings.federation, "node_id", "node_default")
        self.peers_path = getattr(
            settings.federation, "peers_path", "secrets/peers.json"
        )
        self._peers: Dict[str, Dict[str, Any]] = {}
        # Replay cache: map of (sender_node_id:message_id or nonce) -> timestamp
        self._replay_cache: Dict[str, float] = {}

    async def initialize(self) -> None:
        """Initialize the peer registry and load configured nodes."""
        os.makedirs(os.path.dirname(self.peers_path) or ".", exist_ok=True)
        if not os.path.exists(self.peers_path) or os.path.getsize(self.peers_path) == 0:
            self._write_peers_atomic({})
        else:
            try:
                self._peers = self._read_peers()
            except Exception as e:
                logger.error("Failed to read peers registry: %s", e)
                self._peers = {}

    async def start(self) -> None:
        """Start the federation manager."""
        logger.info("FederationManager started.")

    async def stop(self) -> None:
        """Stop the federation manager."""
        logger.info("FederationManager stopped.")

    async def shutdown(self) -> None:
        """Shutdown and clean resources."""
        self._peers.clear()
        self._replay_cache.clear()
        logger.info("FederationManager shutdown complete.")

    def _read_peers(self) -> Dict[str, Dict[str, Any]]:
        with open(self.peers_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("peers", {})

    def _write_peers_atomic(self, peers: Dict[str, Dict[str, Any]]) -> None:
        temp_path = self.peers_path + ".tmp"
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode=0o600)
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump({"peers": peers}, f)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass  # fsync may not be fully supported on all file systems
            os.replace(temp_path, self.peers_path)
        except Exception as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Failed to write peers atomically: {str(e)}",
            ) from e

    async def register_peer(self, node_id: str, base_url: str) -> Dict[str, Any]:
        """Atomically registers a peer node in the local registry configuration file."""
        self._peers = self._read_peers()
        peer_data = {
            "node_id": node_id,
            "base_url": base_url.rstrip("/"),
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "last_seen": None,
        }
        self._peers[node_id] = peer_data
        self._write_peers_atomic(self._peers)
        logger.info("Peer registered: %s (%s)", node_id, base_url)
        return peer_data

    async def list_peers(self) -> List[Dict[str, Any]]:
        """List all configured peer nodes."""
        self._peers = self._read_peers()
        return list(self._peers.values())

    def _clean_replay_cache(self) -> None:
        """Remove cache entries older than 300 seconds to prevent leak."""
        now = time.time()
        expired = [k for k, t in self._replay_cache.items() if now - t > 300.0]
        for k in expired:
            self._replay_cache.pop(k, None)

    async def verify_signature(
        self,
        sender_node_id: str,
        signature: str,
        timestamp_str: str,
        body_bytes: bytes,
        key_id: str,
        created_at: str,
        message_id: str,
        nonce: str,
    ) -> bool:
        """Validate HMAC-SHA256 signature, request freshness, and nonce replay."""
        # 1. Freshness Check (300 seconds window)
        try:
            req_time = datetime.fromisoformat(timestamp_str)
            now_time = datetime.now(timezone.utc)
            diff = abs((now_time - req_time).total_seconds())
            if diff > 300.0:
                logger.warning("Federation request timestamp expired: diff=%s", diff)
                return False
        except Exception as e:
            logger.warning("Invalid timestamp format in request: %s", e)
            return False

        # 2. Replay Protection Check
        self._clean_replay_cache()
        cache_key_msg = f"{sender_node_id}:{message_id}"
        cache_key_nonce = f"{sender_node_id}:{nonce}"
        now_ts = time.time()

        if cache_key_msg in self._replay_cache or cache_key_nonce in self._replay_cache:
            logger.warning(
                "Replay attack detected: message_id=%s, nonce=%s",
                message_id,
                nonce,
            )
            return False

        # Register message_id and nonce
        self._replay_cache[cache_key_msg] = now_ts
        self._replay_cache[cache_key_nonce] = now_ts

        # 3. Retrieve secret and compute signature re-evaluation
        try:
            secret = self.vault_manager.get_secret("federation_secret")
        except Exception as e:
            logger.error("Failed to resolve federation secret: %s", e)
            return False

        # HMAC over schema_version (1), message_id, sender_node_id, timestamp, nonce, key_id, created_at, body
        try:
            body_str = body_bytes.decode("utf-8")
        except Exception:
            return False

        string_to_sign = f"1:{message_id}:{sender_node_id}:{timestamp_str}:{nonce}:{key_id}:{created_at}:{body_str}"
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("Federation HMAC mismatch.")
            return False

        return True

    async def route_message(
        self, peer_node_id: str, message: InterAgentMessage
    ) -> Dict[str, Any]:
        """Sign and route an InterAgentMessage to the target peer node URL.

        Does not raise connection exceptions; returns a structured status map.
        """
        self._peers = self._read_peers()
        peer = self._peers.get(peer_node_id)
        if not peer:
            return {
                "status": "failed",
                "reason": f"Peer {peer_node_id} not registered",
                "latency_ms": 0.0,
            }

        base_url = peer["base_url"]
        url = f"{base_url}/api/v1/federation/route"

        # 1. Resolve key and default metadata
        try:
            secret = self.vault_manager.get_secret("federation_secret")
        except Exception as e:
            return {
                "status": "failed",
                "reason": f"Federation secret unresolved: {str(e)}",
                "latency_ms": 0.0,
            }

        key_id = "fed_key_1"
        created_at = "2026-07-05T00:00:00Z"

        # 2. Package Envelope fields
        message_id = str(uuid4())
        nonce = f"nonce_{uuid4().hex}"
        timestamp_str = datetime.now(timezone.utc).isoformat()
        payload_str = message.model_dump_json()

        # 3. Compute Signature
        string_to_sign = f"1:{message_id}:{self.node_id}:{timestamp_str}:{nonce}:{key_id}:{created_at}:{payload_str}"
        sig = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Jarvis-Node-Id": self.node_id,
            "X-Jarvis-Signature": sig,
            "X-Jarvis-Timestamp": timestamp_str,
            "X-Jarvis-Key-Id": key_id,
            "X-Jarvis-Created-At": created_at,
            "X-Jarvis-Message-Id": message_id,
            "X-Jarvis-Nonce": nonce,
        }

        # 4. Asynchronous transport with timeout and exponential backoff
        attempts = 3
        backoff = 0.1
        start_time = time.monotonic()

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.post(
                        url, content=payload_str, headers=headers
                    )
                latency = int((time.monotonic() - start_time) * 1000)

                if response.status_code == 200:
                    # Update last seen
                    peer["last_seen"] = datetime.now(timezone.utc).isoformat()
                    self._peers[peer_node_id] = peer
                    self._write_peers_atomic(self._peers)

                    return {"status": "success", "latency_ms": latency}
                else:
                    return {
                        "status": "failed",
                        "reason": f"HTTP status {response.status_code}: {response.text}",
                        "latency_ms": latency,
                    }
            except httpx.HTTPError as he:
                latency = int((time.monotonic() - start_time) * 1000)
                logger.warning(
                    "Federation route request attempt %s failed: %s",
                    attempt + 1,
                    he,
                )
                if attempt == attempts - 1:
                    return {
                        "status": "failed",
                        "reason": f"HTTPError connection failure: {str(he)}",
                        "latency_ms": latency,
                    }
                await asyncio.sleep(backoff)
                backoff *= 2
            except Exception as ex:
                latency = int((time.monotonic() - start_time) * 1000)
                return {
                    "status": "failed",
                    "reason": f"Unexpected transfer exception: {str(ex)}",
                    "latency_ms": latency,
                }

        return {
            "status": "failed",
            "reason": "Max routing attempts exceeded",
            "latency_ms": 0.0,
        }

    async def ping_peer(self, peer_node_id: str) -> Dict[str, Any]:
        """Perform simple health check and query peer latency."""
        self._peers = self._read_peers()
        peer = self._peers.get(peer_node_id)
        if not peer:
            return {"status": "offline", "reason": "Node not found in registry"}

        url = f"{peer['base_url']}/api/v1/health"
        start_time = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
            latency = int((time.monotonic() - start_time) * 1000)

            if response.status_code == 200:
                # Update last seen
                peer["last_seen"] = datetime.now(timezone.utc).isoformat()
                self._peers[peer_node_id] = peer
                self._write_peers_atomic(self._peers)

                return {
                    "status": "online",
                    "latency_ms": latency,
                    "last_seen": peer["last_seen"],
                    "version": "1.0.0",
                }
            else:
                return {
                    "status": "offline",
                    "reason": f"Health route returned HTTP {response.status_code}",
                }
        except Exception as e:
            return {"status": "offline", "reason": str(e)}
