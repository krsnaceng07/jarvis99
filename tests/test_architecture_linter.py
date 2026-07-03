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

import json
from pathlib import Path
from typing import Iterator

import pytest

from scripts.architecture_linter import (
    ArchitectureLinter,
    ExitCodeManager,
    FileContext,
    JsonReporter,
    LinterConfig,
    LR1Rule,
    LR2Rule,
    LR3Rule,
    LR4Rule,
    LR5Rule,
    NBR1Rule,
    NBR2Rule,
    NBR3Rule,
    NBR4Rule,
    NSD1Rule,
    NSD2Rule,
    NSD3Rule,
    Report,
    Rule,
    RuleRegistry,
    Severity,
    TextReporter,
    Violation,
    main,
)

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


class _NoOpRule(Rule):
    """A rule that never emits a violation. Used for registry tests."""

    rule_id = "TEST-1"
    default_severity = Severity.INFO

    def check(self, ctx: FileContext) -> Iterator[Violation]:
        return iter(())


def _make_report() -> Report:
    return Report(
        violations=(
            Violation(
                rule_id="LR-1",
                severity=Severity.ERROR,
                file=Path("a.py"),
                line=10,
                col=1,
                message="layer violation",
                snippet="from api import x",
            ),
        ),
        files_scanned=3,
        duration_ms=42,
    )


# ----------------------------------------------------------------------------
# Contract types
# ----------------------------------------------------------------------------


def test_violation_is_frozen_dataclass() -> None:
    v = Violation(
        rule_id="LR-1",
        severity=Severity.ERROR,
        file=Path("a.py"),
        line=1,
        col=1,
        message="test",
    )
    with pytest.raises(AttributeError):
        v.rule_id = "X-1"  # type: ignore[misc]
    d = v.to_dict()
    assert d["rule_id"] == "LR-1"
    assert d["severity"] == "error"
    assert d["line"] == 1
    assert d["file"] == "a.py"


def test_severity_values() -> None:
    assert Severity.ERROR.value == "error"
    assert Severity.WARN.value == "warn"
    assert Severity.INFO.value == "info"


def test_default_config_enables_all_six_categories() -> None:
    cfg = LinterConfig()
    for cat in ("LR", "NBR", "NSD", "NDE", "NUC", "NCP"):
        assert cat in cfg.enabled_categories
    # KG is opt-in (M6+)
    assert "KG" not in cfg.enabled_categories


def test_config_from_toml_minimal(tmp_path: Path) -> None:
    cfg_file = tmp_path / ".architecture-linter.toml"
    cfg_file.write_text('[general]\nseverity_default = "warn"\nexclude = ["tests/"]\n')
    cfg = LinterConfig.from_toml(cfg_file)
    assert cfg.severity_default == Severity.WARN
    assert "tests/" in cfg.exclude
    assert cfg.output_format == "text"


def test_config_from_toml_category_severity(tmp_path: Path) -> None:
    cfg_file = tmp_path / ".architecture-linter.toml"
    cfg_file.write_text(
        '[general]\nseverity_default = "error"\n\n'
        '[rules.LR]\nenabled = true\nseverity = "warn"\n'
        "[rules.KG]\nenabled = false\n"
    )
    cfg = LinterConfig.from_toml(cfg_file)
    assert "LR" in cfg.enabled_categories
    assert "KG" not in cfg.enabled_categories
    assert cfg.category_severity["LR"] == Severity.WARN
    assert cfg.get_severity("LR-1") == Severity.WARN
    assert cfg.get_severity("NBR-1") == Severity.ERROR


# ----------------------------------------------------------------------------
# Rule infrastructure
# ----------------------------------------------------------------------------


def test_registry_register_and_dedup() -> None:
    reg = RuleRegistry()
    reg.register(_NoOpRule())
    with pytest.raises(ValueError, match="Duplicate"):
        reg.register(_NoOpRule())
    assert reg.get("TEST-1") is not None
    assert reg.get("MISSING") is None
    assert len(reg.all()) == 1


def test_registry_rejects_empty_rule_id() -> None:
    class _Empty(Rule):
        rule_id = ""
        default_severity = Severity.ERROR

        def check(self, ctx: FileContext) -> Iterator[Violation]:
            return iter(())

    with pytest.raises(ValueError, match="rule_id must be set"):
        RuleRegistry().register(_Empty())


def test_registry_is_enabled_by_category() -> None:
    reg = RuleRegistry()
    reg.register(_NoOpRule())
    cfg_default = LinterConfig()
    assert reg.is_enabled("TEST-1", cfg_default) is False  # category TEST not enabled
    cfg_test = LinterConfig(enabled_categories={"TEST"})
    assert reg.is_enabled("TEST-1", cfg_test) is True


