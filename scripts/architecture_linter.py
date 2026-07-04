"""
PHASE: 19 / M5.5.1
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/governance/architecture_linter.md
    docs/phases/phase19/m5_5_engineering_governance_freeze.md

IMPLEMENTATION PLAN:
    docs/phases/phase19/m5_5_1_architecture_linter_implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import ast
import enum
import json
import sys
import time
import tomllib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

# Safety: this module never imports eval/exec, never makes network calls,
# never writes outside the report target. It only parses Python source via
# the stdlib `ast` module and reads files locally.


# ============================================================================
# Contracts (frozen in docs/governance/architecture_linter.md §6, §7)
# ============================================================================


class Severity(str, enum.Enum):
    """Rule violation severity. Lower-case string values per JSON schema v1.0."""

    ERROR = "error"
    WARN = "warn"
    INFO = "info"


@dataclass(frozen=True)
class Violation:
    """A single rule violation. Immutable per spec §7 invariants.

    Attributes:
        rule_id: e.g. "LR-1", "NBR-3"
        severity: one of Severity.*
        file: path to the offending file
        line: 1-based line number
        col: 1-based column number
        message: human-readable explanation
        snippet: the offending line of source (best-effort)
    """

    rule_id: str
    severity: Severity
    file: Path
    line: int
    col: int
    message: str
    snippet: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "file": str(self.file),
            "line": self.line,
            "col": self.col,
            "message": self.message,
            "snippet": self.snippet,
        }


@dataclass
class LinterConfig:
    """Parsed `.architecture-linter.toml` configuration.

    Defaults follow the frozen spec §7. Rules are grouped by category prefix
    (LR, NBR, NSD, NDE, NUC, NCP, KG); each category can be toggled and its
    severity overridden.
    """

    severity_default: Severity = Severity.ERROR
    exclude: list[str] = field(default_factory=list)
    output_format: str = "text"
    fail_on: Severity = Severity.ERROR
    enabled_categories: set[str] = field(
        default_factory=lambda: {"LR", "NBR", "NSD", "NDE", "NUC", "NCP"}
    )
    category_severity: dict[str, Severity] = field(default_factory=dict)

    @classmethod
    def from_toml(cls, path: Path) -> "LinterConfig":
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, object]) -> "LinterConfig":
        general = data.get("general", {})
        if not isinstance(general, dict):
            general = {}
        severity_default = Severity(str(general.get("severity_default", "error")))
        exclude = [str(x) for x in general.get("exclude", [])]
        output_format = str(general.get("output_format", "text"))
        fail_on = Severity(str(general.get("fail_on", "error")))

        enabled_categories: set[str] = set()
        category_severity: dict[str, Severity] = {}

        rules_obj = data.get("rules", {})
        if isinstance(rules_obj, dict):
            for category, cfg in rules_obj.items():
                if not isinstance(cfg, dict):
                    continue
                if cfg.get("enabled", True):
                    enabled_categories.add(str(category))
                sev_str = cfg.get("severity")
                if sev_str is not None:
                    category_severity[str(category)] = Severity(str(sev_str))

        return cls(
            severity_default=severity_default,
            exclude=exclude,
            output_format=output_format,
            fail_on=fail_on,
            enabled_categories=enabled_categories,
            category_severity=category_severity,
        )

    def get_severity(self, rule_id: str) -> Severity:
        category = rule_id.split("-")[0]
        return self.category_severity.get(category, self.severity_default)


# ============================================================================
# File context (per-file state passed to rules)
# ============================================================================


@dataclass(frozen=True)
class FileContext:
    """Per-file input handed to each rule's check() method."""

    path: Path
    source: str
    tree: ast.Module


# ============================================================================
# Rule infrastructure
# ============================================================================


class Rule(ABC):
    """Abstract base class for all architecture linter rules.

    Each Rule has a unique rule_id (e.g. "LR-1") and a default severity.
    Implementations override check() and yield zero or more Violations.
    """

    rule_id: str = ""
    default_severity: Severity = Severity.ERROR

    @abstractmethod
    def check(self, ctx: FileContext) -> Iterator[Violation]:
        """Inspect one file and yield zero or more Violations."""

    def violation(
        self,
        ctx: FileContext,
        line: int,
        col: int,
        message: str,
    ) -> Violation:
        """Helper: build a Violation with the offending source line as snippet."""
        snippet = ""
        try:
            lines = ctx.source.splitlines()
            if 0 < line <= len(lines):
                snippet = lines[line - 1].strip()
        except Exception:
            pass
        return Violation(
            rule_id=self.rule_id,
            severity=self.default_severity,
            file=ctx.path,
            line=line,
            col=col,
            message=message,
            snippet=snippet,
        )


class RuleRegistry:
    """Holds registered Rule instances keyed by rule_id.

    Enforces unique rule_ids at registration time. Provides category-based
    enable/disable lookup.
    """

    def __init__(self) -> None:
        self._rules: list[Rule] = []
        self._by_id: dict[str, Rule] = {}

    def register(self, rule: Rule) -> None:
        if not rule.rule_id:
            raise ValueError("Rule.rule_id must be set")
        if rule.rule_id in self._by_id:
            raise ValueError(f"Duplicate rule_id: {rule.rule_id}")
        self._rules.append(rule)
        self._by_id[rule.rule_id] = rule

    def all(self) -> list[Rule]:
        return list(self._rules)

    def get(self, rule_id: str) -> Optional[Rule]:
        return self._by_id.get(rule_id)

    def is_enabled(self, rule_id: str, config: LinterConfig) -> bool:
        category = rule_id.split("-")[0]
        return category in config.enabled_categories


# ============================================================================
# Reporter
# ============================================================================


