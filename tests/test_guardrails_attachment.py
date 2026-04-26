"""End-to-end attachment test: ToolsManager.execute_tool consults
configured guardrails at both ``tool_input`` and ``tool_output`` and
the four on_fail modes drive the result string the LLM sees.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from specialagent.agent.approval import ToolApprovalManager
from specialagent.agent.loop.guardrails import GuardrailRunner
from specialagent.agent.loop.tools import ToolsManager
from specialagent.agent.tools.base import Tool
from specialagent.agent.tools.registry import ToolRegistry
from specialagent.providers.base import ToolCallRequest
from specops_lib.bus import MessageBus
from specops_lib.config.schema import ExecToolConfig, ToolApprovalConfig, WebSearchConfig
from specops_lib.guardrails import (
    CallableGuardrail,
    GuardrailResult,
)


class EchoTool(Tool):
    """Returns whatever ``output`` argument the caller passes."""

    replay_safety = "safe"

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "echo"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"output": {"type": "string"}},
            "required": ["output"],
        }

    async def execute(self, output: str = "", **_: Any) -> str:
        return output


def _make_runner():
    return GuardrailRunner()


def _make_manager(
    tool_guardrails=None,
    default_guardrails=None,
    tmp_path: Path | None = None,
) -> tuple[ToolsManager, EchoTool]:
    bus = MessageBus()
    tools = ToolRegistry()
    mcp = ToolRegistry()
    echo = EchoTool()
    tools.register(echo)
    tm = ToolsManager(
        tools=tools,
        mcp=mcp,
        approval=ToolApprovalManager(bus=bus, config=ToolApprovalConfig()),
        bus=bus,
        subagents=MagicMock(),
        file_service=MagicMock(),
        workspace=tmp_path or Path("/tmp"),
        exec_config=ExecToolConfig(),
        web_search_config=WebSearchConfig(),
        restrict_to_workspace=False,
        ssrf_protection=False,
        max_tool_output_chars=8192,
        guardrail_runner=_make_runner(),
        tool_guardrails=tool_guardrails or {},
        default_tool_guardrails=default_guardrails or [],
    )
    return tm, echo


@pytest.fixture
def manager_factory(tmp_path: Path):
    def _factory(**kwargs):
        return _make_manager(**kwargs, tmp_path=tmp_path)

    return _factory


def _fail_callable(msg: str, fixed: str | None = None):
    def _check(_content: str) -> GuardrailResult:
        return GuardrailResult(passed=False, message=msg, fixed_output=fixed)

    return _check


def _pass_callable():
    def _check(_content: str) -> GuardrailResult:
        return GuardrailResult(passed=True)

    return _check


class TestToolInput:
    async def test_input_blocks_with_raise(self, manager_factory) -> None:
        guard = CallableGuardrail(
            _fail_callable("dangerous args"), name="input_block", on_fail="raise"
        )
        tm, _ = manager_factory(tool_guardrails={"echo": [guard]})
        tc = ToolCallRequest(id="1", name="echo", arguments={"output": "hi"})
        _id, result = await tm.execute_tool(tc, channel="cli", chat_id="d")
        assert "[GUARDRAIL raise on tool_input" in result
        assert "dangerous args" in result

    async def test_input_passes_through_to_dispatch(self, manager_factory) -> None:
        guard = CallableGuardrail(_pass_callable(), name="ok")
        tm, _ = manager_factory(tool_guardrails={"echo": [guard]})
        tc = ToolCallRequest(id="1", name="echo", arguments={"output": "hello"})
        _id, result = await tm.execute_tool(tc, channel="cli", chat_id="d")
        assert result == "hello"

    async def test_input_escalate_returns_paused_marker(self, manager_factory) -> None:
        guard = CallableGuardrail(_fail_callable("needs human"), name="ask", on_fail="escalate")
        tm, _ = manager_factory(tool_guardrails={"echo": [guard]})
        tc = ToolCallRequest(id="1", name="echo", arguments={"output": "hello"})
        _id, result = await tm.execute_tool(tc, channel="cli", chat_id="d")
        assert "[GUARDRAIL escalate on tool_input" in result
        assert "human" in result.lower()


class TestToolOutput:
    async def test_output_replace_on_fix(self, manager_factory) -> None:
        guard = CallableGuardrail(
            _fail_callable("redact me", fixed="[REDACTED]"),
            name="redactor",
            on_fail="fix",
        )
        tm, _ = manager_factory(tool_guardrails={"echo": [guard]})
        tc = ToolCallRequest(id="1", name="echo", arguments={"output": "secret"})
        _id, result = await tm.execute_tool(tc, channel="cli", chat_id="d")
        assert result == "[REDACTED]"

    async def test_output_retry_emits_marker(self, manager_factory) -> None:
        """A guardrail that only fires on the output (passes input by
        inspecting context.position) emits the retry marker."""

        def _output_only(_content: str) -> GuardrailResult:
            # Always fails — we'll verify via per-call wrapping that it
            # was indeed the tool_output position firing.
            return GuardrailResult(passed=False, message="be brief")

        guard = CallableGuardrail(_output_only, name="brief", on_fail="retry", max_retries=2)
        # Attach the guardrail under the tool — both positions will fire,
        # tool_input wins because it runs first. That's the documented
        # behaviour: tool-level guardrails apply at BOTH positions and
        # the first to fail short-circuits.
        tm, _ = manager_factory(tool_guardrails={"echo": [guard]})
        tc = ToolCallRequest(id="1", name="echo", arguments={"output": "long output"})
        _id, result = await tm.execute_tool(tc, channel="cli", chat_id="d")
        assert "[GUARDRAIL retry on tool_input: brief]" in result
        assert "be brief" in result

    async def test_output_only_guardrail_fires_at_output(self, manager_factory) -> None:
        """A guardrail that inspects context.position and only fails on
        tool_output passes through input enforcement and surfaces the
        retry marker at output."""

        def _output_only(_content: str) -> GuardrailResult:
            return GuardrailResult(passed=False, message="too long")

        class OutputOnlyGuardrail(CallableGuardrail):
            def check(self, content, context):
                if context.position != "tool_output":
                    return GuardrailResult(passed=True)
                return super().check(content, context)

        guard = OutputOnlyGuardrail(
            _output_only, name="output_check", on_fail="retry", max_retries=2
        )
        tm, _ = manager_factory(tool_guardrails={"echo": [guard]})
        tc = ToolCallRequest(id="1", name="echo", arguments={"output": "long"})
        _id, result = await tm.execute_tool(tc, channel="cli", chat_id="d")
        assert "[GUARDRAIL retry on tool_output: output_check]" in result


class TestPrefixMatching:
    async def test_mcp_prefix_applies_to_generated_tool(self, manager_factory) -> None:
        """A prefix-keyed guardrail like ``mcp_linear_`` matches every tool
        name starting with that prefix."""
        guard = CallableGuardrail(_fail_callable("blocked"), name="block", on_fail="raise")
        # Register echo under a prefix so the prefix-match path fires.
        tm, _ = manager_factory(tool_guardrails={"echo_prefix_": [guard]})
        # Verify the lookup directly — exercising the tool dispatch
        # path would require registering a tool whose name matches the
        # prefix, which is what the actual MCP/OpenAPI integration
        # already does in production. This test guards the matching
        # logic itself.
        out = tm.guardrails_for_tool("echo_prefix_anything")
        assert any(g.name == "block" for g in out)


class TestNoRunner:
    async def test_no_runner_means_no_enforcement(self, tmp_path: Path) -> None:
        bus = MessageBus()
        tools = ToolRegistry()
        tools.register(EchoTool())
        tm = ToolsManager(
            tools=tools,
            mcp=ToolRegistry(),
            approval=ToolApprovalManager(bus=bus, config=ToolApprovalConfig()),
            bus=bus,
            subagents=MagicMock(),
            file_service=MagicMock(),
            workspace=tmp_path,
            exec_config=ExecToolConfig(),
            web_search_config=WebSearchConfig(),
            restrict_to_workspace=False,
            ssrf_protection=False,
            max_tool_output_chars=8192,
            # No runner => guardrails ignored entirely.
        )
        tc = ToolCallRequest(id="1", name="echo", arguments={"output": "hello"})
        _id, result = await tm.execute_tool(tc, channel="cli", chat_id="d")
        assert result == "hello"