def test_rule_violation_helper_captures_snippet(tmp_path: Path) -> None:
    class _R(Rule):
        rule_id = "LR-TEST"  # category LR is enabled by default
        default_severity = Severity.ERROR

        def check(self, ctx: FileContext) -> Iterator[Violation]:
            return iter([self.violation(ctx, 1, 1, "boom")])

    reg = RuleRegistry()
    reg.register(_R())
    target = tmp_path / "f.py"
    target.write_text("import os  # the offending line\n")
    linter = ArchitectureLinter(LinterConfig(), reg)
    violations = linter._lint_file(target)
    assert len(violations) == 1
    assert violations[0].message == "boom"
    assert "offending line" in violations[0].snippet


# ----------------------------------------------------------------------------
# Reporters
# ----------------------------------------------------------------------------


def test_text_reporter_clean_run() -> None:
    r = TextReporter()
    out = r.render(Report(violations=(), files_scanned=5, duration_ms=12))
    assert "OK" in out
    assert "5 files" in out
    assert "0 violations" in out


def test_text_reporter_with_violations_is_deterministic() -> None:
    out_a = TextReporter().render(_make_report())
    out_b = TextReporter().render(_make_report())
    assert out_a == out_b
    assert "ERROR" in out_a
    assert "LR-1" in out_a
    assert "a.py:10:1" in out_a
    assert "layer violation" in out_a
    assert "from api import x" in out_a


def test_json_reporter_schema_v1() -> None:
    out = JsonReporter().render(_make_report())
    data = json.loads(out)
    assert data["schema_version"] == "1.0"
    assert data["tool"] == "architecture_linter"
    assert data["files_scanned"] == 3
    assert data["summary"] == {"error": 1, "warn": 0, "info": 0}
    assert data["violations"][0]["rule_id"] == "LR-1"
    assert data["violations"][0]["severity"] == "error"


# ----------------------------------------------------------------------------
# Exit codes
# ----------------------------------------------------------------------------


def test_exit_code_no_violations() -> None:
    assert ExitCodeManager.from_violations([], Severity.ERROR) == 0


def test_exit_code_with_error() -> None:
    v = Violation(
        rule_id="X-1",
        severity=Severity.ERROR,
        file=Path("a"),
        line=1,
        col=1,
        message="x",
    )
    assert ExitCodeManager.from_violations([v], Severity.ERROR) == 1


def test_exit_code_warn_below_error_threshold() -> None:
    v = Violation(
        rule_id="X-1",
        severity=Severity.WARN,
        file=Path("a"),
        line=1,
        col=1,
        message="x",
    )
    assert ExitCodeManager.from_violations([v], Severity.ERROR) == 0


def test_exit_code_warn_above_warn_threshold() -> None:
    v = Violation(
        rule_id="X-1",
        severity=Severity.WARN,
        file=Path("a"),
        line=1,
        col=1,
        message="x",
    )
    assert ExitCodeManager.from_violations([v], Severity.WARN) == 1


# ----------------------------------------------------------------------------
# End-to-end: empty registry on a tree
# ----------------------------------------------------------------------------


def test_lint_empty_registry_on_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text("x = 1\n")
    cfg = LinterConfig()
    reg = RuleRegistry()
    linter = ArchitectureLinter(config=cfg, registry=reg)
    violations = linter.lint(tmp_path)
    assert violations == []


