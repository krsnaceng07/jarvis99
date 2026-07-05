"""
PHASE: 21
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 21 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from core.reasoning.goal import Goal, GoalAnalyzer


def test_goal_analyzer_heuristics() -> None:
    analyzer = GoalAnalyzer()

    # Test basic parsing
    goal = Goal(goal_text="Check codebase files and run command: pytest tests/ #test")
    analysis = analyzer.analyze(goal)

    assert analysis.complexity == "medium"
    assert "test" in analysis.tags
    assert analysis.constraints.budget == 10.0
    assert analysis.constraints.deadline_hours == 24.0

    # Test custom budget, deadline, allowed, and forbidden tools parsing
    complex_goal = Goal(
        goal_text="deploy service budget=$50 deadline=12 parallel=2 forbidden=bash,rm allowed=pytest,git precondition:env_setup postcondition:health_check"
    )
    complex_analysis = analyzer.analyze(complex_goal)

    assert complex_analysis.complexity == "high"
    assert complex_analysis.constraints.budget == 50.0
    assert complex_analysis.constraints.deadline_hours == 12.0
    assert complex_analysis.constraints.parallel_limit == 2
    assert "bash" in complex_analysis.constraints.forbidden_tools
    assert "rm" in complex_analysis.constraints.forbidden_tools
    assert "pytest" in complex_analysis.constraints.allowed_tools
    assert "git" in complex_analysis.constraints.allowed_tools
    assert complex_analysis.preconditions == ["env_setup"]
    assert complex_analysis.postconditions == ["health_check"]

    # Test dollar-only regex fallback in GoalAnalyzer
    dollar_goal = Goal(goal_text="solve problems under $150 budget limit")
    dollar_analysis = analyzer.analyze(dollar_goal)
    assert dollar_analysis.constraints.budget == 150.0
