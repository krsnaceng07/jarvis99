"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M10 CLI)

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M10 CLI)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

CLI adapter for skill management. Thin wrapper around SkillInstaller —
no business logic here. Follows audit/cli.py pattern (argparse).
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from core.kernel import Kernel
from core.skills.installer import InstallResult, SkillInstaller
from core.skills.registry import SkillRegistry


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
# Command handlers
# ---------------------------------------------------------------------------


async def cmd_install(
    installer: SkillInstaller,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Handle 'jarvis skill install <name>'."""
    from core.skills.download_dto import DownloadedPackage

    skill_name: str = args.name
    version: str | None = args.version
    force: bool = args.force

    manifest_payload = {
        "id": skill_name,
        "name": skill_name,
        "version": version or "1.0.0",
        "author": "user",
        "description": f"Skill package: {skill_name}",
        "entrypoint": "main.py",
        "permissions": ["file_read"],
        "dependencies": [],
        "signature": "a" * 64,
        "checksum": "b" * 64,
        "jarvis_api_version": "0.8",
        "min_runtime_version": "0.8",
        "approval_level": "L0",
        "trust_level": "COMMUNITY",
        "capabilities": [{"key": f"{skill_name}.skill.execute"}],
        "compatibility": {
            "platforms": ["windows", "linux"],
            "architectures": ["x64"],
            "python": ">=3.11",
            "jarvis_runtime": ">=0.8",
        },
        "limits": {
            "memory": "512MB",
            "cpu": "1",
            "timeout": 60,
            "network": False,
            "filesystem": "sandbox",
        },
        "isolation": "container",
    }

    downloaded = DownloadedPackage(
        skill_id=skill_name,
        version=version or "1.0.0",
        source_kind="local_package",
        package_path=f"skills/{skill_name}.zip",
        checksum="b" * 64,
        size_bytes=1024,
    )

    result: InstallResult = await installer.install(
        manifest_payload=manifest_payload,
        downloaded=downloaded,
        caller_id="cli",
        force=force,
    )

    return {
        "success": result.success,
        "skill_id": result.skill_id,
        "name": result.name,
        "version": result.version,
        "state": result.state,
        "message": result.message or f"Skill '{result.name}' installed successfully.",
    }


async def cmd_remove(
    installer: SkillInstaller,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Handle 'jarvis skill remove <name>'."""
    skill_name: str = args.name
    removed = await installer.remove(skill_name)

    if not removed:
        return {
            "success": False,
            "error": f"Skill '{skill_name}' not found.",
        }

    return {
        "success": True,
        "message": f"Skill '{skill_name}' removed successfully.",
    }


async def cmd_list(
    registry: SkillRegistry,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Handle 'jarvis skill list'."""
    skills = registry.list_skills(active_only=True)
    return {
        "success": True,
        "total": len(skills),
        "skills": [s.model_dump() for s in skills],
    }


async def cmd_search(
    registry: SkillRegistry,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Handle 'jarvis skill search <query>'."""
    query: str = args.query
    if query:
        results = registry.find_by_capability(query)
    else:
        results = registry.list_skills()

    return {
        "success": True,
        "total": len(results),
        "results": [s.model_dump() for s in results],
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _print_human(result: dict[str, Any], command: str) -> None:
    """Print human-readable output."""
    if command == "install":
        if result.get("success"):
            print(
                f"Installed: {result['name']} v{result['version']} ({result['state']})"
            )
        else:
            print(
                f"Install failed: {result.get('error', result.get('message', 'Unknown error'))}"
            )

    elif command == "remove":
        if result.get("success"):
            print(result["message"])
        else:
            print(f"Remove failed: {result.get('error', 'Unknown error')}")

    elif command == "list":
        total = result.get("total", 0)
        if total == 0:
            print("No skills installed.")
        else:
            print(f"Installed skills ({total}):")
            for skill in result.get("skills", []):
                trust = skill.get("trust_level", "?")
                status = skill.get("status", "?")
                caps = ", ".join(skill.get("capabilities", []))
                print(
                    f"  {skill['name']} v{skill['version']} [{status}] ({trust}) {caps}"
                )

    elif command == "search":
        total = result.get("total", 0)
        if total == 0:
            print("No matching skills found.")
        else:
            print(f"Found {total} skill(s):")
            for skill in result.get("results", []):
                trust = skill.get("trust_level", "?")
                caps = ", ".join(skill.get("capabilities", []))
                print(f"  {skill['name']} v{skill['version']} ({trust}) {caps}")

    elif result.get("success") is False:
        print(f"Error: {result.get('error', 'Unknown error')}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for 'jarvis skill'."""
    parser = argparse.ArgumentParser(
        prog="jarvis skill",
        description="JARVIS OS Skill Management CLI",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # install
    install_parser = subparsers.add_parser("install", help="Install a skill package")
    install_parser.add_argument("name", type=str, help="Skill name or ID to install")
    install_parser.add_argument(
        "--version", type=str, default=None, help="Specific version to install"
    )
    install_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing installation"
    )

    # remove
    remove_parser = subparsers.add_parser("remove", help="Remove an installed skill")
    remove_parser.add_argument("name", type=str, help="Skill name or ID to remove")

    # list
    subparsers.add_parser("list", help="List installed skills")

    # search
    search_parser = subparsers.add_parser("search", help="Search skills by capability")
    search_parser.add_argument(
        "query", type=str, nargs="?", default="", help="Capability query string"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Boot Kernel and resolve dependencies
    kernel = asyncio.run(_boot_kernel())

    installer = kernel.container.resolve(SkillInstaller)
    registry = kernel.container.resolve(SkillRegistry)

    # Dispatch to command handler
    if args.command == "install":
        result = asyncio.run(cmd_install(installer, args))
    elif args.command == "remove":
        result = asyncio.run(cmd_remove(installer, args))
    elif args.command == "list":
        result = asyncio.run(cmd_list(registry, args))
    elif args.command == "search":
        result = asyncio.run(cmd_search(registry, args))
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(8)

    # Output
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human(result, args.command)

    # Exit code
    if result.get("success") is False:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