def test_lint_syntax_error_recorded(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("def x(:\n")
    cfg = LinterConfig()
    reg = RuleRegistry()
    linter = ArchitectureLinter(config=cfg, registry=reg)
    violations = linter.lint(tmp_path)
    assert len(violations) == 1
    assert violations[0].rule_id == "LINTER-PARSE"
    assert violations[0].severity == Severity.ERROR


def test_lint_collect_files_respects_exclude(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "skip.py").write_text("x = 1\n")
    cfg = LinterConfig(exclude=["tests/"])
    linter = ArchitectureLinter(config=cfg, registry=RuleRegistry())
    files = linter._collect_files(tmp_path)
    names = [f.name for f in files]
    assert "ok.py" in names
    assert "skip.py" not in names


def test_lint_collect_files_nonexistent_path(tmp_path: Path) -> None:
    linter = ArchitectureLinter(config=LinterConfig(), registry=RuleRegistry())
    assert linter.lint(tmp_path / "does_not_exist") == []


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


def test_cli_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "architecture_linter" in captured.out


def test_cli_missing_config_returns_internal_error(
    tmp_path: Path,
) -> None:
    rc = main(["--config", str(tmp_path / "missing.toml"), "--path", str(tmp_path)])
    assert rc == ExitCodeManager.EXIT_INTERNAL_ERROR


def test_cli_clean_run_text_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg_file = tmp_path / ".architecture-linter.toml"
    cfg_file.write_text('[general]\noutput_format = "text"\n')
    (tmp_path / "ok.py").write_text("x = 1\n")
    rc = main(["--config", str(cfg_file), "--path", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out


def test_cli_clean_run_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg_file = tmp_path / ".architecture-linter.toml"
    cfg_file.write_text('[general]\noutput_format = "json"\n')
    (tmp_path / "ok.py").write_text("x = 1\n")
    rc = main(["--config", str(cfg_file), "--path", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["schema_version"] == "1.0"
    assert data["files_scanned"] == 1


def test_cli_format_override_takes_precedence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg_file = tmp_path / ".architecture-linter.toml"
    cfg_file.write_text('[general]\noutput_format = "text"\n')
    (tmp_path / "ok.py").write_text("x = 1\n")
    rc = main(
        [
            "--config",
            str(cfg_file),
            "--path",
            str(tmp_path),
            "--format",
            "json",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["schema_version"] == "1.0"


# ----------------------------------------------------------------------------
# LR Rules (M5.5.1.B)
# ----------------------------------------------------------------------------


def _write_py(tmp_path: Path, name: str, source: str) -> Path:
    """Helper: write a .py file at <tmp_path>/<name> and return the path."""
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


def _register_and_lint(
    tmp_path: Path, name: str, source: str, rule: Rule
) -> list[Violation]:
    """Helper: write file, register rule, run linter, return violations."""
    target = _write_py(tmp_path, name, source)
    reg = RuleRegistry()
    reg.register(rule)
    linter = ArchitectureLinter(LinterConfig(), reg)
    return linter.lint(target)


# === LR-1: core/ must not import from api/, cli/, ui/ ===


def test_lr1_positive_core_imports_brain(tmp_path: Path) -> None:
    """LR-1 positive: core importing from brain is OK."""
    rule = LR1Rule()
    v = _register_and_lint(tmp_path, "core/svc.py", "from brain.x import Y\n", rule)
    assert v == []


def test_lr1_negative_core_imports_api(tmp_path: Path) -> None:
    """LR-1 negative 1: core importing from api is a violation."""
    rule = LR1Rule()
    v = _register_and_lint(
        tmp_path, "core/svc.py", "from api.routes import foo\n", rule
    )
    assert len(v) == 1
    assert v[0].rule_id == "LR-1"
    assert v[0].severity == Severity.ERROR
    assert "api" in v[0].message


def test_lr1_negative_core_imports_ui(tmp_path: Path) -> None:
    """LR-1 negative 2: core importing ui is a violation."""
    rule = LR1Rule()
    v = _register_and_lint(tmp_path, "core/svc.py", "import ui.app\n", rule)
    assert len(v) == 1
    assert v[0].rule_id == "LR-1"
    assert "ui" in v[0].message


def test_lr1_regression_spec_example(tmp_path: Path) -> None:
    """LR-1 regression: frozen spec verbatim example."""
    rule = LR1Rule()
    v = _register_and_lint(
        tmp_path, "core/memory/kg_service.py", "from api.routes import foo\n", rule
    )
    assert len(v) == 1
    assert v[0].rule_id == "LR-1"
    assert v[0].line == 1
    assert v[0].file.name == "kg_service.py"


# === LR-2: api/ must not import private core files (leading _)


def test_lr2_positive_api_imports_public_core(tmp_path: Path) -> None:
    """LR-2 positive: api importing public core is OK."""
    rule = LR2Rule()
    v = _register_and_lint(tmp_path, "api/svc.py", "from core.public import Y\n", rule)
    assert v == []


def test_lr2_negative_api_imports_underscore_top(tmp_path: Path) -> None:
    """LR-2 negative 1: api importing core._x is a violation."""
    rule = LR2Rule()
    v = _register_and_lint(
        tmp_path, "api/svc.py", "from core._internal import Y\n", rule
    )
    assert len(v) == 1
    assert v[0].rule_id == "LR-2"


def test_lr2_negative_api_imports_underscore_nested(tmp_path: Path) -> None:
    """LR-2 negative 2: api importing core.x._y is a violation."""
    rule = LR2Rule()
    v = _register_and_lint(
        tmp_path, "api/svc.py", "from core.x._private import Y\n", rule
    )
    assert len(v) == 1
    assert v[0].rule_id == "LR-2"


def test_lr2_regression_spec_example(tmp_path: Path) -> None:
    """LR-2 regression: api importing core._security."""
    rule = LR2Rule()
    v = _register_and_lint(
        tmp_path, "api/routes.py", "from core._security import check\n", rule
    )
    assert len(v) == 1
    assert v[0].rule_id == "LR-2"
    assert v[0].line == 1


# === LR-3: ui/ must not import core/ directly


def test_lr3_positive_ui_imports_api(tmp_path: Path) -> None:
    """LR-3 positive: ui importing api is OK."""
    rule = LR3Rule()
    v = _register_and_lint(tmp_path, "ui/app.py", "from api.routes import foo\n", rule)
    assert v == []


def test_lr3_negative_ui_imports_core_top(tmp_path: Path) -> None:
    """LR-3 negative 1: ui importing core directly is a violation."""
    rule = LR3Rule()
    v = _register_and_lint(tmp_path, "ui/app.py", "from core.x import Y\n", rule)
    assert len(v) == 1
    assert v[0].rule_id == "LR-3"


def test_lr3_negative_ui_imports_core_submodule(tmp_path: Path) -> None:
    """LR-3 negative 2: ui importing core.x.y is a violation."""
    rule = LR3Rule()
    v = _register_and_lint(tmp_path, "ui/app.py", "from core.x.y import Z\n", rule)
    assert len(v) == 1
    assert v[0].rule_id == "LR-3"


def test_lr3_regression_spec_example(tmp_path: Path) -> None:
    """LR-3 regression: frozen spec verbatim example."""
    rule = LR3Rule()
    v = _register_and_lint(
        tmp_path, "ui/dashboard.py", "from core.memory import store\n", rule
    )
    assert len(v) == 1
    assert v[0].rule_id == "LR-3"
    assert v[0].line == 1


# === LR-4: cli/ must not import from api/ or ui/


def test_lr4_positive_cli_imports_core(tmp_path: Path) -> None:
    """LR-4 positive: cli importing core is OK."""
    rule = LR4Rule()
    v = _register_and_lint(
        tmp_path, "cli/main.py", "from core.config import settings\n", rule
    )
    assert v == []


def test_lr4_negative_cli_imports_api(tmp_path: Path) -> None:
    """LR-4 negative 1: cli importing api is a violation."""
    rule = LR4Rule()
    v = _register_and_lint(
        tmp_path, "cli/main.py", "from api.routes import foo\n", rule
    )
    assert len(v) == 1
    assert v[0].rule_id == "LR-4"
    assert "api" in v[0].message


def test_lr4_negative_cli_imports_ui(tmp_path: Path) -> None:
    """LR-4 negative 2: cli importing ui is a violation."""
    rule = LR4Rule()
    v = _register_and_lint(tmp_path, "cli/main.py", "import ui.app\n", rule)
    assert len(v) == 1
    assert v[0].rule_id == "LR-4"
    assert "ui" in v[0].message


def test_lr4_regression_spec_example(tmp_path: Path) -> None:
    """LR-4 regression: cli importing api.main is a violation."""
    rule = LR4Rule()
    v = _register_and_lint(tmp_path, "cli/run.py", "from api.main import app\n", rule)
    assert len(v) == 1
    assert v[0].rule_id == "LR-4"


# === LR-5: Generic layer direction check (UI->API->Brain->Memory+Tools)


def test_lr5_positive_layer_respects_direction(tmp_path: Path) -> None:
    """LR-5 positive: ui -> api import respects direction."""
    rule = LR5Rule()
    v = _register_and_lint(tmp_path, "ui/app.py", "from api.routes import foo\n", rule)
    assert v == []


def test_lr5_negative_brain_imports_api(tmp_path: Path) -> None:
    """LR-5 negative 1: brain importing from api violates direction."""
    rule = LR5Rule()
    v = _register_and_lint(tmp_path, "brain/x.py", "from api.routes import foo\n", rule)
    assert len(v) == 1
    assert v[0].rule_id == "LR-5"
    assert "api" in v[0].message


def test_lr5_negative_core_imports_ui(tmp_path: Path) -> None:
    """LR-5 negative 2: core importing from ui violates direction."""
    rule = LR5Rule()
    v = _register_and_lint(tmp_path, "core/x.py", "import ui.app\n", rule)
    assert len(v) == 1
    assert v[0].rule_id == "LR-5"
    assert "ui" in v[0].message


def test_lr5_regression_spec_example(tmp_path: Path) -> None:
    """LR-5 regression: brain importing from ui violates direction."""
    rule = LR5Rule()
    v = _register_and_lint(tmp_path, "brain/x.py", "from ui.app import render\n", rule)
    assert len(v) == 1
    assert v[0].rule_id == "LR-5"
    assert "ui" in v[0].message


# === Helper unit tests (bonus, for 100% core engine coverage) ===


def test_file_layer_returns_none_for_unrecognized_path(tmp_path: Path) -> None:
    from scripts.architecture_linter import _file_layer

    assert _file_layer(tmp_path / "tests" / "x.py") is None
    assert _file_layer(tmp_path / "random" / "x.py") is None
    assert _file_layer(tmp_path / "core" / "x.py") == "core"
    assert _file_layer(tmp_path / "api" / "x.py") == "api"


def test_module_layer_returns_none_for_external(tmp_path: Path) -> None:
    from scripts.architecture_linter import _module_layer

    assert _module_layer("fastapi") is None
    assert _module_layer("pydantic.BaseModel") is None
    assert _module_layer("core.x") == "core"
    assert _module_layer(None) is None
    assert _module_layer("") is None


def test_iter_imports_skips_relative() -> None:
    import ast

    from scripts.architecture_linter import _iter_imports

    src = "from .x import Y\nfrom ..x import Z\nimport os\nfrom core.x import W\n"
    tree = ast.parse(src)
    modules = [m for _, m in _iter_imports(tree)]
    assert "os" in modules
    assert "core.x" in modules
    assert "Y" not in modules
    assert "Z" not in modules


# ----------------------------------------------------------------------------
# NBR Rules (M5.5.1.C) — No Business Logic in Repository
# Spec: docs/governance/architecture_linter.md §3.2
# ----------------------------------------------------------------------------


# === NBR-1: *Repository MUST NOT have business-logic method names ===


def test_nbr1_positive_repository_has_only_crud(tmp_path: Path) -> None:
    """NBR-1 positive: Repository with only CRUD method names is OK."""
    rule = NBR1Rule()
    src = (
        "class MemoryRepository:\n"
        "    async def create(self, data): pass\n"
        "    async def get(self, id): pass\n"
        "    async def update(self, id, data): pass\n"
        "    async def delete(self, id): pass\n"
        "    async def list(self): pass\n"
    )
    v = _register_and_lint(tmp_path, "core/mem.py", src, rule)
    assert v == []


def test_nbr1_negative_process_method(tmp_path: Path) -> None:
    """NBR-1 negative 1: process_* is forbidden in a Repository."""
    rule = NBR1Rule()
    src = (
        "class MemoryRepository:\n"
        "    async def create(self, data): pass\n"
        "    def process_data(self, items): pass\n"
    )
    v = _register_and_lint(tmp_path, "core/mem.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-1"
    assert "process_data" in v[0].message
    assert "MemoryRepository" in v[0].message


def test_nbr1_negative_rank_and_recommend(tmp_path: Path) -> None:
    """NBR-1 negative 2: rank_* and recommend_* are forbidden (with trailing underscore per spec)."""
    rule = NBR1Rule()
    src = (
        "class ItemRepository:\n"
        "    def rank_items(self, items): pass\n"
        "    def recommend_items(self, user): pass\n"
    )
    v = _register_and_lint(tmp_path, "core/items.py", src, rule)
    assert len(v) == 2
    rule_ids = {x.rule_id for x in v}
    assert rule_ids == {"NBR-1"}
    method_names = {x.message for x in v}
    assert any("rank_items" in m for m in method_names)
    assert any("recommend_items" in m for m in method_names)


def test_nbr1_regression_spec_example(tmp_path: Path) -> None:
    """NBR-1 regression: spec §3.2 example verbatim — def score_memory in MemoryRepository."""
    rule = NBR1Rule()
    src = (
        "class MemoryRepository:\n"
        "    def score_memory(self, m):\n"
        "        return m.value\n"
    )
    v = _register_and_lint(tmp_path, "core/mem.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-1"
    assert v[0].line == 2
    assert v[0].file.name == "mem.py"


def test_nbr1_ignores_non_repository_class(tmp_path: Path) -> None:
    """NBR-1 only targets *Repository classes; other classes are not flagged."""
    rule = NBR1Rule()
    src = (
        "class ScoringService:\n"
        "    def score_memory(self, m): pass\n"
        "    def rank_items(self, items): pass\n"
    )
    v = _register_and_lint(tmp_path, "core/svc.py", src, rule)
    assert v == []


# === NBR-2: *Repository MUST NOT call LLM / embedding / planner ===


def test_nbr2_positive_repository_uses_db_only(tmp_path: Path) -> None:
    """NBR-2 positive: Repository with only DB calls is OK."""
    rule = NBR2Rule()
    src = (
        "class MemoryRepository:\n"
        "    async def create(self, data):\n"
        "        await db.insert(data)\n"
        "    async def get(self, id):\n"
        "        return await db.select(id)\n"
    )
    v = _register_and_lint(tmp_path, "core/mem.py", src, rule)
    assert v == []


def test_nbr2_negative_llm_call(tmp_path: Path) -> None:
    """NBR-2 negative 1: calling llm.generate is forbidden."""
    rule = NBR2Rule()
    src = (
        "class MemoryRepository:\n"
        "    async def create(self, data):\n"
        "        result = await self.llm.generate(data)\n"
        "        return result\n"
    )
    v = _register_and_lint(tmp_path, "core/mem.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-2"
    assert "llm" in v[0].message
    assert "llm.generate" in v[0].message


def test_nbr2_negative_embedding_call(tmp_path: Path) -> None:
    """NBR-2 negative 2: calling embeddings.embed is forbidden."""
    rule = NBR2Rule()
    src = (
        "class ItemRepository:\n"
        "    async def index(self, item):\n"
        "        vec = await self.embeddings.embed_query(item.text)\n"
        "        return vec\n"
    )
    v = _register_and_lint(tmp_path, "core/items.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-2"
    assert "embeddings" in v[0].message


def test_nbr2_regression_spec_example(tmp_path: Path) -> None:
    """NBR-2 regression: spec §3.2 example verbatim — await llm.generate(...) in Repository.create()."""
    rule = NBR2Rule()
    src = (
        "class Repository:\n"
        "    async def create(self, data):\n"
        "        return await llm.generate(data)\n"
    )
    v = _register_and_lint(tmp_path, "core/repo.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-2"
    assert v[0].line == 3


def test_nbr2_ignores_non_repository_class(tmp_path: Path) -> None:
    """NBR-2 only targets *Repository; LLM calls in other classes are not flagged."""
    rule = NBR2Rule()
    src = (
        "class BrainService:\n"
        "    async def chat(self, msg):\n"
        "        return await self.llm.generate(msg)\n"
    )
    v = _register_and_lint(tmp_path, "core/brain.py", src, rule)
    assert v == []


# === NBR-3: *Repository MUST NOT write to event bus directly ===


def test_nbr3_positive_repository_returns_data(tmp_path: Path) -> None:
    """NBR-3 positive: Repository that returns data (no bus writes) is OK."""
    rule = NBR3Rule()
    src = (
        "class MemoryRepository:\n"
        "    async def update(self, id, data):\n"
        "        result = await db.update(id, data)\n"
        "        return result\n"
    )
    v = _register_and_lint(tmp_path, "core/mem.py", src, rule)
    assert v == []


def test_nbr3_negative_bus_publish(tmp_path: Path) -> None:
    """NBR-3 negative 1: bus.publish is forbidden in a Repository."""
    rule = NBR3Rule()
    src = (
        "class MemoryRepository:\n"
        "    async def update(self, id, data):\n"
        "        result = await db.update(id, data)\n"
        "        await self.bus.publish('updated', result)\n"
        "        return result\n"
    )
    v = _register_and_lint(tmp_path, "core/mem.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-3"
    assert "bus" in v[0].message
    assert "self.bus.publish" in v[0].message


def test_nbr3_negative_event_bus_emit(tmp_path: Path) -> None:
    """NBR-3 negative 2: event_bus.emit is forbidden in a Repository."""
    rule = NBR3Rule()
    src = (
        "class OrderRepository:\n"
        "    async def save(self, order):\n"
        "        await db.insert(order)\n"
        "        self.event_bus.emit('order_saved', order)\n"
    )
    v = _register_and_lint(tmp_path, "core/orders.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-3"
    assert "emit" in v[0].message


def test_nbr3_regression_spec_example(tmp_path: Path) -> None:
    """NBR-3 regression: spec §3.2 example verbatim — await bus.publish(...) in Repository.update()."""
    rule = NBR3Rule()
    src = (
        "class Repository:\n"
        "    async def update(self, id, data):\n"
        "        await bus.publish('updated', id)\n"
    )
    v = _register_and_lint(tmp_path, "core/repo.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-3"
    assert v[0].line == 3


def test_nbr3_ignores_unrelated_publish(tmp_path: Path) -> None:
    """NBR-3 must not flag publishes on non-bus objects."""
    rule = NBR3Rule()
    src = (
        "class MemoryRepository:\n"
        "    async def update(self, id, data):\n"
        "        # This is a Kafka producer (not a bus); should not flag\n"
        "        await self.producer.publish('topic', data)\n"
    )
    v = _register_and_lint(tmp_path, "core/mem.py", src, rule)
    assert v == []


# === NBR-4: *Repository MUST NOT perform merge() of graph nodes ===


def test_nbr4_positive_repository_no_merge(tmp_path: Path) -> None:
    """NBR-4 positive: Repository without merge method is OK."""
    rule = NBR4Rule()
    src = (
        "class KGRepository:\n"
        "    async def create_node(self, node): pass\n"
        "    async def get_node(self, id): pass\n"
    )
    v = _register_and_lint(tmp_path, "core/kg.py", src, rule)
    assert v == []


def test_nbr4_negative_merge_method_exact(tmp_path: Path) -> None:
    """NBR-4 negative 1: a method named exactly 'merge' is forbidden."""
    rule = NBR4Rule()
    src = (
        "class KGRepository:\n"
        "    async def create_node(self, node): pass\n"
        "    def merge(self, a, b): pass\n"
    )
    v = _register_and_lint(tmp_path, "core/kg.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-4"
    assert "merge" in v[0].message


def test_nbr4_negative_merge_nodes_method(tmp_path: Path) -> None:
    """NBR-4 negative 2: merge_nodes method is forbidden."""
    rule = NBR4Rule()
    src = "class KGRepository:\n    def merge_nodes(self, n1, n2): pass\n"
    v = _register_and_lint(tmp_path, "core/kg.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-4"
    assert "merge_nodes" in v[0].message


def test_nbr4_regression_spec_example(tmp_path: Path) -> None:
    """NBR-4 regression: spec §3.2 example verbatim — def merge_nodes(...) in KGRepository."""
    rule = NBR4Rule()
    src = "class KGRepository:\n    def merge_nodes(self, n1, n2):\n        return n1\n"
    v = _register_and_lint(tmp_path, "core/kg.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NBR-4"
    assert v[0].line == 2
    assert v[0].file.name == "kg.py"


def test_nbr4_ignores_non_repository_class(tmp_path: Path) -> None:
    """NBR-4 only targets *Repository; merge methods in other classes are not flagged."""
    rule = NBR4Rule()
    src = (
        "class KGService:\n"
        "    def merge_nodes(self, n1, n2): pass\n"
        "    def merge(self, a, b): pass\n"
    )
    v = _register_and_lint(tmp_path, "core/kg_svc.py", src, rule)
    assert v == []


# NSD rules (NSD-1, NSD-2, NSD-3) — M5.5.1.D implementation
# Spec: docs/governance/architecture_linter.md §3.3
# Test matrix: 4 NSD-1 + 4 NSD-2 + 4 NSD-3 = 12 tests
# Architect approval: 2026-07-03


# === NSD-1: *Engine MUST NOT perform DB writes ===


def test_nsd1_positive_engine_pure_compute(tmp_path: Path) -> None:
    """NSD-1 positive: Engine with no DB calls is OK; non-Engine classes ignored."""
    rule = NSD1Rule()
    src = (
        "class ScoringEngine:\n"
        "    def score(self, items):\n"
        "        return [x * 2 for x in items]\n"
        "class FooService:\n"  # non-Engine: rule must NOT iterate into it
        "    async def load(self):\n"
        "        return await db.execute('SELECT 1')\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert v == []


def test_nsd1_negative_db_execute(tmp_path: Path) -> None:
    """NSD-1 negative 1: ``await db.execute(...)`` is forbidden in an Engine."""
    rule = NSD1Rule()
    src = (
        "class InferenceEngine:\n"
        "    async def infer(self, prompt):\n"
        "        await db.execute('INSERT INTO logs ...', prompt)\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NSD-1"
    assert "db.execute" in v[0].message


def test_nsd1_negative_session_save(tmp_path: Path) -> None:
    """NSD-1 negative 2: ``session.save_*`` is forbidden in an Engine.

    Also covers a complex dotted call (``self.repo.session.save``) where
    the DB keyword is mid-path — the rule matches on segment containment.
    """
    rule = NSD1Rule()
    src = (
        "class ReasoningExecutionEngine:\n"
        "    async def execute_goal(self, session, plan):\n"
        "        await session.save_session_record(plan)\n"
        "        await self.repo.session.save_plan(plan)\n"
    )
    v = _register_and_lint(tmp_path, "core/reasoning/eng.py", src, rule)
    assert len(v) == 2
    assert all(x.rule_id == "NSD-1" for x in v)


def test_nsd1_regression_spec_example(tmp_path: Path) -> None:
    """NSD-1 regression: spec §3.3 example verbatim — InferenceEngine + await db.execute()."""
    rule = NSD1Rule()
    src = (
        "class InferenceEngine:\n"
        "    async def infer(self, prompt):\n"
        "        return await db.execute(prompt)\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NSD-1"
    assert v[0].line == 3


# === NSD-2: *Engine MUST NOT mutate its inputs (DTOs are immutable) ===
# B5 refinement: x = x or default  and  x = default if x is None else x
# are local-rebind patterns and MUST NOT be flagged.


def test_nsd2_positive_engine_returns_new(tmp_path: Path) -> None:
    """NSD-2 positive: Engine that constructs new values is OK.

    Also covers the no-arg path (no input parameters -> skip walk).
    """
    rule = NSD2Rule()
    src = (
        "class TraversalEngine:\n"
        "    def traverse(self, node):\n"
        "        new_node = Node(value=node.value * 2)\n"
        "        return new_node\n"
        "class StateLessEngine:\n"  # no params; rule must skip silently
        "    def run(self):\n"
        "        return 42\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert v == []


def test_nsd2_negative_subscript_mutation(tmp_path: Path) -> None:
    """NSD-2 negative 1: mutating a subscript OR attribute on input is forbidden.

    Also covers AugAssign on Attribute/Subscript (B5 inverse: these DO
    mutate the object and MUST be flagged).
    """
    rule = NSD2Rule()
    src = (
        "class TraversalEngine:\n"
        "    def traverse(self, node):\n"
        "        node.properties['visited'] = True\n"
        "        node.score = 0.5\n"
        "        node.count += 1\n"
        "        node['k'] += 1\n"
        "        return node\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert len(v) == 4
    assert all(x.rule_id == "NSD-2" for x in v)


def test_nsd2_regression_spec_example(tmp_path: Path) -> None:
    """NSD-2 regression: spec §3.3 example verbatim — TraversalEngine + node.properties['x'] = 1."""
    rule = NSD2Rule()
    src = (
        "class TraversalEngine:\n"
        "    def visit(self, node):\n"
        "        node.properties['x'] = 1\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NSD-2"
    assert v[0].line == 3
    assert "node" in v[0].message


def test_nsd2_whitelist_default_or_pattern(tmp_path: Path) -> None:
    """NSD-2 B5 whitelist: every local-rebind pattern on a PARAMETER must be ignored.

    The B5 refinement (2026-07-03) requires that the LHS of the assignment
    is itself a method parameter — i.e. the developer is rebinding the
    local parameter name rather than mutating the caller's object. This
    covers all 6 approved patterns:

    1. ``x = x or default``               (BoolOp, Or)
    2. ``x = default if x is None else x``  (IfExp, orelse)
    3. ``x = x if x else default``         (IfExp, body)
    4. ``x = x + 1``                       (BinOp, left)
    5. ``x = 1 + x``                       (BinOp, right)
    6. ``x += 1`` on a plain Name parameter (AugAssign on Name)

    Note: a plain ``x = x`` (RHS = Name, not BinOp/IfExp/BoolOp) is NOT in
    the B5 whitelist and IS flagged — developers should use ``x = x + 0``
    or ``x = x or x`` instead. This preserves the audit value of the rule.
    """
    rule = NSD2Rule()
    src = (
        "class ScoringEngine:\n"
        "    def score(self, ctx, items, base):\n"
        # 1. BoolOp / Or  (LHS = parameter name 'ctx')
        "        ctx = ctx or default_ctx()\n"
        # 2. IfExp / orelse == target  (LHS = parameter name 'base')
        "        base = default_ts if ctx is None else base\n"
        # 3. IfExp / body == target  (LHS = parameter name 'items')
        "        items = items if items else []\n"
        # 4. BinOp / left  (LHS = parameter name 'ctx' rebound)
        "        ctx = ctx + other\n"
        # 5. BinOp / right  (LHS = parameter name 'base' rebound)
        "        base = 1 + base\n"
        # 6. AugAssign on plain Name parameter (no mutation, just rebind)
        "        items += [1]\n"
        "        return ctx\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert v == []


# === NSD-3: *Engine MUST NOT call tools or external services ===


def test_nsd3_positive_engine_pure_function(tmp_path: Path) -> None:
    """NSD-3 positive: Engine with no tool/HTTP calls is OK; non-Engine ignored."""
    rule = NSD3Rule()
    src = (
        "class ScoringEngine:\n"
        "    def score(self, items):\n"
        "        return sum(items) / len(items)\n"
        "class ToolService:\n"  # non-Engine: rule must NOT iterate into it
        "    async def execute(self, name, args):\n"
        "        return await self.tool.run(name, args)\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert v == []


def test_nsd3_negative_tool_execute(tmp_path: Path) -> None:
    """NSD-3 negative 1: ``await tool.execute(...)`` is forbidden in an Engine."""
    rule = NSD3Rule()
    src = (
        "class ScoringEngine:\n"
        "    async def score(self, items):\n"
        "        result = await tool.execute('lookup', items)\n"
        "        return result\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NSD-3"
    assert "tool" in v[0].message


def test_nsd3_negative_http_client(tmp_path: Path) -> None:
    """NSD-3 negative 2: ``http_client.get(...)`` is forbidden in an Engine.

    Also covers multiple tool keyword variants (rest_client, requests,
    httpx) in a single engine to exercise the segment-containment check.
    """
    rule = NSD3Rule()
    src = (
        "class InferenceEngine:\n"
        "    async def fetch_context(self, url):\n"
        "        return await self.http_client.get(url)\n"
        "    async def fetch_alt(self, url):\n"
        "        return await self.rest_client.post(url)\n"
        "    async def fetch_legacy(self, url):\n"
        "        return requests.get(url)\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert len(v) == 3
    assert all(x.rule_id == "NSD-3" for x in v)


def test_nsd3_regression_spec_example(tmp_path: Path) -> None:
    """NSD-3 regression: spec §3.3 example verbatim — ScoringEngine + await tool.execute()."""
    rule = NSD3Rule()
    src = (
        "class ScoringEngine:\n"
        "    async def score(self, items):\n"
        "        return await tool.execute(items)\n"
    )
    v = _register_and_lint(tmp_path, "core/eng.py", src, rule)
    assert len(v) == 1
    assert v[0].rule_id == "NSD-3"
    assert v[0].line == 3
    assert "tool" in v[0].message
