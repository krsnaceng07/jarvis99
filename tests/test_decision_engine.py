"""
PHASE: 24
STATUS: TEST
SPECIFICATION:
    docs/84_PHASE_24_AUTONOMOUS_AGENT_SPECIFICATION.md

AUTHORITATIVE: NO
"""

from core.reasoning.decision_engine import DecisionEngine
from core.reasoning.task import ExecutorType


class TestDecisionEngine:
    def setup_method(self) -> None:
        self.engine = DecisionEngine()

    def test_python_keyword_selects_python(self) -> None:
        result = self.engine.select_tool("Write a python script to analyse CSV files.")
        assert result.executor_type == ExecutorType.PYTHON
        assert result.confidence >= 0.85

    def test_shell_keyword_selects_shell(self) -> None:
        result = self.engine.select_tool(
            "Run a shell command to install the package using pip."
        )
        assert result.executor_type == ExecutorType.SHELL
        assert result.confidence >= 0.80

    def test_browser_keyword_selects_browser(self) -> None:
        result = self.engine.select_tool(
            "Navigate to the URL and take a screenshot of the page."
        )
        assert result.executor_type == ExecutorType.BROWSER

    def test_api_keyword_selects_api(self) -> None:
        result = self.engine.select_tool(
            "Send a POST request to the REST endpoint with the payload."
        )
        assert result.executor_type == ExecutorType.API

    def test_file_keyword_selects_file(self) -> None:
        result = self.engine.select_tool(
            "Read the file and write the output to a new file."
        )
        assert result.executor_type == ExecutorType.FILE

    def test_memory_keyword_selects_memory(self) -> None:
        result = self.engine.select_tool(
            "Recall what the user said about their preferences earlier from memory."
        )
        assert result.executor_type == ExecutorType.MEMORY

    def test_human_keyword_selects_human(self) -> None:
        result = self.engine.select_tool("Confirm with the human before proceeding.")
        assert result.executor_type == ExecutorType.HUMAN
        assert result.confidence >= 0.90

    def test_llm_keyword_selects_llm(self) -> None:
        result = self.engine.select_tool(
            "Summarize the following document and explain the key points."
        )
        assert result.executor_type == ExecutorType.LLM

    def test_forced_executor_via_context(self) -> None:
        result = self.engine.select_tool(
            "Do something ambiguous",
            context={"forced_executor": "python"},
        )
        assert result.executor_type == ExecutorType.PYTHON
        assert result.confidence >= 0.90

    def test_unknown_description_defaults_to_llm(self) -> None:
        result = self.engine.select_tool("xyzzy frobnicate the quux.")
        assert result.executor_type == ExecutorType.LLM
        assert result.confidence < 0.60

    def test_decision_engine_never_executes(self) -> None:
        """DecisionEngine must have no executor/dispatcher attributes."""
        engine = DecisionEngine()
        assert not hasattr(engine, "dispatcher")
        assert not hasattr(engine, "executor")
        assert not hasattr(engine, "tool")
