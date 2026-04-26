"""Tests for replay-safety enforcement in ToolsManager.execute_tool.

Covers the three replay-safety values:
  - "safe":       always re-execute on resume (idempotency_key may match
                  but the dispatcher does not consult the journal).
  - "checkpoint": short-circuit when a prior tool_result exists; surface
                  "[INTERRUPTED]" when only tool_call exists.
  - "skip":       refuse to continue when only tool_call exists.
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from specialagent.agent.approval import ToolApprovalManager
from specialagent.agent.loop.tools import ToolsManager
from specialagent.agent.tools.base import Tool
from specialagent.agent.tools.registry import ToolRegistry
from specialagent.providers.base import ToolCallRequest
from specops_lib.bus import MessageBus
from specops_lib.config.schema import ExecToolConfig, ToolApprovalConfig, WebSearchConfig
from specops_lib.execution import JournalLookup, derive_idempotency_key


class FakeJournal(JournalLookup):
    """In-memory journal for tests."""

    def __init__(self) -> None:
        self.results: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: dict[tuple[str, str], dict[str, Any]] = {}

    async def find_tool_result(self, execution_id, idempotency_key):
        return self.results.get((execution_id, idempotency_key))

    async def find_tool_call(self, execution_id, idempotency_key):
        return self.calls.get((execution_id, idempotency_key))


class CountingTool(Tool):
    """Records how many times execute() actually ran."""

    def __init__(self, name: str = "fake", replay_safety: str = "checkpoint") -> None:
        self._name = name
        self.calls = 0
        type(self).replay_safety = replay_safety  # per-instance override via class

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "fake tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs: Any) -> str:
        self.calls += 1
        return f"executed {self._name}"


@pytest.fixture
def tools_manager(tmp_path: Path):
    bus = MessageBus()
    approval = ToolApprovalManager(bus=bus, config=ToolApprovalConfig())
    tools = ToolRegistry()
    mcp = ToolRegistry()
    journal = FakeJournal()
    tm = ToolsManager(
        tools=tools,
        mcp=mcp,
        approval=approval,
        bus=bus,
        subagents=MagicMock(),
        file_service=MagicMock(),
        workspace=tmp_path,
        exec_config=ExecToolConfig(),
        web_search_config=WebSearchConfig(),
        restrict_to_workspace=False,
        ssrf_protection=False,
        max_tool_output_chars=8192,
        journal_lookup=journal,
    )
    return tm, tools, journal


class TestReplaySafetyCheckpoint:
    async def test_first_run_executes(self, tools_manager) -> None:
        tm, tools, _journal = tools_manager
        tool = CountingTool("fake_cp", replay_safety="checkpoint")
        tools.register(tool)
        tc = ToolCallRequest(id="tc1", name="fake_cp", arguments={})
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )
        assert result == "executed fake_cp"
        assert tool.calls == 1

    async def test_short_circuits_on_prior_result(self, tools_manager) -> None:
        tm, tools, journal = tools_manager
        tool = CountingTool("fake_cp", replay_safety="checkpoint")
        tools.register(tool)
        args = {"x": 1}
        key = derive_idempotency_key("E1", "step:0", "fake_cp", args)
        journal.results[("E1", key)] = {
            "payload_json": "cached output",
            "result_status": "ok",
        }
        tc = ToolCallRequest(id="tc1", name="fake_cp", arguments=args)
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )
        assert result == "cached output"
        assert tool.calls == 0

    async def test_interrupted_returns_synthetic_message(self, tools_manager) -> None:
        """tool_call exists, no tool_result → don't re-run a side-effecting tool."""
        tm, tools, journal = tools_manager
        tool = CountingTool("fake_cp", replay_safety="checkpoint")
        tools.register(tool)
        args = {"x": 1}
        key = derive_idempotency_key("E1", "step:0", "fake_cp", args)
        journal.calls[("E1", key)] = {"event_kind": "tool_call"}
        tc = ToolCallRequest(id="tc1", name="fake_cp", arguments=args)
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )
        assert "INTERRUPTED" in result
        assert tool.calls == 0


class TestReplaySafetySkip:
    async def test_skip_aborts_on_interrupted(self, tools_manager) -> None:
        tm, tools, journal = tools_manager
        tool = CountingTool("fake_skip", replay_safety="skip")
        tools.register(tool)
        args = {"x": 1}
        key = derive_idempotency_key("E1", "step:0", "fake_skip", args)
        journal.calls[("E1", key)] = {"event_kind": "tool_call"}
        tc = ToolCallRequest(id="tc1", name="fake_skip", arguments=args)
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )
        assert "RESUME UNSAFE" in result
        assert tool.calls == 0


class TestReplaySafetySafe:
    async def test_safe_always_executes(self, tools_manager) -> None:
        """Even if a prior result exists, replay_safety=safe re-runs the tool."""
        tm, tools, journal = tools_manager
        tool = CountingTool("fake_safe", replay_safety="safe")
        tools.register(tool)
        args = {"x": 1}
        key = derive_idempotency_key("E1", "step:0", "fake_safe", args)
        journal.results[("E1", key)] = {
            "payload_json": "stale cache",
            "result_status": "ok",
        }
        tc = ToolCallRequest(id="tc1", name="fake_safe", arguments=args)
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )
        assert result == "executed fake_safe"
        assert tool.calls == 1


class TestNoExecutionId:
    async def test_no_execution_id_skips_journal(self, tools_manager) -> None:
        """Backwards-compat: if execution_id is empty the dispatcher must not consult the journal."""
        tm, tools, journal = tools_manager
        tool = CountingTool("fake_cp", replay_safety="checkpoint")
        tools.register(tool)
        # Even with a journal entry, it shouldn't be looked up without execution_id.
        journal.results[("anything", "anything")] = {"payload_json": "won't see this"}
        tc = ToolCallRequest(id="tc1", name="fake_cp", arguments={})
        _id, result = await tm.execute_tool(tc, channel="cli", chat_id="d")
        assert result == "executed fake_cp"
        assert tool.calls == 1
