"""
PHASE: 35
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_35_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from core.exceptions import JarvisSystemError

logger = logging.getLogger(__name__)

# Try to import psutil for real CPU and memory metrics
try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]


class ScaleManager:
    """Coordinates remote task offloading and distributed tool execution across federated peers."""

    def __init__(
        self,
        settings: Any,
        db_manager: Any,
        federation_manager: Any,
        vault_manager: Any,
        local_orchestrator: Any,
        local_sandbox: Optional[Any] = None,
    ) -> None:
        """Initialize ScaleManager with system dependencies."""
        self.settings = settings
        self.db_manager = db_manager
        self.federation_manager = federation_manager
        self.vault_manager = vault_manager
        self.local_orchestrator = local_orchestrator
        self.local_sandbox = local_sandbox

        # Metrics cache: node_id -> (timestamp, metrics_dict)
        self._metrics_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}
        # TTL for the cache (2-3 seconds as approved by Architect)
        self._cache_ttl = 2.5

        # Offloaded tasks tracker: task_id -> status_dict
        self._offloaded_tasks: Dict[str, Dict[str, Any]] = {}

    def _get_signature_headers(self, payload_str: str) -> Dict[str, str]:
        """Compute P2P HMAC signature headers for a payload string."""
        node_id = getattr(self.federation_manager, "node_id", "node_default")
        try:
            secret = self.vault_manager.get_secret("federation_secret")
        except Exception as e:
            logger.error("Failed to resolve federation secret for signing: %s", e)
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Federation secret unresolved: {str(e)}",
            ) from e

        key_id = "fed_key_1"
        created_at = "2026-07-05T00:00:00Z"
        message_id = str(uuid4())
        nonce = f"nonce_{uuid4().hex}"
        timestamp_str = datetime.now(timezone.utc).isoformat()

        # string_to_sign matches the Phase 31 verify_signature expected schema
        string_to_sign = f"1:{message_id}:{node_id}:{timestamp_str}:{nonce}:{key_id}:{created_at}:{payload_str}"
        sig = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "Content-Type": "application/json",
            "X-Jarvis-Node-Id": node_id,
            "X-Jarvis-Signature": sig,
            "X-Jarvis-Timestamp": timestamp_str,
            "X-Jarvis-Key-Id": key_id,
            "X-Jarvis-Created-At": created_at,
            "X-Jarvis-Message-Id": message_id,
            "X-Jarvis-Nonce": nonce,
        }

    async def get_node_load_metrics(self) -> Dict[str, Any]:
        """Calculate local load factors (CPU, memory, active task count) for load balancing."""
        # 1. CPU and Memory calculation
        cpu_usage = 0.1
        memory_usage = 0.1
        if psutil:
            try:
                cpu_usage = psutil.cpu_percent(interval=None) / 100.0
                mem = psutil.virtual_memory()
                memory_usage = mem.percent / 100.0
            except Exception as e:
                logger.warning("Failed to query psutil metrics: %s", e)

        # 2. Active tasks calculation from SwarmOrchestrator
        active_tasks = 0
        if self.local_orchestrator:
            try:
                active_worker_count = len(self.local_orchestrator.active_worker_tasks)
                queued_count = (
                    self.local_orchestrator.queue.size
                    if hasattr(self.local_orchestrator.queue, "size")
                    else 0
                )
                active_tasks = active_worker_count + queued_count
            except Exception as e:
                logger.warning("Failed to query orchestrator tasks count: %s", e)

        return {
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "active_tasks": active_tasks,
        }

    async def fetch_peer_load_metrics(self, peer_node_id: str) -> Dict[str, Any]:
        """Fetch or retrieve from cache the load metrics of a peer node."""
        now = time.monotonic()
        if peer_node_id in self._metrics_cache:
            cache_time, cached_val = self._metrics_cache[peer_node_id]
            if now - cache_time <= self._cache_ttl:
                return cached_val

        # Not cached or expired: Query remote peer GET /api/v1/federation/load
        peers = await self.federation_manager.list_peers()
        peer_record = next((p for p in peers if p["node_id"] == peer_node_id), None)
        if not peer_record:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Peer node {peer_node_id} is not registered in registry.",
            )

        url = f"{peer_record['base_url']}/api/v1/federation/load"
        headers = self._get_signature_headers("")

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                body = resp.json()
                # Unpack standard envelope if nested
                data = body.get("data", body)
                metrics = {
                    "cpu_usage": data.get("cpu_usage", 1.0),
                    "memory_usage": data.get("memory_usage", 1.0),
                    "active_tasks": data.get("active_tasks", 100),
                }
                self._metrics_cache[peer_node_id] = (now, metrics)
                return metrics
            else:
                logger.warning(
                    "Peer %s metrics query returned HTTP status %s",
                    peer_node_id,
                    resp.status_code,
                )
        except Exception as e:
            logger.error("Failed to query peer %s load metrics: %s", peer_node_id, e)

        # Fallback to high load to penalize unavailable peer
        return {"cpu_usage": 1.0, "memory_usage": 1.0, "active_tasks": 999}

    async def select_best_peer(self) -> Optional[str]:
        """Deterministic peer selection selecting the registered peer with the lowest load factor."""
        peers = await self.federation_manager.list_peers()
        if not peers:
            return None

        # Fetch metrics for all registered peers
        peer_metrics: List[tuple[str, Dict[str, Any]]] = []
        for p in peers:
            node_id = p["node_id"]
            try:
                metrics = await self.fetch_peer_load_metrics(node_id)
                peer_metrics.append((node_id, metrics))
            except Exception:
                # Fallback on failure
                peer_metrics.append(
                    (
                        node_id,
                        {"cpu_usage": 1.0, "memory_usage": 1.0, "active_tasks": 999},
                    )
                )

        # Deterministic sorting:
        # Sort key = (active_tasks, cpu_usage, memory_usage, node_id)
        # Ties are resolved alphabetically by node_id.
        def sort_key(item: tuple[str, Dict[str, Any]]) -> tuple[Any, ...]:
            node_id, m = item
            return (m["active_tasks"], m["cpu_usage"], m["memory_usage"], node_id)

        peer_metrics.sort(key=sort_key)
        return peer_metrics[0][0] if peer_metrics else None

    async def offload_task(
        self, peer_node_id: str, task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Sign and offload a task payload to a federated peer for remote execution."""
        peers = await self.federation_manager.list_peers()
        peer_record = next((p for p in peers if p["node_id"] == peer_node_id), None)
        if not peer_record:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Peer node {peer_node_id} is not registered in registry.",
            )

        url = f"{peer_record['base_url']}/api/v1/federation/offload"
        payload_str = json.dumps(task_data)
        headers = self._get_signature_headers(payload_str)

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, content=payload_str, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            else:
                raise JarvisSystemError(
                    code="SYSTEM_001",
                    message=f"Remote offload request failed with status {resp.status_code}: {resp.text}",
                )
        except Exception as e:
            if isinstance(e, JarvisSystemError):
                raise
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Unexpected transport error during remote offload: {str(e)}",
            ) from e

    async def execute_remote_tool(
        self, peer_node_id: str, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delegate a tool execution request to a remote peer."""
        peers = await self.federation_manager.list_peers()
        peer_record = next((p for p in peers if p["node_id"] == peer_node_id), None)
        if not peer_record:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Peer node {peer_node_id} is not registered in registry.",
            )

        url = f"{peer_record['base_url']}/api/v1/federation/tools/execute"
        payload_str = json.dumps({"tool_name": tool_name, "arguments": arguments})
        headers = self._get_signature_headers(payload_str)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, content=payload_str, headers=headers)
            if resp.status_code == 200:
                body = resp.json()
                return body.get("data", body)
            else:
                raise JarvisSystemError(
                    code="SYSTEM_001",
                    message=f"Remote tool delegation failed with status {resp.status_code}: {resp.text}",
                )
        except Exception as e:
            if isinstance(e, JarvisSystemError):
                raise
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Unexpected transport error during remote tool execution: {str(e)}",
            ) from e

    async def run_offloaded_task_background(
        self,
        task_id: str,
        code: str,
        sender_node_id: Optional[str] = None,
        callback_url: Optional[str] = None,
    ) -> None:
        """Execute sandboxed task offload and trigger the callback."""
        local_node_id = getattr(self.federation_manager, "node_id", "node_default")
        self._offloaded_tasks[task_id] = {
            "task_id": task_id,
            "status": "RUNNING",
            "node_id": local_node_id,
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
        }

        try:
            if not self.local_sandbox:
                raise ValueError("Local sandbox runner is not configured.")

            # Execute python snippet strictly inside the sandbox image/runtime
            result = await self.local_sandbox.run(
                image="python:3.12-slim",
                command=["python", "-c", code],
                timeout=30.0,
            )
            exit_code = result.get("exit_code", 0)
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            status = "SUCCESS" if exit_code == 0 else "FAILED"
        except Exception as e:
            logger.error("Error executing background offloaded task: %s", e)
            status = "FAILED"
            stdout = ""
            stderr = f"Sandbox execution crash: {str(e)}"
            exit_code = -1

        self._offloaded_tasks[task_id] = {
            "task_id": task_id,
            "status": status,
            "node_id": local_node_id,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
        }

        # Resolve target callback URL
        target_callback_url = callback_url
        if not target_callback_url and sender_node_id:
            peers = await self.federation_manager.list_peers()
            peer = next((p for p in peers if p["node_id"] == sender_node_id), None)
            if peer:
                target_callback_url = (
                    f"{peer['base_url']}/api/v1/federation/offload/callback"
                )

        if target_callback_url:
            callback_payload = {
                "task_id": task_id,
                "status": status,
                "node_id": local_node_id,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
            }
            payload_str = json.dumps(callback_payload)
            try:
                headers = self._get_signature_headers(payload_str)
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        target_callback_url, content=payload_str, headers=headers
                    )
                if resp.status_code != 200:
                    logger.warning(
                        "Task offload callback to %s returned status %s",
                        target_callback_url,
                        resp.status_code,
                    )
            except Exception as e:
                logger.error(
                    "Failed to POST task offload callback to %s: %s",
                    target_callback_url,
                    e,
                )
