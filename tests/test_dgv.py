"""
Tests for the Dependency Graph Validator (M5.5.2).

Coverage target: >= 90%.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.architecture_linter import Severity
from scripts.dgv import (
    DependencyGraph,
    DependencyGraphValidator,
    DGVConfig,
    DGVDotReporter,
    DGVJsonReporter,
    DGVReport,
    DGVTextReporter,
    DGVViolation,
    Edge,
    GraphBuilder,
    _find_cycles,
    _get_layer,
    _is_external,
    _is_forbidden_connection,
    _is_layer_direction_violation,
    _path_to_module,
    _tarjan_scc,
    run,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a small fake repository structure for testing."""
    # Create a layered structure
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "memory").mkdir()
    (tmp_path / "core" / "memory" / "repository.py").write_text(
        "from core.memory.dto import MemoryDTO\n"
    )
    (tmp_path / "core" / "memory" / "dto.py").write_text(
        "from pydantic import BaseModel\nclass MemoryDTO(BaseModel):\n    pass\n"
    )
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "handlers.py").write_text(
        "from core.memory.repository import MemoryRepository\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("import os\n")
    return tmp_path


@pytest.fixture
def empty_graph() -> DependencyGraph:
    return DependencyGraph()


@pytest.fixture
def simple_graph() -> DependencyGraph:
    """A -> B -> C (no cycles)."""
    g = DependencyGraph()
    for n in ("a", "b", "c"):
        g.add_node(n)
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    return g


# ============================================================================
# Test: DependencyGraph
# ============================================================================


class TestDependencyGraph:
    def test_empty_graph(self) -> None:
        g = DependencyGraph()
        assert g.nodes == set()
        assert g.edges == set()

    def test_add_node(self) -> None:
        g = DependencyGraph()
        g.add_node("core.memory.repository")
        assert "core.memory.repository" in g.nodes
        assert g.successors("core.memory.repository") == set()

    def test_add_edge(self) -> None:
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        assert g.successors("a") == {"b"}
        assert g.predecessors("b") == {"a"}
        assert g.fan_out("a") == 1
        assert g.fan_in("b") == 1

    def test_self_loop_ignored(self) -> None:
        g = DependencyGraph()
        g.add_node("a")
        g.add_edge("a", "a")
        assert g.edges == set()
        assert g.fan_out("a") == 0

    def test_orphans_empty(self, simple_graph: DependencyGraph) -> None:
        assert simple_graph.orphans() == set()

    def test_orphans_isolated_node(self) -> None:
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_node("orphan")
        g.add_edge("a", "b")
        assert g.orphans() == {"orphan"}

    def test_orphans_skips_test_modules(self) -> None:
        g = DependencyGraph()
        g.add_node("tests.test_foo")
        g.add_node("orphan")
        assert g.orphans() == {"orphan"}


# ============================================================================
# Test: Path -> module name
# ============================================================================


class TestPathToModule:
    def test_regular_module(self) -> None:
        p = Path("core") / "memory" / "repository.py"
        assert _path_to_module(p, Path(".")) == "core.memory.repository"

    def test_init_file(self) -> None:
        p = Path("core") / "__init__.py"
        assert _path_to_module(p, Path(".")) == "core.__init__"

    def test_nested_init(self) -> None:
        p = Path("core") / "memory" / "__init__.py"
        assert _path_to_module(p, Path(".")) == "core.memory.__init__"


# ============================================================================
# Test: External module detection
# ============================================================================


class TestIsExternal:
    def test_third_party(self) -> None:
        assert _is_external("fastapi") is True
        assert _is_external("pydantic.BaseModel") is True

    def test_internal_layers(self) -> None:
        assert _is_external("core.memory.repository") is False
        assert _is_external("api.handlers") is False
        assert _is_external("cli.main") is False

    def test_empty(self) -> None:
        assert _is_external("") is True
        # Test None separately
        # assert _is_external(None) is True  # not used in production code


# ============================================================================
# Test: Layer direction
# ============================================================================


class TestLayerDirection:
    def test_get_layer(self) -> None:
        assert _get_layer("core.memory.x") == "core"
        assert _get_layer("api.handlers") == "api"
        assert _get_layer("fastapi") is None
        assert _get_layer("") is None

    def test_valid_direction_ui_to_core(self) -> None:
        # UI -> API (allowed)
        assert _is_layer_direction_violation("ui.main", "api.handlers") is False
        # API -> core (allowed)
        assert _is_layer_direction_violation("api.x", "core.x") is False

    def test_invalid_direction_core_to_api(self) -> None:
        # core -> api (NOT allowed)
        assert _is_layer_direction_violation("core.x", "api.x") is True

    def test_invalid_direction_api_to_ui(self) -> None:
        assert _is_layer_direction_violation("api.x", "ui.x") is True

    def test_same_layer_no_violation(self) -> None:
        assert _is_layer_direction_violation("core.x", "core.y") is False

    def test_external_modules_no_violation(self) -> None:
        assert _is_layer_direction_violation("core.x", "fastapi") is False


# ============================================================================
# Test: Forbidden connections
# ============================================================================


class TestForbidden:
    def test_core_to_api_forbidden(self) -> None:
        assert _is_forbidden_connection("core.x", "api.x") is True

    def test_api_to_core_not_in_set(self) -> None:
        # API -> core is allowed (it goes downstream direction)
        assert _is_forbidden_connection("api.x", "core.x") is False

    def test_tools_to_everything_forbidden(self) -> None:
        assert _is_forbidden_connection("tools.x", "core.x") is True
        assert _is_forbidden_connection("tools.x", "api.x") is True

    def test_external_not_forbidden(self) -> None:
        assert _is_forbidden_connection("core.x", "fastapi") is False


# ============================================================================
# Test: Tarjan's SCC
# ============================================================================


class TestTarjanSCC:
    def test_no_cycles(self, simple_graph: DependencyGraph) -> None:
        sccs = _tarjan_scc(simple_graph)
        # Each node should be its own SCC
        for scc in sccs:
            assert len(scc) == 1

    def test_two_node_cycle(self) -> None:
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        sccs = _tarjan_scc(g)
        big = [s for s in sccs if len(s) >= 2]
        assert len(big) == 1
        assert set(big[0]) == {"a", "b"}

    def test_three_node_cycle(self) -> None:
        g = DependencyGraph()
        for n in ("a", "b", "c"):
            g.add_node(n)
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", "a")
        sccs = _tarjan_scc(g)
        big = [s for s in sccs if len(s) >= 2]
        assert len(big) == 1
        assert set(big[0]) == {"a", "b", "c"}

    def test_self_loop(self) -> None:
        g = DependencyGraph()
        g.add_node("a")
        g.add_edge("a", "a")
        # Note: add_edge filters self-loops, so use direct graph manipulation
        g._adj["a"].add("a")
        g._rev_adj["a"].add("a")
        sccs = _tarjan_scc(g)
        _ = sccs
        cycles = _find_cycles(g)
        assert len(cycles) == 1
        assert cycles[0] == ["a"]


# ============================================================================
# Test: GraphBuilder
# ============================================================================


class TestGraphBuilder:
    def test_empty_repo(self, tmp_path: Path) -> None:
        builder = GraphBuilder(tmp_path)
        graph, modules = builder.build()
        assert graph.nodes == set()
        assert graph.edges == set()

    def test_simple_repo(self, tmp_repo: Path) -> None:
        builder = GraphBuilder(tmp_repo)
        graph, modules = builder.build()
        # Should find at least core.memory.repository, core.memory.dto, api.handlers
        assert "core.memory.repository" in graph.nodes
        assert "core.memory.dto" in graph.nodes
        assert "api.handlers" in graph.nodes

    def test_edges_detected(self, tmp_repo: Path) -> None:
        builder = GraphBuilder(tmp_repo)
        graph, _ = builder.build()
        # core.memory.repository should import core.memory.dto
        assert graph.successors("core.memory.repository") == {"core.memory.dto"}
        # api.handlers should import core.memory.repository
        assert graph.successors("api.handlers") == {"core.memory.repository"}

    def test_exclude(self, tmp_path: Path) -> None:
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "x.py").write_text("import os\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "t.py").write_text("import os\n")
        builder = GraphBuilder(tmp_path, exclude=["tests/"])
        graph, _ = builder.build()
        assert "core.x" in graph.nodes
        assert "tests.t" not in graph.nodes

    def test_syntax_error_handled(self, tmp_path: Path) -> None:
        (tmp_path / "broken.py").write_text("def broken(:\n  pass\n")
        builder = GraphBuilder(tmp_path)
        graph, _ = builder.build()  # should not raise
        assert "broken" in graph.nodes


# ============================================================================
# Test: Validator
# ============================================================================


class TestValidator:
    def test_no_violations(self, simple_graph: DependencyGraph) -> None:
        config = DGVConfig()
        validator = DependencyGraphValidator(config)
        violations = validator.validate(simple_graph)
        assert violations == []

    def test_cycle_detected(self) -> None:
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        config = DGVConfig()
        validator = DependencyGraphValidator(config)
        violations = validator.validate(g)
        cycle_violations = [v for v in violations if v.rule_id == "CYCLE-1"]
        assert len(cycle_violations) >= 1
        assert all(v.severity == Severity.ERROR for v in cycle_violations)

    def test_layer_direction_detected(self) -> None:
        g = DependencyGraph()
        g.add_node("core.x")
        g.add_node("api.y")
        g.add_edge("core.x", "api.y")
        config = DGVConfig()
        validator = DependencyGraphValidator(config)
        violations = validator.validate(g)
        dir_violations = [v for v in violations if v.rule_id == "LAYER-DIRECTION-1"]
        assert len(dir_violations) == 1

    def test_forbidden_detected(self) -> None:
        g = DependencyGraph()
        g.add_node("core.x")
        g.add_node("tools.y")
        g.add_edge("core.x", "tools.y")
        # core -> tools is not in forbidden set (memory/tools imports core, not vice versa)
        # Let's test core -> api
        g2 = DependencyGraph()
        g2.add_node("core.x")
        g2.add_node("api.y")
        g2.add_edge("core.x", "api.y")
        config = DGVConfig()
        validator = DependencyGraphValidator(config)
        violations = validator.validate(g2)
        forbidden = [v for v in violations if v.rule_id == "FORBIDDEN-1"]
        assert len(forbidden) == 1

    def test_orphan_detected(self) -> None:
        g = DependencyGraph()
        g.add_node("orphan")
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        config = DGVConfig()
        validator = DependencyGraphValidator(config)
        violations = validator.validate(g)
        orphans = [v for v in violations if v.rule_id == "ORPHAN-1"]
        assert len(orphans) == 1
        assert orphans[0].source_module == "orphan"
        assert orphans[0].severity == Severity.WARN

    def test_coupling_detected(self) -> None:
        g = DependencyGraph()
        # Create a node with high fan-out
        hub = "core.hub"
        g.add_node(hub)
        for i in range(25):
            target = f"core.target{i}"
            g.add_node(target)
            g.add_edge(hub, target)
        config = DGVConfig(coupling_threshold=20)
        validator = DependencyGraphValidator(config)
        violations = validator.validate(g)
        coupling = [v for v in violations if v.rule_id == "COUPLING-2"]
        assert len(coupling) == 1
        assert coupling[0].source_module == hub

    def test_disabled_rule(self) -> None:
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        g.add_edge("b", "a")
        config = DGVConfig(enable_cycle=False)
        validator = DependencyGraphValidator(config)
        violations = validator.validate(g)
        cycle_violations = [v for v in violations if v.rule_id == "CYCLE-1"]
        assert cycle_violations == []


# ============================================================================
# Test: Config
# ============================================================================


class TestConfig:
    def test_defaults(self) -> None:
        config = DGVConfig()
        assert config.fail_on == Severity.ERROR
        assert config.output_format == "text"
        assert config.coupling_threshold == 20
        assert config.enable_cycle is True
        assert config.enable_orphans is True

    def test_from_toml(self, tmp_path: Path) -> None:
        toml_path = tmp_path / ".dgv.toml"
        toml_path.write_text(
            """
[general]
fail_on = "warn"
output_format = "json"
render_png = true

[coupling]
threshold = 10

[rules]
cycle = { enabled = false }
orphans = { enabled = true }
"""
        )
        config = DGVConfig.from_toml(toml_path)
        assert config.fail_on == Severity.WARN
        assert config.output_format == "json"
        assert config.render_png is True
        assert config.coupling_threshold == 10
        assert config.enable_cycle is False
        assert config.enable_orphans is True

    def test_from_toml_minimal(self, tmp_path: Path) -> None:
        toml_path = tmp_path / ".dgv.toml"
        toml_path.write_text("")
        config = DGVConfig.from_toml(toml_path)
        assert config.fail_on == Severity.ERROR
        assert config.coupling_threshold == 20


# ============================================================================
# Test: DGVViolation
# ============================================================================


class TestDGVViolation:
    def test_to_dict(self) -> None:
        v = DGVViolation(
            rule_id="CYCLE-1",
            severity=Severity.ERROR,
            source_module="a",
            target_module="b",
            message="test",
        )
        d = v.to_dict()
        assert d["rule_id"] == "CYCLE-1"
        assert d["severity"] == "error"
        assert d["source_module"] == "a"
        assert d["target_module"] == "b"
        assert d["message"] == "test"


# ============================================================================
# Test: Reporters
# ============================================================================


class TestReporters:
    def _make_report(self) -> tuple[list[DGVViolation], DGVReport]:
        g = DependencyGraph()
        g.add_node("a")
        g.add_node("b")
        g.add_edge("a", "b")
        violations = [
            DGVViolation(
                rule_id="CYCLE-1",
                severity=Severity.ERROR,
                source_module="a",
                target_module="b",
                message="test cycle",
            )
        ]
        report = DGVReport(
            violations=tuple(violations),
            nodes_count=2,
            edges_count=1,
            cycles_count=0,
            duration_ms=10,
            graph=g,
        )
        return violations, report

    def test_text_reporter_with_violations(self) -> None:
        _violations, report = self._make_report()
        out = DGVTextReporter().render(report)
        assert "Dependency Graph Validator" in out
        assert "CYCLE-1" in out
        assert "a -> b" in out

    def test_text_reporter_no_violations(self) -> None:
        g = DependencyGraph()
        g.add_node("a")
        report = DGVReport(
            violations=(),
            nodes_count=1,
            edges_count=0,
            cycles_count=0,
            duration_ms=5,
            graph=g,
        )
        out = DGVTextReporter().render(report)
        assert "OK" in out
        assert "0 violations" in out

    def test_json_reporter(self) -> None:
        _violations, report = self._make_report()
        out = DGVJsonReporter().render(report)
        data = json.loads(out)
        assert data["tool"] == "dependency_graph_validator"
        assert data["files_scanned"] == 2
        assert len(data["violations"]) == 1
        assert data["summary"]["error"] == 1

    def test_dot_reporter(self) -> None:
        _violations, report = self._make_report()
        out = DGVDotReporter().render(report)
        assert "digraph dependencies" in out
        assert '"a" -> "b"' in out

    def test_dot_reporter_colors_violations(self) -> None:
        g = DependencyGraph()
        g.add_node("core.x")
        g.add_node("api.y")
        g.add_edge("core.x", "api.y")
        report = DGVReport(
            violations=(),
            nodes_count=2,
            edges_count=1,
            cycles_count=0,
            duration_ms=1,
            graph=g,
        )
        out = DGVDotReporter().render(report)
        # core -> api is a forbidden connection; should be red
        assert '[color="red"]' in out


# ============================================================================
# Test: Run end-to-end
# ============================================================================


class TestRun:
    def test_run_on_empty_repo(self, tmp_path: Path) -> None:
        config = DGVConfig()
        violations, report = run(tmp_path, config)
        assert violations == []
        assert report.nodes_count == 0

    def test_run_on_real_repo(self, tmp_repo: Path) -> None:
        config = DGVConfig()
        violations, report = run(tmp_repo, config)
        # core -> api is forbidden
        # The fixture has api/handlers.py importing core, so add a core -> api edge
        # to trigger the forbidden violation
        report.graph.add_edge("core.memory.dto", "api.handlers")
        # Re-run validation
        validator = DependencyGraphValidator(config)
        new_violations = validator.validate(report.graph)
        # Check that we now detect a forbidden connection
        assert any(
            v.rule_id == "FORBIDDEN-1"
            for v in new_violations
            if v.source_module == "core.memory.dto"
            and v.target_module == "api.handlers"
        )
        # Report should be populated
        assert report.nodes_count >= 4
        assert report.duration_ms >= 0

    def test_run_with_excludes(self, tmp_path: Path) -> None:
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "x.py").write_text("import os\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "t.py").write_text("import os\n")
        config = DGVConfig(exclude=["tests/"])
        violations, report = run(tmp_path, config)
        # tests.t should not be a node
        assert "tests.t" not in report.graph.nodes
        assert "core.x" in report.graph.nodes

    def test_run_performance_small_repo(self, tmp_path: Path) -> None:
        # Create a small repo with 10 modules
        for i in range(10):
            (tmp_path / f"m{i}.py").write_text("import os\n")
        config = DGVConfig()
        violations, report = run(tmp_path, config)
        # Should be fast
        assert report.duration_ms < 5000  # 5s budget

    def test_run_with_layer_violation(self, tmp_path: Path) -> None:
        """Test that we detect a layer direction violation in a real repo."""
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "x.py").write_text("from api.y import something\n")
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "y.py").write_text("import os\n")
        config = DGVConfig()
        violations, _ = run(tmp_path, config)
        # core -> api violates both layer direction and forbidden
        assert any(v.rule_id == "FORBIDDEN-1" for v in violations)
        assert any(v.rule_id == "LAYER-DIRECTION-1" for v in violations)

    def test_run_with_orphan(self, tmp_path: Path) -> None:
        """Test that we detect orphaned modules."""
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "used.py").write_text("import os\n")
        (tmp_path / "core" / "orphan.py").write_text("import os\n")
        config = DGVConfig()
        violations, _ = run(tmp_path, config)
        # Both modules are orphans (no imports between them)
        assert any(
            v.rule_id == "ORPHAN-1" and "orphan" in v.source_module for v in violations
        )

    def test_run_with_external_imports(self, tmp_path: Path) -> None:
        """Test that we ignore third-party imports."""
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "x.py").write_text(
            "import fastapi\nimport pydantic\nfrom fastapi import FastAPI\n"
        )
        config = DGVConfig()
        violations, _ = run(tmp_path, config)
        # No forbidden connections (external imports are ignored)
        assert not any(v.rule_id == "FORBIDDEN-1" for v in violations)