@dataclass(frozen=True)
class Report:
    """Linter output. Frozen so it can be safely shared across reporters."""

    violations: tuple[Violation, ...]
    files_scanned: int
    duration_ms: int

    def to_dict(self) -> dict[str, object]:
        violations_list = list(self.violations)
        return {
            "schema_version": "1.0",
            "tool": "architecture_linter",
            "files_scanned": self.files_scanned,
            "duration_ms": self.duration_ms,
            "violations": [v.to_dict() for v in violations_list],
            "summary": {
                "error": sum(
                    1 for v in violations_list if v.severity == Severity.ERROR
                ),
                "warn": sum(1 for v in violations_list if v.severity == Severity.WARN),
                "info": sum(1 for v in violations_list if v.severity == Severity.INFO),
            },
        }


class Reporter(ABC):
    @abstractmethod
    def render(self, report: Report) -> str:
        """Render a Report as a string."""


class TextReporter(Reporter):
    """Human-readable text output. Deterministic: sorted by (file, line, col, rule_id)."""

    def render(self, report: Report) -> str:
        if not report.violations:
            return (
                f"OK: {report.files_scanned} files scanned, "
                f"0 violations ({report.duration_ms}ms)"
            )
        header = (
            f"Architecture Linter: {len(report.violations)} violations "
            f"in {report.files_scanned} files ({report.duration_ms}ms)"
        )
        lines: list[str] = [header, ""]
        for v in sorted(
            report.violations, key=lambda x: (str(x.file), x.line, x.col, x.rule_id)
        ):
            lines.append(
                f"{v.severity.value.upper():5s} {v.rule_id} {v.file}:{v.line}:{v.col}"
            )
            lines.append(f"      {v.message}")
            if v.snippet:
                lines.append(f"      > {v.snippet}")
            lines.append("")
        return "\n".join(lines)


class JsonReporter(Reporter):
    """Machine-readable output. Conforms to JSON schema v1.0 (see §7 of plan)."""

    def render(self, report: Report) -> str:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)


# ============================================================================
# Exit Code Manager
# ============================================================================


class ExitCodeManager:
    """Maps linter outcome to a process exit code.

    0 = no violations at or above fail_on threshold
    1 = at least one violation at or above fail_on threshold
    2 = internal linter error (config missing/invalid, unhandled exception)
    """

    EXIT_OK = 0
    EXIT_VIOLATIONS = 1
    EXIT_INTERNAL_ERROR = 2

    _SEVERITY_RANK: dict[Severity, int] = {
        Severity.INFO: 0,
        Severity.WARN: 1,
        Severity.ERROR: 2,
    }

    @classmethod
    def from_violations(cls, violations: list[Violation], fail_on: Severity) -> int:
        threshold = cls._SEVERITY_RANK[fail_on]
        for v in violations:
            if cls._SEVERITY_RANK[v.severity] >= threshold:
                return cls.EXIT_VIOLATIONS
        return cls.EXIT_OK


# ============================================================================
# Linter orchestrator
# ============================================================================


class ArchitectureLinter:
    """Main entry point. Walks files, dispatches to rules, returns violations."""

    def __init__(self, config: LinterConfig, registry: RuleRegistry) -> None:
        self.config = config
        self.registry = registry

    def lint(self, path: Path) -> list[Violation]:
        violations: list[Violation] = []
        for file_path in self._collect_files(path):
            violations.extend(self._lint_file(file_path))
        return violations

    def _collect_files(self, path: Path) -> list[Path]:
        """Return sorted list of .py files under path, respecting exclude globs."""
        if not path.exists():
            return []
        if path.is_file():
            return [path] if path.suffix == ".py" else []
        files: list[Path] = []
        for p in path.rglob("*.py"):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(path)
                # Normalize to POSIX separators so exclude patterns ("tests/")
                # match consistently on Windows and POSIX.
                rel_str = rel.as_posix()
            except ValueError:
                rel_str = p.as_posix()
            if any(rel_str.startswith(ex) for ex in self.config.exclude):
                continue
            files.append(p)
        return sorted(files)

    def _lint_file(self, file_path: Path) -> list[Violation]:
        violations: list[Violation] = []
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError:
            return violations
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            violations.append(
                Violation(
                    rule_id="LINTER-PARSE",
                    severity=Severity.ERROR,
                    file=file_path,
                    line=e.lineno or 0,
                    col=e.offset or 0,
                    message=f"Failed to parse Python file: {e.msg}",
                )
            )
            return violations
        ctx = FileContext(path=file_path, source=source, tree=tree)
        for rule in self.registry.all():
            if not self.registry.is_enabled(rule.rule_id, self.config):
                continue
            for v in rule.check(ctx):
                severity = self.config.get_severity(rule.rule_id)
                violations.append(
                    Violation(
                        rule_id=v.rule_id,
                        severity=severity,
                        file=v.file,
                        line=v.line,
                        col=v.col,
                        message=v.message,
                        snippet=v.snippet,
                    )
                )
        return violations

    def report(
        self,
        violations: list[Violation],
        files_scanned: int,
        duration_ms: int,
    ) -> Report:
        return Report(
            violations=tuple(violations),
            files_scanned=files_scanned,
            duration_ms=duration_ms,
        )


# ============================================================================
# LayerDirection rules (LR-1..5) — added in M5.5.1.B
# ============================================================================

# Top-level layers recognized by the linter. The order is irrelevant; the
# membership check is what matters. Add new layers here only via a CR.
_LAYER_PREFIXES: tuple[str, ...] = (
    "core",
    "api",
    "ui",
    "cli",
    "brain",
    "memory",
    "tools",
)


def _file_layer(path: Path) -> str | None:
    """Return the top-level layer of a file path, or None if not in a known layer.

    A file at `core/memory/x.py` is in layer "core". A file at
    `tests/test_x.py` is in no recognized layer (returns None).
    """
    parts = path.parts
    for layer in _LAYER_PREFIXES:
        if layer in parts:
            return layer
    return None


