"""
PHASE: 16
STATUS: IMPLEMENTATION
SPECIFICATION:
    AGENTS.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import argparse
import asyncio
import importlib
import inspect
import json
import os
import sys
import time
from typing import List

from audit.base import Audit
from audit.report import AuditReport, AuditResult, AuditStatus


def discover_audits() -> List[Audit]:
    """Dynamically discover and instantiate all Audit subclasses under audit/."""
    audits: List[Audit] = []
    package_dir = os.path.dirname(__file__)

    # Scan the audit directory for any python files except internal ones
    for filename in os.listdir(package_dir):
        if (
            filename.endswith(".py")
            and not filename.startswith("_")
            and filename not in ("base.py", "cli.py", "report.py")
        ):
            module_name = f"audit.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)
                for _, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, Audit)
                        and obj is not Audit
                    ):
                        audits.append(obj())
            except Exception as e:
                # If a module fails to load (e.g. while being implemented), skip or warn
                print(
                    f"Warning: Failed to import module {module_name}: {e}",
                    file=sys.stderr,
                )

    # Sort audits by name for deterministic execution
    audits.sort(key=lambda a: a.name)
    return audits


async def run_audits(
    selected_audit_name: str | None, verbose: bool, quiet: bool
) -> AuditReport:
    """Run discovered audits and compile the results report."""
    all_audits = discover_audits()
    results: List[AuditResult] = []

    for audit in all_audits:
        # Filter if a specific audit name was requested
        if selected_audit_name and audit.name != selected_audit_name:
            continue

        if not quiet:
            print(f"Running audit: {audit.name} ...", end="\r", flush=True)

        start_time = time.perf_counter()
        try:
            res = await audit.run()
            res.duration_seconds = round(time.perf_counter() - start_time, 4)
            results.append(res)
        except Exception as e:
            duration = round(time.perf_counter() - start_time, 4)
            results.append(
                AuditResult(
                    name=audit.name,
                    status=AuditStatus.FAIL,
                    message=f"Unhandled exception during audit: {e}",
                    details={"error": str(e)},
                    duration_seconds=duration,
                )
            )

    # Calculate overall status
    overall_status = AuditStatus.PASS
    for r in results:
        if r.status == AuditStatus.FAIL:
            overall_status = AuditStatus.FAIL
            break
        elif r.status == AuditStatus.WARNING and overall_status == AuditStatus.PASS:
            overall_status = AuditStatus.WARNING

    return AuditReport(overall_status=overall_status, results=results)


def main() -> None:
    """Entry point for the CLI tool."""
    parser = argparse.ArgumentParser(description="JARVIS OS Automated Audit CLI")
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )
    parser.add_argument(
        "--audit", type=str, default=None, help="Run only a specific audit check"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Print minimal summary output"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print verbose details of all runs"
    )

    args = parser.parse_args()

    report = asyncio.run(run_audits(args.audit, args.verbose, args.quiet))

    # Export to file
    try:
        with open("audit_report.json", "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2, default=str)
    except Exception as e:
        print(f"Warning: Could not save report JSON to file: {e}", file=sys.stderr)

    # Output to stdout
    if args.json:
        print(json.dumps(report.model_dump(), indent=2, default=str))
    else:
        if not args.quiet:
            print("\n" + "=" * 50)
            print("JARVIS OS AUDIT REPORT SUMMARY")
            print("=" * 50)
            for res in report.results:
                padding = "." * (30 - len(res.name))
                print(
                    f"{res.name} {padding} {res.status.value} ({res.duration_seconds}s)"
                )
                if args.verbose or res.status == AuditStatus.FAIL:
                    print(f"  Message: {res.message}")
                    if res.details:
                        print(f"  Details: {res.details}")
            print("=" * 50)
            print(f"OVERALL STATUS: {report.overall_status.value}")
            print("=" * 50)

    # Return exit code based on overall status
    if report.overall_status == AuditStatus.FAIL:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
