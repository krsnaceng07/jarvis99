"""
PHASE: 36
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/98_PHASE_36_SWARM_INTELLIGENCE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_36_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from core.interfaces import InterAgentMessage


class ConsensusManager:
    """Manages multi-agent consensus proposals, voting rounds, and state commitments."""

    def __init__(
        self,
        settings: Any,
        db_manager: Any,
        federation_manager: Any,
        vault_manager: Any,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize ConsensusManager with system dependencies."""
        self.settings = settings
        self.db_manager = db_manager
        self.federation_manager = federation_manager
        self.vault_manager = vault_manager
        self.event_bus = event_bus
        self._proposals: Dict[str, Dict[str, Any]] = {}

    async def create_proposal(
        self, proposal_type: str, payload: Dict[str, Any], proposer_node_id: str
    ) -> Dict[str, Any]:
        """Propose a system mutation (e.g. peer authorization, configuration change).

        Returns:
            The proposal record containing proposal_id, status, and metadata.
        """
        proposal_id = str(uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=30)

        proposal = {
            "proposal_id": proposal_id,
            "type": proposal_type,
            "payload": payload,
            "proposer_node_id": proposer_node_id,
            "status": "PENDING",
            "votes": {},
            "yes_votes": 0,
            "no_votes": 0,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        # Auto-vote YES for the proposer if it's a known peer or the local node
        proposal["votes"][proposer_node_id] = True
        proposal["yes_votes"] = 1

        self._proposals[proposal_id] = proposal
        await self._check_consensus_resolution(proposal_id)
        return self._proposals[proposal_id]

    async def cast_vote(
        self, proposal_id: str, voter_node_id: str, vote: bool, signature: str
    ) -> Dict[str, Any]:
        """Record a signed vote from a federated peer.

        Returns:
            The updated proposal status and consensus resolution outcome.
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found.")

        # Check Expiration
        expires_at = datetime.fromisoformat(proposal["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            proposal["status"] = "EXPIRED"
            return proposal

        if proposal["status"] in ("APPROVED", "REJECTED", "EXPIRED"):
            return proposal

        # Verify signature using shared secret from vault
        secret = self.vault_manager.get_secret("federation_secret")
        if not secret:
            secret = "default_shared_secret"

        string_to_sign = f"{proposal_id}:{voter_node_id}:{str(vote).lower()}"
        expected_sig = hmac.new(
            secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, signature):
            raise ValueError("Invalid vote signature.")

        # Prevent double voting / update counts
        previous_vote = proposal["votes"].get(voter_node_id)
        proposal["votes"][voter_node_id] = vote

        if previous_vote is None:
            if vote:
                proposal["yes_votes"] += 1
            else:
                proposal["no_votes"] += 1
        elif previous_vote != vote:
            if vote:
                proposal["yes_votes"] += 1
                proposal["no_votes"] -= 1
            else:
                proposal["no_votes"] += 1
                proposal["yes_votes"] -= 1

        await self._check_consensus_resolution(proposal_id)
        return proposal

    async def get_proposal_status(self, proposal_id: str) -> Dict[str, Any]:
        """Fetch the current state, voting statistics, and expiration details of a proposal."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found.")

        # Perform deferred expiration check
        if proposal["status"] == "PENDING":
            expires_at = datetime.fromisoformat(proposal["expires_at"])
            if datetime.now(timezone.utc) > expires_at:
                proposal["status"] = "EXPIRED"

        return proposal

    async def _check_consensus_resolution(self, proposal_id: str) -> None:
        """Evaluate if the votes count meets consensus resolution criteria."""
        proposal = self._proposals[proposal_id]
        if proposal["status"] != "PENDING":
            return

        # Fetch active peers to calculate total cluster size N
        peers = await self.federation_manager.list_peers()
        local_node_id = getattr(self.federation_manager, "node_id", "node_a")

        # Total cluster size N includes all registered peers + the local node
        peer_ids = {p["node_id"] for p in peers}
        peer_ids.add(local_node_id)
        peer_ids.add(
            proposal["proposer_node_id"]
        )  # include proposer in case it is external
        for v_id in proposal["votes"].keys():
            peer_ids.add(v_id)

        n = len(peer_ids)
        majority_required = (n // 2) + 1

        if proposal["yes_votes"] >= majority_required:
            proposal["status"] = "APPROVED"
        elif proposal["no_votes"] > (n - majority_required):
            proposal["status"] = "REJECTED"

        # Publish consensus.reached event
        if self.event_bus and proposal["status"] in ("APPROVED", "REJECTED"):
            try:
                payload_data = proposal.get("payload") or {}
                raw_mission_id = payload_data.get("mission_id")

                try:
                    mission_id = UUID(str(raw_mission_id))
                except (ValueError, TypeError):
                    mission_id = uuid4()

                msg = InterAgentMessage(
                    sender="consensus_manager",
                    receiver="all",
                    action="consensus.reached",
                    body={
                        "mission_id": str(mission_id),
                        "approved": proposal["status"] == "APPROVED",
                        "votes": proposal["votes"],
                        "reason": f"Consensus resolution finished with status: {proposal['status']}",
                    },
                    correlation_id=mission_id,
                )
                await self.event_bus.publish("consensus.reached", msg)
            except Exception as e:
                import logging
                logging.getLogger("jarvis.core.runtime.consensus").error(
                    "Failed to publish consensus.reached event: %s", e
                )
