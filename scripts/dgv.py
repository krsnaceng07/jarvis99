"""
PHASE: 19 / M5.5.2
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/governance/dependency_graph_validator.md
    docs/phases/phase19/m5_5_engineering_governance_freeze.md

IMPLEMENTATION PLAN:
    docs/phases/phase19/m5_5_2_dependency_graph_validator_implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from scripts.architecture_linter import (
    ExitCodeManager,
    Severity,
    _iter_imports,
)

# ============================================================================
# Contracts (frozen in docs/governance/dependency_graph_validator.md §6, §7)
# ============================================================================


@dataclass(frozen=True)
class DGVViolation:
    """A single DGV violation. Immutable per spec §7 invariants.

    Attributes:
        rule_id: e.g. "CYCLE-1", "FORBIDDEN-1", "COUPLING-1"
        severity: one of Severity.*
        source_module: the module that has the issue
        target_module: the related module (cycle member, forbidden target, etc.)
        message: human-readable explanation
    """

    rule_id: str
    severity: Severity
    source_module: str
    target_module: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "source_module": self.source_module,
            "target_module": self.target_module,
            "message": self.message,
        }


@dataclass
class DGVConfig:
    """Parsed `.dgv.toml` configuration.

    Defaults follow the frozen spec §7.
    """

    fail_on: Severity = Severity.ERROR
    output_format: str = "text"
    output_path: Optional[Path] = None
    render_png: bool = False
    coupling_threshold: int = 20
    enable_cycle: bool = True
    enable_layer_direction: bool = True
    enable_forbidden: bool = True
    enable_orphans: bool = True
    enable_coupling: bool = True
    exclude: list[str] = field(default_factory=list)

    @classmethod
    def from_toml(cls, path: Path) -> "DGVConfig":
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, object]) -> "DGVConfig":
        general = data.get("general", {})
        if not isinstance(general, dict):
            general = {}
        fail_on = Severity(str(general.get("fail_on", "error")))
        output_format = str(general.get("output_format", "text"))
        output_path_str = general.get("output_path")
        output_path = Path(str(output_path_str)) if output_path_str else None
        render_png = bool(general.get("render_png", False))
        exclude = [str(x) for x in general.get("exclude", [])]

        coupling_obj = data.get("coupling", {})
        if not isinstance(coupling_obj, dict):
            coupling_obj = {}
        coupling_threshold = int(coupling_obj.get("threshold", 20))

        rules_obj = data.get("rules", {})
        if not isinstance(rules_obj, dict):
            rules_obj = {}

        def _enabled(name: str) -> bool:
            cfg = rules_obj.get(name, {})
            if not isinstance(cfg, dict):
                return True
            return bool(cfg.get("enabled", True))

        return cls(
            fail_on=fail_on,
            output_format=output_format,
            output_path=output_path,
            render_png=render_png,
            coupling_threshold=coupling_threshold,
            enable_cycle=_enabled("cycle"),
            enable_layer_direction=_enabled("layer_direction"),
            enable_forbidden=_enabled("forbidden"),
            enable_orphans=_enabled("orphans"),
            enable_coupling=_enabled("coupling"),
            exclude=exclude,
        )


# ============================================================================
# Graph data structure
# ============================================================================


@dataclass(frozen=True)
class Edge:
    """A directed edge in the dependency graph.

    Attributes:
        source: source module dotted path (e.g. "core.memory.repository")
        target: target module dotted path (e.g. "core.memory.dto")
    """

    source: str
    target: str


@dataclass
class DependencyGraph:
    """Module-level dependency graph.

    Nodes are module dotted paths; edges are import statements.
    """

    nodes: set[str] = field(default_factory=set)
    edges: set[Edge] = field(default_factory=set)
    # Adjacency list: source -> set of targets
    _adj: dict[str, set[str]] = field(default_factory=dict)
    # Reverse adjacency: target -> set of sources (for fan-in computation)
    _rev_adj: dict[str, set[str]] = field(default_factory=dict)

    def add_node(self, module: str) -> None:
        self.nodes.add(module)
        self._adj.setdefault(module, set())
        self._rev_adj.setdefault(module, set())

    def add_edge(self, source: str, target: str) -> None:
        if source == target:
            return
        edge = Edge(source, target)
        self.edges.add(edge)
        self._adj[source].add(target)
        self._rev_adj[target].add(source)

    def successors(self, node: str) -> set[str]:
        return set(self._adj.get(node, set()))

    def predecessors(self, node: str) -> set[str]:
        return set(self._rev_adj.get(node, set()))

    def fan_out(self, node: str) -> int:
        return len(self._adj.get(node, set()))

    def fan_in(self, node: str) -> int:
        return len(self._rev_adj.get(node, set()))

    def orphans(self) -> set[str]:
        """Return nodes with no incoming AND no outgoing edges (excluding test/entry points)."""
        result: set[str] = set()
        for node in self.nodes:
            if not self._adj.get(node) and not self._rev_adj.get(node):
                # Skip __init__.py and test files
                parts = node.split(".")
                if "tests" in parts or "__init__" in parts or "test_" in parts[-1]:
                    continue
                result.add(node)
        return result


# ============================================================================
# Module path resolution
# ============================================================================


def _path_to_module(rel_path: Path, root: Path) -> str:
    """Convert a relative .py file path to a dotted module name.

    Example: `core/memory/repository.py` -> `core.memory.repository`
             `core/__init__.py`             -> `core.__init__`
    """
    parts = list(rel_path.parts)
    if parts[-1] == "__init__.py":
        parts[-1] = "__init__"
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _resolve_module_to_path(module: str, modules: dict[str, Path]) -> Optional[Path]:
    """Resolve a dotted module name to a file path using the collected module map."""
    return modules.get(module)


# ============================================================================
# Graph builder
# ============================================================================


def _is_external(module: str) -> bool:
    """Return True if the module is a third-party/external package.

    External modules are those whose top-level segment is not one of our layers.
    """
    if not module:
        return True
    head = module.split(".")[0]
    layer_prefixes = (
        "core",
        "api",
        "ui",
        "cli",
        "brain",
        "memory",
        "tools",
        "tests",
        "scripts",
    )
    return head not in layer_prefixes


class GraphBuilder:
    """Builds a module-level dependency graph by walking a directory tree."""

    def __init__(self, root: Path, exclude: list[str] | None = None) -> None:
        self.root = root
        self.exclude = exclude or []

    def build(self) -> tuple[DependencyGraph, dict[str, Path]]:
        """Walk files, parse imports, and build the dependency graph.

        Returns:
            (graph, modules) where modules maps dotted module name -> file path.
        """
        graph = DependencyGraph()
        modules: dict[str, Path] = {}

        files = self._collect_files()
        # First pass: collect all module names
        for file_path in files:
            rel = file_path.relative_to(self.root)
            module_name = _path_to_module(rel, self.root)
            graph.add_node(module_name)
            modules[module_name] = file_path

        # Second pass: parse imports and add edges
        for file_path in files:
            rel = file_path.relative_to(self.root)
            module_name = _path_to_module(rel, self.root)
            try:
                source = file_path.read_text(encoding="utf-8")
            except OSError:
                continue
            try:
                tree = ast.parse(source, filename=str(file_path))
            except SyntaxError:
                continue
            self._process_imports(graph, module_name, tree, modules)

        return graph, modules

    def _collect_files(self) -> list[Path]:
        """Return sorted list of .py files under root, respecting exclude globs."""
        files: list[Path] = []
        for p in self.root.rglob("*.py"):
            if not p.is_file():
                continue
            try:
                rel = p.relative_to(self.root)
                rel_str = rel.as_posix()
            except ValueError:
                rel_str = p.as_posix()
            if any(rel_str.startswith(ex) for ex in self.exclude):
                continue
            files.append(p)
        return sorted(files)

    def _process_imports(
        self,
        graph: DependencyGraph,
        source_module: str,
        tree: ast.Module,
        modules: dict[str, Path],
    ) -> None:
        """Parse imports in the tree and add edges to the graph."""
        for _node, module_name in _iter_imports(tree):
            if not module_name or _is_external(module_name):
                continue
            # Try to find the target module
            target = self._resolve_target(module_name, modules)
            if target is None:
                # External-ish but starts with known prefix; might be a missing module
                # Still add as node so we can flag it later
                target = module_name
                graph.add_node(target)
            graph.add_edge(source_module, target)

    def _resolve_target(
        self, module_name: str, modules: dict[str, Path]
    ) -> Optional[str]:
        """Resolve an imported module name to a known internal module, or None."""
        if module_name in modules:
            return module_name
        # Try parent packages (e.g. "core.memory" might be a package, not a module)
        parts = module_name.split(".")
        for i in range(len(parts), 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in modules:
                return candidate
        return None


# ============================================================================
# Tarjan's algorithm for strongly connected components (cycle detection)
# ============================================================================


def _tarjan_scc(graph: DependencyGraph) -> list[list[str]]:
    """Compute strongly connected components using Tarjan's algorithm.

    Returns a list of SCCs. Each SCC is a list of node names. SCCs of size
    >= 2 (or self-loops) indicate cycles.
    """
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        # Iterative implementation to avoid recursion limits on large graphs
        work_stack: list[tuple[str, Iterator[str]]] = [(v, iter(graph.successors(v)))]
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        while work_stack:
            node, successors = work_stack[-1]
            try:
                w = next(successors)
            except StopIteration:
                if lowlink[node] == index[node]:
                    component: list[str] = []
                    while True:
                        w2 = stack.pop()
                        on_stack[w2] = False
                        component.append(w2)
                        if w2 == node:
                            break
                    sccs.append(component)
                work_stack.pop()
                if work_stack:
                    parent = work_stack[-1][0]
                    lowlink[parent] = min(lowlink[parent], lowlink[node])
                continue

            if w not in index:
                index[w] = index_counter[0]
                lowlink[w] = index_counter[0]
                index_counter[0] += 1
                stack.append(w)
                on_stack[w] = True
                work_stack.append((w, iter(graph.successors(w))))
            elif on_stack.get(w, False):
                lowlink[node] = min(lowlink[node], index[w])

    for node in graph.nodes:
        if node not in index:
            strongconnect(node)

    return sccs


def _find_cycles(graph: DependencyGraph) -> list[list[str]]:
    """Find all cycles in the graph (SCCs of size >= 2 or with self-loops)."""
    cycles: list[list[str]] = []
    for scc in _tarjan_scc(graph):
        if len(scc) >= 2:
            cycles.append(sorted(scc))
        elif len(scc) == 1:
            # Self-loop check
            node = scc[0]
            if node in graph.successors(node):
                cycles.append([node])
    return cycles


# ============================================================================
# Validation rules
# ============================================================================

# Layer ranks (mirrors architecture_linter.py LR-5)
_LAYER_RANKS: dict[str, int] = {
    "ui": 0,
    "api": 1,
    "cli": 1,
    "brain": 2,
    "core": 2,
    "memory": 3,
    "tools": 3,
}


def _get_layer(module: str) -> Optional[str]:
    """Return the top-level layer of a module name, or None if external/empty."""
    if not module:
        return None
    head = module.split(".")[0]
    return head if head in _LAYER_RANKS else None


def _is_layer_direction_violation(source: str, target: str) -> bool:
    """Check if a source -> target edge violates layer direction rules.

    Returns True if importing from a "more upstream" layer (lower rank = more
    downstream; higher rank = more upstream). Imports must go from low rank
    to high rank (same or deeper).
    """
    src_layer = _get_layer(source)
    tgt_layer = _get_layer(target)
    if src_layer is None or tgt_layer is None:
        return False
    if src_layer == tgt_layer:
        return False
    src_rank = _LAYER_RANKS[src_layer]
    tgt_rank = _LAYER_RANKS[tgt_layer]
    return tgt_rank < src_rank


# Forbidden connections: pairs of layers that must NEVER import each other
_FORBIDDEN_CONNECTIONS: set[tuple[str, str]] = {
    ("core", "api"),
    ("core", "ui"),
    ("core", "cli"),
    ("brain", "api"),
    ("brain", "ui"),
    ("brain", "cli"),
    ("memory", "api"),
    ("memory", "ui"),
    ("memory", "cli"),
    ("memory", "brain"),
    ("memory", "core"),
    ("tools", "api"),
    ("tools", "ui"),
    ("tools", "cli"),
    ("tools", "brain"),
    ("tools", "core"),
    ("tools", "memory"),
}


def _is_forbidden_connection(source: str, target: str) -> bool:
    """Check if source -> target is a forbidden connection."""
    src_layer = _get_layer(source)
    tgt_layer = _get_layer(target)
    if src_layer is None or tgt_layer is None:
        return False
    return (src_layer, tgt_layer) in _FORBIDDEN_CONNECTIONS


# ============================================================================
# Validator
# ============================================================================


class DependencyGraphValidator:
    """Validates a dependency graph against architectural rules.

    Yields DGVViolation objects for each rule violation found.
    """

    def __init__(self, config: DGVConfig) -> None:
        self.config = config

    def validate(self, graph: DependencyGraph) -> list[DGVViolation]:
        """Run all enabled validation rules against the graph."""
        violations: list[DGVViolation] = []
        if self.config.enable_cycle:
            violations.extend(self._check_cycles(graph))
        if self.config.enable_layer_direction:
            violations.extend(self._check_layer_direction(graph))
        if self.config.enable_forbidden:
            violations.extend(self._check_forbidden(graph))
        if self.config.enable_orphans:
            violations.extend(self._check_orphans(graph))
        if self.config.enable_coupling:
            violations.extend(self._check_coupling(graph))
        return violations

    def _check_cycles(self, graph: DependencyGraph) -> Iterator[DGVViolation]:
        """Check for circular dependencies."""
        cycles = _find_cycles(graph)
        for cycle in cycles:
            for member in cycle:
                yield DGVViolation(
                    rule_id="CYCLE-1",
                    severity=Severity.ERROR,
                    source_module=member,
                    target_module=" -> ".join(cycle),
                    message=(
                        f"Circular dependency detected involving module "
                        f"'{member}' (cycle: {' -> '.join(cycle)})"
                    ),
                )

    def _check_layer_direction(self, graph: DependencyGraph) -> Iterator[DGVViolation]:
        """Check layer direction violations."""
        for edge in sorted(graph.edges, key=lambda e: (e.source, e.target)):
            if _is_layer_direction_violation(edge.source, edge.target):
                src_layer = _get_layer(edge.source)
                tgt_layer = _get_layer(edge.target)
                yield DGVViolation(
                    rule_id="LAYER-DIRECTION-1",
                    severity=Severity.ERROR,
                    source_module=edge.source,
                    target_module=edge.target,
                    message=(
                        f"Layer direction violation: '{edge.source}' ({src_layer}) "
                        f"cannot import from '{edge.target}' ({tgt_layer}) "
                        f"(UI->API->Brain->Memory+Tools direction)"
                    ),
                )

    def _check_forbidden(self, graph: DependencyGraph) -> Iterator[DGVViolation]:
        """Check for forbidden layer connections."""
        for edge in sorted(graph.edges, key=lambda e: (e.source, e.target)):
            if _is_forbidden_connection(edge.source, edge.target):
                src_layer = _get_layer(edge.source)
                tgt_layer = _get_layer(edge.target)
                yield DGVViolation(
                    rule_id="FORBIDDEN-1",
                    severity=Severity.ERROR,
                    source_module=edge.source,
                    target_module=edge.target,
                    message=(
                        f"Forbidden connection: '{edge.source}' ({src_layer}) "
                        f"must not import from '{edge.target}' ({tgt_layer})"
                    ),
                )

    def _check_orphans(self, graph: DependencyGraph) -> Iterator[DGVViolation]:
        """Check for orphaned modules (no incoming or outgoing edges)."""
        for node in sorted(graph.orphans()):
            yield DGVViolation(
                rule_id="ORPHAN-1",
                severity=Severity.WARN,
                source_module=node,
                target_module="",
                message=(
                    f"Orphaned module '{node}' has no incoming or outgoing dependencies"
                ),
            )

    def _check_coupling(self, graph: DependencyGraph) -> Iterator[DGVViolation]:
        """Check for modules with excessive fan-in or fan-out."""
        threshold = self.config.coupling_threshold
        for node in sorted(graph.nodes):
            fan_in = graph.fan_in(node)
            fan_out = graph.fan_out(node)
            if fan_in > threshold:
                yield DGVViolation(
                    rule_id="COUPLING-1",
                    severity=Severity.WARN,
                    source_module=node,
                    target_module="",
                    message=(
                        f"Module '{node}' has high fan-in ({fan_in} > {threshold}); "
                        f"consider refactoring"
                    ),
                )
            if fan_out > threshold:
                yield DGVViolation(
                    rule_id="COUPLING-2",
                    severity=Severity.WARN,
                    source_module=node,
                    target_module="",
                    message=(
                        f"Module '{node}' has high fan-out ({fan_out} > {threshold}); "
                        f"consider refactoring"
                    ),
                )


# ============================================================================
# Reporters
# ============================================================================


@dataclass(frozen=True)
class DGVReport:
    """DGV output. Frozen so it can be safely shared across reporters."""

    violations: tuple[DGVViolation, ...]
    nodes_count: int
    edges_count: int
    cycles_count: int
    duration_ms: int
    graph: DependencyGraph

    def to_dict(self) -> dict[str, object]:
        violations_list = list(self.violations)
        return {
            "schema_version": "1.0",
            "tool": "dependency_graph_validator",
            "files_scanned": self.nodes_count,
            "edges": self.edges_count,
            "cycles": self.cycles_count,
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


class DGVReporter:
    """Base class for DGV reporters."""

    def render(self, report: DGVReport) -> str:
        raise NotImplementedError


class DGVTextReporter(DGVReporter):
    """Human-readable text output."""

    def render(self, report: DGVReport) -> str:
        if not report.violations:
            return (
                f"OK: {report.nodes_count} modules, {report.edges_count} edges, "
                f"{report.cycles_count} cycles, 0 violations ({report.duration_ms}ms)"
            )
        header = (
            f"Dependency Graph Validator: {len(report.violations)} violations "
            f"({report.nodes_count} modules, {report.edges_count} edges, "
            f"{report.cycles_count} cycles, {report.duration_ms}ms)"
        )
        lines: list[str] = [header, ""]
        for v in sorted(
            report.violations,
            key=lambda x: (x.source_module, x.target_module, x.rule_id),
        ):
            lines.append(
                f"{v.severity.value.upper():5s} {v.rule_id} {v.source_module}"
                + (f" -> {v.target_module}" if v.target_module else "")
            )
            lines.append(f"      {v.message}")
            lines.append("")
        return "\n".join(lines)


class DGVJsonReporter(DGVReporter):
    """Machine-readable JSON output."""

    def render(self, report: DGVReport) -> str:
        return json.dumps(report.to_dict(), indent=2, sort_keys=True)


class DGVDotReporter(DGVReporter):
    """Graphviz DOT output for the dependency graph."""

    def render(self, report: DGVReport) -> str:
        lines: list[str] = ["digraph dependencies {"]
        lines.append("  rankdir=LR;")
        lines.append("  node [shape=box, style=rounded];")
        # Group nodes by layer for cleaner visualization
        for node in sorted(report.graph.nodes):
            layer = _get_layer(node) or "other"
            color = _layer_color(layer)
            safe_node = node.replace('"', '\\"')
            lines.append(f'  "{safe_node}" [color="{color}"];')
        for edge in sorted(report.graph.edges, key=lambda e: (e.source, e.target)):
            color = (
                "red"
                if _is_forbidden_connection(edge.source, edge.target)
                or _is_layer_direction_violation(edge.source, edge.target)
                else "black"
            )
            safe_src = edge.source.replace('"', '\\"')
            safe_tgt = edge.target.replace('"', '\\"')
            lines.append(f'  "{safe_src}" -> "{safe_tgt}" [color="{color}"];')
        lines.append("}")
        return "\n".join(lines)


def _layer_color(layer: str) -> str:
    """Return a color for a layer in DOT output."""
    return {
        "ui": "lightblue",
        "api": "lightgreen",
        "cli": "lightyellow",
        "brain": "lightpink",
        "core": "lightgray",
        "memory": "orange",
        "tools": "lightcoral",
    }.get(layer, "white")


class DGVPngRenderer:
    """Renders DOT output to PNG using Graphviz (optional)."""

    def __init__(self, dot_path: Path, png_path: Path) -> None:
        self.dot_path = dot_path
        self.png_path = png_path

    def render(self) -> bool:
        """Render DOT to PNG. Returns True on success, False if Graphviz is missing."""
        if shutil.which("dot") is None:
            return False
        try:
            subprocess.run(
                [
                    "dot",
                    "-Tpng",
                    str(self.dot_path),
                    "-o",
                    str(self.png_path),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            return False


# ============================================================================
# Main entry point
# ============================================================================


def run(
    root: Path,
    config: DGVConfig,
) -> tuple[list[DGVViolation], DGVReport]:
    """Run the DGV against a directory tree.

    Returns (violations, report) for testing/inspection.
    """
    start = time.perf_counter()
    builder = GraphBuilder(root, exclude=config.exclude)
    graph, _modules = builder.build()
    validator = DependencyGraphValidator(config)
    violations = validator.validate(graph)
    cycles = _find_cycles(graph)
    duration_ms = int((time.perf_counter() - start) * 1000)
    report = DGVReport(
        violations=tuple(violations),
        nodes_count=len(graph.nodes),
        edges_count=len(graph.edges),
        cycles_count=len(cycles),
        duration_ms=duration_ms,
        graph=graph,
    )
    return violations, report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns process exit code."""
    argv = argv if argv is not None else sys.argv[1:]
    if argv and any(arg.startswith("-") for arg in argv):
        print("Usage: python scripts/dgv.py [path_to_scan]", file=sys.stderr)
        print(
            "Error: Options starting with '-' are not supported in CLI. Use .dgv.toml for configuration.",
            file=sys.stderr,
        )
        return ExitCodeManager.EXIT_INTERNAL_ERROR

    root = Path(argv[0]) if argv else Path(".")
    config_path = root / ".dgv.toml"

    config = DGVConfig.from_toml(config_path) if config_path.exists() else DGVConfig()
    violations, report = run(root, config)

    if config.output_format == "json":
        reporter: DGVReporter = DGVJsonReporter()
    else:
        reporter = DGVTextReporter()

    output = reporter.render(report)
    if config.output_path:
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        config.output_path.write_text(output, encoding="utf-8")
    else:
        print(output)

    # DOT output (always generated when output_format is dot, or alongside)
    dot_reporter = DGVDotReporter()
    dot_output = dot_reporter.render(report)
    dot_path = root / "docs" / "diagrams" / "dependency_graph.dot"
    dot_path.parent.mkdir(parents=True, exist_ok=True)
    dot_path.write_text(dot_output, encoding="utf-8")

    # Optional PNG
    if config.render_png:
        png_path = dot_path.with_suffix(".png")
        png_renderer = DGVPngRenderer(dot_path, png_path)
        if not png_renderer.render():
            print(
                "Warning: Graphviz 'dot' not found; PNG not generated",
                file=sys.stderr,
            )

    # Exit code
    rank = {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}[config.fail_on]
    for v in violations:
        if {Severity.INFO: 0, Severity.WARN: 1, Severity.ERROR: 2}[v.severity] >= rank:
            return ExitCodeManager.EXIT_VIOLATIONS
    return ExitCodeManager.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