# ============================================================================
# Test: Edge dataclass
# ============================================================================


class TestEdge:
    def test_edge_equality(self) -> None:
        e1 = Edge(source="a", target="b")
        e2 = Edge(source="a", target="b")
        assert e1 == e2
        assert e1 != Edge(source="a", target="c")

    def test_edge_hashable(self) -> None:
        e1 = Edge(source="a", target="b")
        s = {e1, Edge(source="a", target="b")}
        assert len(s) == 1


# ============================================================================
# Test: Main CLI
# ============================================================================


class TestMain:
    def test_main_on_clean_repo(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test main() runs successfully on a clean repo."""
        from scripts.dgv import main

        # Empty repo
        actual_exit_code = main([str(tmp_path)])
        assert actual_exit_code == 0
        captured = capsys.readouterr()
        assert "OK" in captured.out

    def test_main_with_violations(self, tmp_path: Path) -> None:
        """Test main() returns non-zero exit code when violations exist."""
        from scripts.dgv import main

        # Create a repo with a forbidden connection
        (tmp_path / "core").mkdir()
        (tmp_path / "core" / "x.py").write_text("from api.y import z\n")
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "y.py").write_text("import os\n")
        actual_exit_code = main([str(tmp_path)])
        assert actual_exit_code == 1

    def test_main_with_json_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test main() can output JSON format."""
        from scripts.dgv import main

        config_path = tmp_path / ".dgv.toml"
        config_path.write_text(
            """
[general]
output_format = "json"
"""
        )
        actual_exit_code = main([str(tmp_path)])
        assert actual_exit_code == 0
        captured = capsys.readouterr()
        # JSON output should be valid
        data = json.loads(captured.out)
        assert data["tool"] == "dependency_graph_validator"

    def test_dot_file_generated(self, tmp_path: Path) -> None:
        """Test that DOT file is generated in docs/diagrams/."""
        from scripts.dgv import main

        main([str(tmp_path)])  # No return value assigned here as it's not used.
        dot_path = tmp_path / "docs" / "diagrams" / "dependency_graph.dot"
        assert dot_path.exists()
        content = dot_path.read_text(encoding="utf-8")
        assert "digraph dependencies" in content
