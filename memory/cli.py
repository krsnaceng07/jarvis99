"""JARVIS OS - Phase 19 M9 Memory CLI Commands.

Thin CLI adapter exposing all 10 frozen memory commands (spec §10).
Every handler delegates to MemoryOrchestrator — no business logic here.
Mirrors API endpoints one-to-one (spec §9.1 frozen mapping).

PHASE: 19
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/81_PHASE_19_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

Exit Codes (spec §10):
    0: Success
    1: Error (invalid args, not found)
    8: Internal error
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict
from uuid import UUID

from core.kernel import Kernel
from core.memory.dto import (
    ExecutionOutcome,
    MemoryTier,
    ReflectionRequest,
    RetrievalRequest,
)
from core.memory.orchestrator import MemoryOrchestrator


async def _boot_kernel() -> Kernel:
    """Boot a minimal Kernel for CLI DI resolution."""
    kernel = Kernel()
    await kernel.initialize()
    config_path = os.getenv("JARVIS_CONFIG_PATH", "config.yaml")
    boot_ok = await kernel.boot(config_path)
    if not boot_ok:
        print("ERROR: Kernel boot failed.", file=sys.stderr)
        sys.exit(8)
    return kernel


# ---------------------------------------------------------------------------
# Command handlers — each returns a dict suitable for JSON or human output
# ---------------------------------------------------------------------------


async def cmd_store(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory store <content>'."""
    try:
        metadata: Dict[str, Any] = {}
        if args.metadata:
            metadata = json.loads(args.metadata)
        chunk_id = await orchestrator.store(
            content=args.content,
            source_type=args.source_type,
            metadata=metadata or None,
            importance=args.importance,
            confidence=args.confidence,
        )
        return {"success": True, "chunk_id": str(chunk_id)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_recall(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory recall <query>'."""
    try:
        request = RetrievalRequest(
            query=args.query,
            max_chunks=args.max_chunks,
            min_score=args.min_score,
        )
        response = await orchestrator.recall(request)
        chunks = [
            {
                "memory_id": str(c.memory_id),
                "content": c.content,
                "content_hash": c.content_hash,
            }
            for c in response.chunks
        ]
        return {"success": True, "total": len(chunks), "chunks": chunks}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_get(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory get <chunk_id>'."""
    try:
        chunk_id = UUID(args.chunk_id)
        record = await orchestrator.memory_repo.get_by_id(chunk_id)
        if record is None:
            return {"success": False, "error": "Memory not found"}
        tier = orchestrator._infer_tier(record)
        return {
            "success": True,
            "memory_id": str(record.memory_id),
            "content": record.content,
            "memory_type": record.memory_type.value
            if hasattr(record.memory_type, "value")
            else str(record.memory_type),
            "confidence": record.confidence,
            "importance": record.importance,
            "tier": tier.value,
            "created_at": str(record.created_at),
            "updated_at": str(record.updated_at),
        }
    except ValueError:
        return {"success": False, "error": f"Invalid UUID: {args.chunk_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_score(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory score <chunk_id>'."""
    try:
        chunk_id = UUID(args.chunk_id)
        score = await orchestrator.score(chunk_id)
        return {
            "success": True,
            "memory_id": str(chunk_id),
            "final_score": score.final_score,
            "recency_score": score.recency_score,
            "importance_score": score.importance_score,
            "confidence_score": score.confidence_score,
            "access_score": score.access_score,
        }
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            return {"success": False, "error": "Memory not found"}
        return {"success": False, "error": f"Invalid UUID: {args.chunk_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_reflect(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory reflect <chunk_id> --outcome <outcome>'."""
    try:
        chunk_id = UUID(args.chunk_id)
        outcome = ExecutionOutcome(args.outcome)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    try:
        request = ReflectionRequest(
            memory_id=chunk_id,
            outcome=outcome,
            confidence_delta=args.delta,
        )
        result = await orchestrator.reflect(request)
        return {"success": result, "memory_id": str(chunk_id), "action": "reflect"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_forget(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory forget <chunk_id>'."""
    try:
        chunk_id = UUID(args.chunk_id)
        result = await orchestrator.forget(
            chunk_id=chunk_id,
            reason=args.reason or "CLI forget",
            cascade=args.cascade,
        )
        return {"success": result, "memory_id": str(chunk_id), "action": "forget"}
    except ValueError:
        return {"success": False, "error": f"Invalid UUID: {args.chunk_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_archive(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory archive <chunk_id>'."""
    try:
        chunk_id = UUID(args.chunk_id)
        result = await orchestrator.archive(
            chunk_id=chunk_id,
            reason=args.reason or "CLI archive",
        )
        return {"success": result, "memory_id": str(chunk_id), "action": "archive"}
    except ValueError:
        return {"success": False, "error": f"Invalid UUID: {args.chunk_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_promote(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory promote <chunk_id> --tier <tier>'."""
    try:
        chunk_id = UUID(args.chunk_id)
        target_tier = MemoryTier(args.tier)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    try:
        result = await orchestrator.promote(chunk_id=chunk_id, target_tier=target_tier)
        return {
            "success": result,
            "memory_id": str(chunk_id),
            "action": "promote",
            "target_tier": target_tier.value,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_stats(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory stats'."""
    try:
        records = await orchestrator.memory_repo.list_records()
        return {"success": True, "total_chunks": len(records)}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def cmd_search(
    orchestrator: MemoryOrchestrator,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    """Handle 'jarvis memory search <query>'."""
    try:
        request = RetrievalRequest(
            query=args.query,
            max_chunks=args.max_chunks,
            min_score=args.min_score,
        )
        response = await orchestrator.recall(request)
        chunks = [
            {
                "memory_id": str(c.memory_id),
                "content": c.content,
                "content_hash": c.content_hash,
            }
            for c in response.chunks
        ]
        return {"success": True, "total": len(chunks), "chunks": chunks}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _print_human(result: Dict[str, Any], command: str) -> None:
    """Print human-readable output for a command result."""
    if not result.get("success", False):
        print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)
        return

    if command == "store":
        print(f"Stored: {result['chunk_id']}")

    elif command == "recall":
        total = result.get("total", 0)
        if total == 0:
            print("No memories found.")
        else:
            print(f"Found {total} memory(ies):")
            for chunk in result.get("chunks", []):
                content_preview = chunk["content"][:80]
                print(f"  [{chunk['memory_id'][:8]}] {content_preview}")

    elif command == "get":
        print(f"Memory: {result['memory_id']}")
        print(f"  Type:       {result['memory_type']}")
        print(f"  Tier:       {result['tier']}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Importance: {result['importance']}")
        print(f"  Content:    {result['content'][:200]}")

    elif command == "score":
        print(f"Score for {result['memory_id']}:")
        print(f"  Final:      {result['final_score']:.4f}")
        print(f"  Recency:    {result['recency_score']:.4f}")
        print(f"  Importance: {result['importance_score']:.4f}")
        print(f"  Confidence: {result['confidence_score']:.4f}")
        print(f"  Access:     {result['access_score']:.4f}")

    elif command in ("reflect", "forget", "archive", "promote"):
        action = result.get("action", command)
        mid = result.get("memory_id", "?")
        print(f"{action.capitalize()}: {mid} — {'OK' if result['success'] else 'FAILED'}")

    elif command == "stats":
        print(f"Total memories: {result.get('total_chunks', 0)}")

    elif command == "search":
        total = result.get("total", 0)
        if total == 0:
            print("No matching memories.")
        else:
            print(f"Found {total} match(es):")
            for chunk in result.get("chunks", []):
                content_preview = chunk["content"][:80]
                print(f"  [{chunk['memory_id'][:8]}] {content_preview}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Command dispatch table
_COMMANDS = {
    "store": cmd_store,
    "recall": cmd_recall,
    "get": cmd_get,
    "score": cmd_score,
    "reflect": cmd_reflect,
    "forget": cmd_forget,
    "archive": cmd_archive,
    "promote": cmd_promote,
    "stats": cmd_stats,
    "search": cmd_search,
}


def main() -> None:
    """CLI entry point for 'jarvis memory'."""
    parser = argparse.ArgumentParser(
        prog="jarvis memory",
        description="JARVIS OS Memory Management CLI (Phase 19 M9)",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # store
    store_p = subparsers.add_parser("store", help="Store a new memory")
    store_p.add_argument("content", type=str, help="Memory content to store")
    store_p.add_argument(
        "--source-type", type=str, default="user_input", help="Source type"
    )
    store_p.add_argument(
        "--importance", type=float, default=0.5, help="Importance (0-1)"
    )
    store_p.add_argument(
        "--confidence", type=float, default=1.0, help="Confidence (0-1)"
    )
    store_p.add_argument(
        "--metadata", type=str, default=None, help="JSON metadata string"
    )

    # recall
    recall_p = subparsers.add_parser("recall", help="Retrieve memories with scoring")
    recall_p.add_argument("query", type=str, help="Query string")
    recall_p.add_argument(
        "--max-chunks", type=int, default=50, help="Max chunks to return"
    )
    recall_p.add_argument(
        "--min-score", type=float, default=0.0, help="Minimum score threshold"
    )

    # get
    get_p = subparsers.add_parser("get", help="Get a specific memory")
    get_p.add_argument("chunk_id", type=str, help="Memory UUID")

    # score
    score_p = subparsers.add_parser("score", help="Get the score for a memory")
    score_p.add_argument("chunk_id", type=str, help="Memory UUID")

    # reflect
    reflect_p = subparsers.add_parser("reflect", help="Apply reflection to a memory")
    reflect_p.add_argument("chunk_id", type=str, help="Memory UUID")
    reflect_p.add_argument(
        "--outcome",
        type=str,
        required=True,
        choices=["success", "failure", "partial", "timeout"],
        help="Execution outcome",
    )
    reflect_p.add_argument(
        "--delta", type=float, default=0.1, help="Confidence delta (±0-1)"
    )

    # forget
    forget_p = subparsers.add_parser("forget", help="Forget a memory")
    forget_p.add_argument("chunk_id", type=str, help="Memory UUID")
    forget_p.add_argument("--reason", type=str, default=None, help="Forget reason")
    forget_p.add_argument(
        "--cascade", action="store_true", help="Cascade delete related memories"
    )

    # archive
    archive_p = subparsers.add_parser("archive", help="Archive a memory")
    archive_p.add_argument("chunk_id", type=str, help="Memory UUID")
    archive_p.add_argument("--reason", type=str, default=None, help="Archive reason")

    # promote
    promote_p = subparsers.add_parser("promote", help="Promote a memory to higher tier")
    promote_p.add_argument("chunk_id", type=str, help="Memory UUID")
    promote_p.add_argument(
        "--tier",
        type=str,
        required=True,
        help="Target tier (conversation, long_term, archived)",
    )

    # stats
    subparsers.add_parser("stats", help="Get memory statistics")

    # search
    search_p = subparsers.add_parser("search", help="Search memories by query")
    search_p.add_argument("query", type=str, help="Search query string")
    search_p.add_argument(
        "--max-chunks", type=int, default=50, help="Max results to return"
    )
    search_p.add_argument(
        "--min-score", type=float, default=0.0, help="Minimum score threshold"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Boot Kernel and resolve MemoryOrchestrator
    kernel = asyncio.run(_boot_kernel())
    orchestrator = kernel.container.resolve(MemoryOrchestrator)

    # Dispatch to command handler
    handler = _COMMANDS.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(8)

    result = asyncio.run(handler(orchestrator, args))

    # Output
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human(result, args.command)

    # Exit code (spec §10)
    if result.get("success") is False:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