def _module_layer(module: str | None) -> str | None:
    """Return the top-level layer of an imported module, or None if external/empty.

    A module `core.memory.x` is in layer "core". A module `fastapi` is
    external (returns None). An empty/None module (relative import) returns
    None.
    """
    if not module:
        return None
    head = module.split(".")[0]
    return head if head in _LAYER_PREFIXES else None


def _iter_imports(tree: ast.Module) -> Iterator[tuple[ast.stmt, str]]:
    """Yield (node, module_name) for every static import in the AST.

    Skips relative imports (level > 0) — they cannot cross package boundaries
    and are not subject to layer direction.

    Returns ``tuple[ast.stmt, str]`` rather than ``tuple[ast.AST, str]`` so
    that downstream callers can access ``.lineno`` / ``.col_offset`` under
    mypy --strict (the base ``ast.AST`` class does not declare those
    attributes; both ``ast.Import`` and ``ast.ImportFrom`` are ``ast.stmt``
    subclasses and therefore DO have them at runtime).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node, node.module


class LR1Rule(Rule):
    """LR-1: core/ must not import from api/, cli/, ui/."""

    rule_id = "LR-1"
    default_severity = Severity.ERROR
    _FORBIDDEN: frozenset[str] = frozenset({"api", "cli", "ui"})

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        if _file_layer(ctx.path) != "core":
            return
        for node, module in _iter_imports(ctx.tree):
            target = _module_layer(module)
            if target in self._FORBIDDEN:
                yield self.violation(
                    ctx,
                    node.lineno,
                    node.col_offset,
                    f"core/ must not import from {target}/ (forbidden layer dependency; import: {module})",
                )


class LR2Rule(Rule):
    """LR-2: api/ must not import private core files (names with leading _)."""

    rule_id = "LR-2"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        if _file_layer(ctx.path) != "api":
            return
        for node, module in _iter_imports(ctx.tree):
            if _module_layer(module) != "core":
                continue
            # A segment is "private" if it starts with "_". The first
            # segment ("core") is the package name, not private.
            parts = module.split(".")
            if any(p.startswith("_") for p in parts[1:]):
                yield self.violation(
                    ctx,
                    node.lineno,
                    node.col_offset,
                    f"api/ must not import private core files (imported: {module})",
                )


class LR3Rule(Rule):
    """LR-3: ui/ must not import core/ directly."""

    rule_id = "LR-3"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        if _file_layer(ctx.path) != "ui":
            return
        for node, module in _iter_imports(ctx.tree):
            if _module_layer(module) == "core":
                yield self.violation(
                    ctx,
                    node.lineno,
                    node.col_offset,
                    f"ui/ must not import core/ directly (imported: {module})",
                )


class LR4Rule(Rule):
    """LR-4: cli/ must not import from api/ or ui/."""

    rule_id = "LR-4"
    default_severity = Severity.ERROR
    _FORBIDDEN: frozenset[str] = frozenset({"api", "ui"})

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        if _file_layer(ctx.path) != "cli":
            return
        for node, module in _iter_imports(ctx.tree):
            target = _module_layer(module)
            if target in self._FORBIDDEN:
                yield self.violation(
                    ctx,
                    node.lineno,
                    node.col_offset,
                    f"cli/ must not import from {target}/ (forbidden layer dependency; import: {module})",
                )


class LR5Rule(Rule):
    """LR-5: Generic layer direction check (UI→API→Brain→Memory+Tools).

    Catches layer direction violations not specifically named by LR-1..4.
    A layer is allowed to import from itself or from any deeper layer in
    the direction chain. Imports going upstream (e.g. core → ui) are
    violations.
    """

    rule_id = "LR-5"
    default_severity = Severity.ERROR

    # Lower rank = more downstream. UI is the most downstream, Memory/Tools
    # are the most upstream. Imports must go from low to high (same or deeper).
    _RANK: dict[str, int] = {
        "ui": 0,
        "api": 1,
        "cli": 1,
        "brain": 2,
        "core": 2,
        "memory": 3,
        "tools": 3,
    }

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        from_layer = _file_layer(ctx.path)
        if from_layer is None:
            return
        from_rank = self._RANK.get(from_layer, -1)
        if from_rank < 0:
            return
        for node, module in _iter_imports(ctx.tree):
            to_layer = _module_layer(module)
            if to_layer is None or to_layer == from_layer:
                continue  # external or same-layer — OK
            to_rank = self._RANK.get(to_layer, -1)
            if to_rank < 0:
                continue  # unknown target layer — skip
            if to_rank < from_rank:
                yield self.violation(
                    ctx,
                    node.lineno,
                    node.col_offset,
                    (
                        f"Layer direction violation: {from_layer}/ cannot import "
                        f"from {to_layer}/ (UI->API->Brain->Memory+Tools direction)"
                    ),
                )


# ============================================================================
# NBR helpers (used by NBR-1..4)
# ============================================================================


def _iter_classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    """Yield every class definition in the module (top-level and nested)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield node


def _is_repository_class(cls: ast.ClassDef) -> bool:
    """Return True if the class name ends with 'Repository'.

    Per NBR rules, the spec targets classes named ``*Repository`` (e.g.
    ``MemoryRepository``, ``KGRepository``). Abstract base classes
    (``AbstractRepository``, ``BaseRepository``) and interfaces
    (``IRepository``) are also covered unless an explicit allowlist is
    added later via configuration.
    """
    return cls.name.endswith("Repository")


def _iter_method_nodes(
    cls: ast.ClassDef,
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yield every method definition declared directly on the class body."""
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _call_dotted_name(node: ast.Call) -> str | None:
    """Return the dotted name of a Call's function, or None if not resolvable.

    Resolves chains of ``ast.Attribute`` to a dot-joined string. Examples:

    - ``self.llm.generate(...)`` -> ``"self.llm.generate"``
    - ``bus.publish(...)``      -> ``"bus.publish"``
    - ``llm(...)``              -> ``"llm"``
    - ``f(x) for f in xs``      -> ``None`` (not a simple Name/Attribute)
    """
    func = node.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    else:
        return None
    return ".".join(reversed(parts))


# ============================================================================
# NBR rules — No Business Logic in Repository
# Spec: docs/governance/architecture_linter.md §3.2
# ============================================================================


class NBR1Rule(Rule):
    """NBR-1: *Repository MUST NOT contain methods with business-logic names.

    Detects method definitions whose names start with a forbidden prefix:
    ``process_``, ``decide_``, ``validate_``, ``score_``, ``rank_``,
    ``recommend_``. These belong in Service / Engine layers, not in the
    Repository (which is restricted to CRUD + transactions + versioning
    + checksums per spec §3.2).
    """

    rule_id = "NBR-1"
    default_severity = Severity.ERROR
    _FORBIDDEN_PREFIXES: tuple[str, ...] = (
        "process_",
        "decide_",
        "validate_",
        "score_",
        "rank_",
        "recommend_",
    )

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        for cls in _iter_classes(ctx.tree):
            if not _is_repository_class(cls):
                continue
            for method in _iter_method_nodes(cls):
                if any(method.name.startswith(p) for p in self._FORBIDDEN_PREFIXES):
                    yield self.violation(
                        ctx,
                        method.lineno,
                        method.col_offset,
                        (
                            f"Repository '{cls.name}' must not have method "
                            f"'{method.name}' (forbidden business-logic name; "
                            f"belongs in Service / Engine layer)"
                        ),
                    )


class NBR2Rule(Rule):
    """NBR-2: *Repository MUST NOT call an LLM, embedding model, or planner.

    Heuristic detection: scans method bodies for Call nodes whose dotted
    function name contains a forbidden segment keyword (``llm``,
    ``embedding``, ``embeddings``, ``planner``). The Repository is a data
    gateway; inference / planning belong in the Engine / Service layer.
    """

    rule_id = "NBR-2"
    default_severity = Severity.ERROR
    _FORBIDDEN_KEYWORDS: tuple[str, ...] = (
        "llm",
        "embedding",
        "embeddings",
        "planner",
    )

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        for cls in _iter_classes(ctx.tree):
            if not _is_repository_class(cls):
                continue
            for method in _iter_method_nodes(cls):
                for node in ast.walk(method):
                    if not isinstance(node, ast.Call):
                        continue
                    name = _call_dotted_name(node)
                    if name is None:
                        continue
                    segments = name.split(".")
                    if any(kw in segments for kw in self._FORBIDDEN_KEYWORDS):
                        yield self.violation(
                            ctx,
                            node.lineno,
                            node.col_offset,
                            (
                                f"Repository '{cls.name}.{method.name}' must not "
                                f"call LLM/embedding/planner (call: {name})"
                            ),
                        )


class NBR3Rule(Rule):
    """NBR-3: *Repository MUST NOT write to the event bus directly.

    Detects Call nodes whose final segment is a publish-style method
    (``publish`` / ``emit`` / ``dispatch``) AND whose object path
    contains a bus-related keyword (``bus`` / ``event`` / ``events`` /
    ``event_bus``). The Repository must RETURN data for the Orchestrator
    to publish — direct bus writes bypass the orchestration contract.
    """

    rule_id = "NBR-3"
    default_severity = Severity.ERROR
    _PUBLISH_METHODS: tuple[str, ...] = ("publish", "emit", "dispatch")
    _BUS_OBJECT_KEYWORDS: tuple[str, ...] = (
        "bus",
        "event",
        "events",
        "event_bus",
    )

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        for cls in _iter_classes(ctx.tree):
            if not _is_repository_class(cls):
                continue
            for method in _iter_method_nodes(cls):
                for node in ast.walk(method):
                    if not isinstance(node, ast.Call):
                        continue
                    name = _call_dotted_name(node)
                    if name is None:
                        continue
                    segments = name.split(".")
                    if len(segments) < 2:
                        continue
                    last = segments[-1]
                    obj_parts = segments[:-1]
                    if last in self._PUBLISH_METHODS and any(
                        kw in obj_parts for kw in self._BUS_OBJECT_KEYWORDS
                    ):
                        yield self.violation(
                            ctx,
                            node.lineno,
                            node.col_offset,
                            (
                                f"Repository '{cls.name}.{method.name}' must not "
                                f"write to event bus (call: {name}); return data "
                                f"for the orchestrator to publish"
                            ),
                        )


class NBR4Rule(Rule):
    """NBR-4: *Repository MUST NOT perform merge() of graph nodes.

    Graph-node merge is a KGService concern, not a Repository concern.
    Detects methods named exactly ``merge`` or starting with ``merge_``
    (e.g. ``merge_nodes``, ``merge_graph``).
    """

    rule_id = "NBR-4"
    default_severity = Severity.ERROR
    _FORBIDDEN_EXACT: tuple[str, ...] = ("merge",)
    _FORBIDDEN_PREFIXES: tuple[str, ...] = ("merge_",)

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        for cls in _iter_classes(ctx.tree):
            if not _is_repository_class(cls):
                continue
            for method in _iter_method_nodes(cls):
                if method.name in self._FORBIDDEN_EXACT or any(
                    method.name.startswith(p) for p in self._FORBIDDEN_PREFIXES
                ):
                    yield self.violation(
                        ctx,
                        method.lineno,
                        method.col_offset,
                        (
                            f"Repository '{cls.name}' must not have method "
                            f"'{method.name}' (graph merge is a KGService concern)"
                        ),
                    )


# ============================================================================
# NSD helpers (used by NSD-1..3)
# Spec: docs/governance/architecture_linter.md §3.3
# ============================================================================


def _is_engine_class(cls: ast.ClassDef) -> bool:
    """Return True if the class name ends with 'Engine'.

    Per NSD rules, the spec targets decision / inference / scoring engines
    (``InferenceEngine``, ``TraversalEngine``, ``ScoringEngine``,
    ``DecisionEngine``, etc.). This includes traversal, retrieval, and
    inference classes that conventionally use the ``Engine`` suffix.
    """
    return cls.name.endswith("Engine")


def _target_root_name(target: ast.expr) -> str | None:
    """Return the leftmost ``ast.Name.id`` in an assignment target chain.

    Walks through ``ast.Attribute`` / ``ast.Subscript`` layers and returns
    the id of the root name. Returns None if the chain does not terminate
    in a simple Name (e.g. ``(a, b).x = 1``).

    Examples:
        ``node.properties["x"] = 1`` -> ``"node"``
        ``node.x = 1``              -> ``"node"``
        ``self.x = 1``              -> ``"self"``
        ``(a, b)[0] = 1``           -> ``None``
    """
    current = target
    while isinstance(current, (ast.Attribute, ast.Subscript)):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return None


def _is_local_rebind(value: ast.expr, target_id: str) -> bool:
    """Return True if ``value`` is a self-referencing local-rebind pattern.

    Detects patterns where the RHS reads the same local name being assigned
    and produces a NEW value (not an in-place mutation of an object):

    - ``x = x or default``               (BoolOp with Or)
    - ``x = default if x is None else x`` (IfExp with orelse == target)
    - ``x = x if x else default``         (IfExp with body == target)
    - ``x = x + 1`` / ``x = 1 + x``       (BinOp containing target)

    These rebind the local name; they do NOT mutate any passed-in DTO.
    Approved per Architect disposition B5 (2026-07-03).
    """
    if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):
        if value.values and isinstance(value.values[0], ast.Name):
            return value.values[0].id == target_id
    if isinstance(value, ast.IfExp):
        if isinstance(value.orelse, ast.Name) and value.orelse.id == target_id:
            return True
        if isinstance(value.body, ast.Name) and value.body.id == target_id:
            return True
    if isinstance(value, ast.BinOp):
        if isinstance(value.left, ast.Name) and value.left.id == target_id:
            return True
        if isinstance(value.right, ast.Name) and value.right.id == target_id:
            return True
    return False


def _aug_assign_mutates_object(target: ast.expr) -> bool:
    """Return True if an ``AugAssign`` target mutates an object (not a local).

    - ``x += 1``    -> False (local rebind — new int object, then rebind)
    - ``x.attr += 1`` -> True (object attribute mutation in place)
    - ``x[0] += 1``  -> True (object subscript mutation in place)

    Per Architect disposition B5, ``AugAssign`` on a plain ``Name`` is a
    local rebind and is NOT flagged by NSD-2.
    """
    return isinstance(target, (ast.Attribute, ast.Subscript))


# ============================================================================
# NSD rules — No Side Effects in Decision Engine
# Spec: docs/governance/architecture_linter.md §3.3
# ============================================================================


class NSD1Rule(Rule):
    """NSD-1: *Engine MUST NOT perform DB writes.

    Detects method bodies that contain a ``Call`` whose object path
    includes a database-related segment (``db``, ``database``, ``conn``,
    ``connection``, ``session``, ``cursor``, ``pool``, ``tx``,
    ``transaction``). DB writes belong in the Repository layer, not in
    the decision / inference / scoring engine.
    """

    rule_id = "NSD-1"
    default_severity = Severity.ERROR
    _DB_KEYWORDS: tuple[str, ...] = (
        "db",
        "database",
        "conn",
        "connection",
        "session",
        "cursor",
        "pool",
        "tx",
        "transaction",
    )

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        for cls in _iter_classes(ctx.tree):
            if not _is_engine_class(cls):
                continue
            for method in _iter_method_nodes(cls):
                for node in ast.walk(method):
                    if not isinstance(node, ast.Call):
                        continue
                    name = _call_dotted_name(node)
                    if name is None:
                        continue
                    segments = name.split(".")
                    if any(kw in segments for kw in self._DB_KEYWORDS):
                        yield self.violation(
                            ctx,
                            node.lineno,
                            node.col_offset,
                            (
                                f"Engine '{cls.name}.{method.name}' must not "
                                f"perform DB writes (call: {name})"
                            ),
                        )


class NSD2Rule(Rule):
    """NSD-2: *Engine MUST NOT mutate its inputs (inputs are immutable DTOs).

    Detects assignments (``Assign`` / ``AugAssign``) whose target chain
    terminates at a method parameter name (i.e. mutating a passed-in DTO
    or input object). ``self.*`` and the local-rebind patterns
    (``x = x or default``, ``x = default if x is None else x``,
    ``x = x + 1``, ``x += 1`` on a plain name) are NOT flagged per
    Architect disposition B5.
    """

    rule_id = "NSD-2"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        for cls in _iter_classes(ctx.tree):
            if not _is_engine_class(cls):
                continue
            for method in _iter_method_nodes(cls):
                # Collect parameter names: positional + keyword-only.
                # Exclude 'self' / 'cls'.
                arg_names: set[str] = set()
                for a in (
                    method.args.posonlyargs + method.args.args + method.args.kwonlyargs
                ):
                    if a.arg not in ("self", "cls"):
                        arg_names.add(a.arg)
                if not arg_names:
                    continue
                for node in ast.walk(method):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            root = _target_root_name(target)
                            if root is None or root not in arg_names:
                                continue
                            # B5 refinement: skip local-rebind patterns
                            if _is_local_rebind(node.value, root):
                                continue
                            yield self.violation(
                                ctx,
                                node.lineno,
                                node.col_offset,
                                (
                                    f"Engine '{cls.name}.{method.name}' must not "
                                    f"mutate input '{root}' (inputs are immutable DTOs)"
                                ),
                            )
                    elif isinstance(node, ast.AugAssign):
                        root = _target_root_name(node.target)
                        if root is None or root not in arg_names:
                            continue
                        # B5 refinement: AugAssign on plain Name is a local rebind
                        if not _aug_assign_mutates_object(node.target):
                            continue
                        yield self.violation(
                            ctx,
                            node.lineno,
                            node.col_offset,
                            (
                                f"Engine '{cls.name}.{method.name}' must not "
                                f"augment-mutate input '{root}' (inputs are immutable DTOs)"
                            ),
                        )


class NSD3Rule(Rule):
    """NSD-3: *Engine MUST NOT call tools or external services.

    Detects method bodies that contain a ``Call`` whose object path
    includes a tool- or external-service-related segment (``tool``,
    ``tools``, ``http_client``, ``rest_client``, ``grpc_client``,
    ``requests``, ``urllib``, ``httpx``, ``aiohttp``). Tool execution and
    external HTTP belong in dedicated Tool / Service classes, not in
    the engine.
    """

    rule_id = "NSD-3"
    default_severity = Severity.ERROR
    _TOOL_KEYWORDS: tuple[str, ...] = (
        "tool",
        "tools",
        "http_client",
        "rest_client",
        "grpc_client",
        "requests",
        "urllib",
        "httpx",
        "aiohttp",
    )

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        for cls in _iter_classes(ctx.tree):
            if not _is_engine_class(cls):
                continue
            for method in _iter_method_nodes(cls):
                for node in ast.walk(method):
                    if not isinstance(node, ast.Call):
                        continue
                    name = _call_dotted_name(node)
                    if name is None:
                        continue
                    segments = name.split(".")
                    if any(kw in segments for kw in self._TOOL_KEYWORDS):
                        yield self.violation(
                            ctx,
                            node.lineno,
                            node.col_offset,
                            (
                                f"Engine '{cls.name}.{method.name}' must not "
                                f"call tools or external services (call: {name})"
                            ),
                        )


# ============================================================================
# NDE helpers (used by NDE-1..3)
# ============================================================================


def _is_dto_file(path: Path) -> bool:
    """Return True if file is a DTO file (ends with dto.py or types.py)."""
    name = path.name.lower()
    return name.endswith("dto.py") or name.endswith("types.py")


def _iter_base_classes(cls: ast.ClassDef) -> Iterator[str]:
    """Yield base class names for a class definition."""
    for base in cls.bases:
        if isinstance(base, ast.Name):
            yield base.id
        elif isinstance(base, ast.Attribute):
            parts: list[str] = []
            current: ast.expr = base
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                yield ".".join(reversed(parts))


def _is_non_dto_class(
    cls: ast.ClassDef, for_nde3: bool = False, is_dto_file: bool = False
) -> bool:
    """Return True if class is an Enum, TypedDict, Protocol, SQLAlchemy model, or other non-DTO type to skip.

    Args:
        cls: The AST class definition node
        for_nde3: Whether this check is for NDE3 rule
        is_dto_file: Whether the class is in a DTO file (dto.py or types.py)
    """
    base_classes = list(_iter_base_classes(cls))
    # Skip known non-DTO classes
    if cls.name in ("CancellationToken",):
        return True
    # Skip Enums
    for base in base_classes:
        if base.endswith("Enum") or base in (
            "Enum",
            "IntEnum",
            "StrEnum",
            "Flag",
            "IntFlag",
        ):
            return True
    # Skip TypedDict, Protocol, Generic
    for base in base_classes:
        if (
            base in ("TypedDict", "Protocol", "Generic")
            or base.endswith("TypedDict")
            or base.endswith("Protocol")
            or base.endswith("Generic")
        ):
            return True
    # Skip SQLAlchemy models (inherit from Base)
    for base in base_classes:
        if base == "Base":
            return True
    # Check for @dataclass decorator first (NDE2 needs to flag these)
    uses_dataclass = any(
        isinstance(deco, ast.Call)
        and isinstance(deco.func, ast.Name)
        and deco.func.id == "dataclass"
        for deco in cls.decorator_list
    )
    if uses_dataclass:
        return False  # Don't skip dataclasses, NDE2 needs to flag them
    # If we're in a DTO file, only skip the above types, don't skip others
    if is_dto_file:
        return False
    # If not in a DTO file, check if class looks like a DTO
    looks_like_dto = (
        "DTO" in cls.name
        or cls.name.endswith("Request")
        or cls.name.endswith("Response")
    )
    has_base_model = any("BaseModel" in b for b in base_classes)
    if not has_base_model and not looks_like_dto:
        return True
    return False


# ============================================================================
# NDE rules — No DTO in Repository/Engine
# Spec: docs/governance/architecture_linter.md §3.4
# ============================================================================


class NDE1Rule(Rule):
    """NDE-1: DTO files MUST NOT import from Repository/Engine/Service.

    Checks if any import in a *dto.py or *types.py file imports a
    module or name that contains 'Repository', 'Engine', or 'Service'
    (unless the module is a dto module itself).
    """

    rule_id = "NDE-1"
    default_severity = Severity.ERROR
    _FORBIDDEN_KEYWORDS: tuple[str, ...] = (
        "repository",
        "engine",
        "service",
    )

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        if not _is_dto_file(ctx.path):
            return
        for node, module_name in _iter_imports(ctx.tree):
            violation_yielded = False
            # Check if module is a dto module (ends with dto or types)
            is_dto_module = False
            if module_name:
                module_parts = module_name.split(".")
                last_part = module_parts[-1].lower() if module_parts else ""
                is_dto_module = last_part.endswith("dto") or last_part.endswith("types")

            if not is_dto_module:
                # Check module name (case-insensitive)
                lower_module_name = module_name.lower() if module_name else ""
                if module_name and any(
                    kw in lower_module_name for kw in self._FORBIDDEN_KEYWORDS
                ):
                    yield self.violation(
                        ctx,
                        node.lineno,
                        node.col_offset,
                        (
                            f"DTO file '{ctx.path.name}' must not import from "
                            f"Repository/Engine/Service (import: {module_name})"
                        ),
                    )
                    violation_yielded = True
                # Only check imported names if we didn't already yield a violation for module
                if not violation_yielded and isinstance(
                    node, (ast.Import, ast.ImportFrom)
                ):
                    for alias in node.names:
                        lower_alias_name = alias.name.lower()
                        if any(
                            kw in lower_alias_name for kw in self._FORBIDDEN_KEYWORDS
                        ):
                            yield self.violation(
                                ctx,
                                node.lineno,
                                node.col_offset,
                                (
                                    f"DTO file '{ctx.path.name}' must not import "
                                    f"Repository/Engine/Service (import: {alias.name})"
                                ),
                            )


class NDE2Rule(Rule):
    """NDE-2: DTOs MUST be BaseModel (Pydantic), not @dataclass or other.

    Checks if any class in a DTO file is using @dataclass instead of
    inheriting from BaseModel.
    """

    rule_id = "NDE-2"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        if not _is_dto_file(ctx.path):
            return
        for cls in _iter_classes(ctx.tree):
            if _is_non_dto_class(cls, for_nde3=False, is_dto_file=True):
                continue
            # Check if it's using @dataclass
            uses_dataclass = any(
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Name)
                and deco.func.id == "dataclass"
                for deco in cls.decorator_list
            )
            if uses_dataclass:
                yield self.violation(
                    ctx,
                    cls.lineno,
                    cls.col_offset,
                    (
                        f"DTO '{cls.name}' in '{ctx.path.name}' must be "
                        f"Pydantic BaseModel, not @dataclass"
                    ),
                )
            # Check if it inherits from BaseModel
            has_base_model = any("BaseModel" in b for b in _iter_base_classes(cls))
            if not uses_dataclass and not has_base_model:
                # If it's not a dataclass and doesn't inherit BaseModel, flag it
                yield self.violation(
                    ctx,
                    cls.lineno,
                    cls.col_offset,
                    (
                        f"DTO '{cls.name}' in '{ctx.path.name}' must inherit "
                        f"from Pydantic BaseModel"
                    ),
                )


class NDE3Rule(Rule):
    """NDE-3: DTOs MUST carry schema_version field.

    Checks if any class in a DTO file has a schema_version field.
    """

    rule_id = "NDE-3"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        if not _is_dto_file(ctx.path):
            return
        for cls in _iter_classes(ctx.tree):
            if _is_non_dto_class(cls, for_nde3=True, is_dto_file=True):
                continue
            has_schema_version = False
            # Check class body for assignments to schema_version
            for stmt in cls.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(
                    stmt.target, ast.Name
                ):
                    if stmt.target.id == "schema_version":
                        has_schema_version = True
                        break
                elif isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == "schema_version"
                        ):
                            has_schema_version = True
                            break
                    if has_schema_version:
                        break
            if not has_schema_version:
                yield self.violation(
                    ctx,
                    cls.lineno,
                    cls.col_offset,
                    (
                        f"DTO '{cls.name}' in '{ctx.path.name}' must have "
                        f"a 'schema_version' field"
                    ),
                )


# ============================================================================
# NUC rules — No UI in Core
# Spec: docs/governance/architecture_linter.md §3.5
# ============================================================================


class NUC1Rule(Rule):
    """NUC-1: core/ MUST NOT import from fastapi/starlette/flask/click/typer/rich/textual.

    Checks if any import in a file under core/ imports forbidden UI/web/CLI libraries.
    """

    rule_id = "NUC-1"
    default_severity = Severity.ERROR
    _FORBIDDEN_KEYWORDS: tuple[str, ...] = (
        "fastapi",
        "starlette",
        "flask",
        "click",
        "typer",
        "rich",
        "textual",
    )

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        # Check if file is in core/
        parts = ctx.path.parts
        if "core" not in parts:
            return
        for node, module_name in _iter_imports(ctx.tree):
            if module_name and any(
                kw in module_name for kw in self._FORBIDDEN_KEYWORDS
            ):
                yield self.violation(
                    ctx,
                    node.lineno,
                    node.col_offset,
                    (
                        f"core/ file '{ctx.path.name}' must not import "
                        f"from forbidden UI/web/CLI libraries (import: {module_name})"
                    ),
                )


class NUC2Rule(Rule):
    """NUC-2: core/ MUST NOT import from tkinter/pyqt/kivy/playwright.

    Checks if any import in a file under core/ imports forbidden GUI/browser libraries.
    """

    rule_id = "NUC-2"
    default_severity = Severity.ERROR
    _FORBIDDEN_KEYWORDS: tuple[str, ...] = (
        "tkinter",
        "pyqt",
        "kivy",
        "playwright",
    )

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        # Check if file is in core/
        parts = ctx.path.parts
        if "core" not in parts:
            return
        for node, module_name in _iter_imports(ctx.tree):
            lower_module_name = module_name.lower() if module_name else ""
            if module_name and any(
                kw in lower_module_name for kw in self._FORBIDDEN_KEYWORDS
            ):
                yield self.violation(
                    ctx,
                    node.lineno,
                    node.col_offset,
                    (
                        f"core/ file '{ctx.path.name}' must not import "
                        f"from forbidden GUI/browser libraries (import: {module_name})"
                    ),
                )


# ============================================================================
# NCP rules — No Cross-Phase Imports
# Spec: docs/governance/architecture_linter.md §3.6
# ============================================================================


def _is_in_frozen_phase(path: Path) -> bool:
    """Check if a file is in a frozen phase (1-13)."""
    parts = path.parts
    # Check for phase-specific directories (like core/phase13/, etc.)
    for part in parts:
        if part.startswith("phase") and len(part) > 5:
            try:
                phase_num = int(part[5:])
                if 1 <= phase_num <= 13:
                    return True
            except ValueError:
                pass
    return False


def _imports_non_frozen_phase(module_name: str) -> bool:
    """Check if an import is from a non-frozen phase (14+)."""
    if module_name and "phase" in module_name:
        parts = module_name.split(".")
        for part in parts:
            if part.startswith("phase") and len(part) > 5:
                try:
                    phase_num = int(part[5:])
                    if phase_num >= 14:
                        return True
                except ValueError:
                    pass
    return False


class NCP1Rule(Rule):
    """NCP-1: Frozen phase MUST NOT import from non-frozen phase.

    Checks if a file in a frozen phase (1-13) imports from a non-frozen phase (14+).
    """

    rule_id = "NCP-1"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        if not _is_in_frozen_phase(ctx.path):
            return
        for node, module_name in _iter_imports(ctx.tree):
            if module_name and _imports_non_frozen_phase(module_name):
                yield self.violation(
                    ctx,
                    node.lineno,
                    node.col_offset,
                    (
                        f"Frozen phase file '{ctx.path.name}' must not import "
                        f"from non-frozen phase (import: {module_name})"
                    ),
                )


# ============================================================================
# KG rules — M6-Specific (stubs, disabled by default)
# Spec: docs/governance/architecture_linter.md §5
# ============================================================================


class KG1Rule(Rule):
    """KG-1: core/memory/kg/inference_engine.py MUST NOT call await db.execute(...)."""

    rule_id = "KG-1"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        # Stub for M6
        yield from []


class KG2Rule(Rule):
    """KG-2: core/memory/kg/repository.py MUST NOT call LLM/embedding."""

    rule_id = "KG-2"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        yield from []


class KG3Rule(Rule):
    """KG-3: core/memory/kg/service.py MUST NOT bypass IKGRepository."""

    rule_id = "KG-3"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        yield from []


class KG4Rule(Rule):
    """KG-4: core/memory/kg/dto.py MUST NOT import from service.py or repository.py."""

    rule_id = "KG-4"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        yield from []


class KG5Rule(Rule):
    """KG-5: api/, cli/, ui/ MUST NOT import from core/memory/kg/ directly."""

    rule_id = "KG-5"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        yield from []


class KG6Rule(Rule):
    """KG-6: TraversalEngine MUST NOT write to kg_nodes or kg_edges tables."""

    rule_id = "KG-6"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        yield from []


class KG7Rule(Rule):
    """KG-7: InferenceEngine MUST NOT write to any table."""

    rule_id = "KG-7"
    default_severity = Severity.ERROR

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        yield from []


# ============================================================================
# CLI
# ============================================================================


def build_registry() -> RuleRegistry:
    """Build the default registry with all enabled rules.

    Rules are registered by sub-milestone:
    - LR-1..5 in M5.5.1.B
    - NBR-1..4 in M5.5.1.C
    - NSD-1..3 in M5.5.1.D (APPROVED 2026-07-03)
    - NDE-1..3, NUC-1..2 in M5.5.1.E
    - NCP-1..2, KG-1..7 (stubs) in M5.5.1.F
    """
    registry = RuleRegistry()
    registry.register(LR1Rule())
    registry.register(LR2Rule())
    registry.register(LR3Rule())
    registry.register(LR4Rule())
    registry.register(LR5Rule())
    registry.register(NBR1Rule())
    registry.register(NBR2Rule())
    registry.register(NBR3Rule())
    registry.register(NBR4Rule())
    registry.register(NSD1Rule())
    registry.register(NSD2Rule())
    registry.register(NSD3Rule())
    registry.register(NDE1Rule())
    registry.register(NDE2Rule())
    registry.register(NDE3Rule())
    registry.register(NUC1Rule())
    registry.register(NUC2Rule())
    registry.register(NCP1Rule())
    registry.register(KG1Rule())
    registry.register(KG2Rule())
    registry.register(KG3Rule())
    registry.register(KG4Rule())
    registry.register(KG5Rule())
    registry.register(KG6Rule())
    registry.register(KG7Rule())
    return registry


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point. Returns process exit code (0/1/2)."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="architecture_linter",
        description=(
            "Enforce JARVIS OS architectural rules "
            "(see docs/governance/architecture_linter.md)."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(".architecture-linter.toml"),
        help="Path to .architecture-linter.toml config file (default: CWD)",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("."),
        help="Root path to lint (default: current directory)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format (overrides config)",
    )
    parser.add_argument(
        "--fail-on",
        dest="fail_on",
        choices=["error", "warn", "info"],
        default=None,
        help="Minimum severity to fail on (overrides config)",
    )
    args = parser.parse_args(argv)

    try:
        if not args.config.exists():
            print(f"Config file not found: {args.config}", file=sys.stderr)
            return ExitCodeManager.EXIT_INTERNAL_ERROR
        config = LinterConfig.from_toml(args.config)
        if args.format is not None:
            config.output_format = args.format
        if args.fail_on is not None:
            config.fail_on = Severity(args.fail_on)

        registry = build_registry()
        linter = ArchitectureLinter(config=config, registry=registry)

        files = linter._collect_files(args.path)
        start = time.monotonic()
        violations = linter.lint(args.path)
        duration_ms = int((time.monotonic() - start) * 1000)

        report = linter.report(violations, len(files), duration_ms)
        reporter: Reporter = (
            JsonReporter() if config.output_format == "json" else TextReporter()
        )
        print(reporter.render(report))
        return ExitCodeManager.from_violations(violations, config.fail_on)
    except Exception as e:
        print(f"Internal linter error: {e}", file=sys.stderr)
        return ExitCodeManager.EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
