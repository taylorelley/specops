"""Integration: simulate a worker killed mid-tool-call and verify a fresh
worker picks up the journal and short-circuits the in-flight tool.

This test does not spawn a subprocess. It exercises the same wiring a
real kill-and-resume goes through:

  worker A (process 1)
    -> writes activity.jsonl events (tool_call only, no tool_result)
    -> "dies" (we just stop interacting with it)

  worker B (process 2, fresh ToolsManager + LocalJournalLookup)
    -> reads activity.jsonl from the same logs dir
    -> dispatches the same tool with the same args
    -> short-circuits to the [INTERRUPTED] sentinel without re-running
       the side-effecting tool

Plus the "previous run completed" path: when a tool_result row exists,
the dispatcher reuses the cached output without re-executing.
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
from specops_lib.activity import ActivityLog
from specops_lib.bus import MessageBus
from specops_lib.config.schema import ExecToolConfig, ToolApprovalConfig, WebSearchConfig
from specops_lib.execution import LocalJournalLookup, derive_idempotency_key, make_event


class SentinelTool(Tool):
    """Mid-call kill emulation: writes a sentinel file, then 'sleeps' (no-op).

    In a real kill scenario the worker dies between sentinel-creation and
    the tool_result emit. The test simulates this by writing the
    tool_call event to the journal (without a matching tool_result) and
    THEN brings up a fresh dispatcher.
    """

    replay_safety = "checkpoint"
    sentinel_path: Path

    def __init__(self, sentinel_path: Path) -> None:
        type(self).sentinel_path = sentinel_path
        self.calls = 0

    @property
    def name(self) -> str:
        return "sentinel_tool"

    @property
    def description(self) -> str:
        return "writes a sentinel file"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"label": {"type": "string"}},
            "required": ["label"],
        }

    async def execute(self, label: str = "x", **kwargs: Any) -> str:
        self.calls += 1
        with open(type(self).sentinel_path, "a", encoding="utf-8") as f:
            f.write(f"{label}\n")
        return f"wrote {label}"


def _build_tools_manager(logs_path: Path, sentinel_path: Path) -> tuple[ToolsManager, SentinelTool]:
    bus = MessageBus()
    approval = ToolApprovalManager(bus=bus, config=ToolApprovalConfig())
    tools = ToolRegistry()
    mcp = ToolRegistry()
    lookup = LocalJournalLookup(logs_path)
    tool = SentinelTool(sentinel_path)
    tools.register(tool)
    tm = ToolsManager(
        tools=tools,
        mcp=mcp,
        approval=approval,
        bus=bus,
        subagents=MagicMock(),
        file_service=MagicMock(),
        workspace=logs_path.parent,
        exec_config=ExecToolConfig(),
        web_search_config=WebSearchConfig(),
        restrict_to_workspace=False,
        ssrf_protection=False,
        max_tool_output_chars=8192,
        journal_lookup=lookup,
    )
    return tm, tool


@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


@pytest.fixture
def sentinel(tmp_path: Path) -> Path:
    return tmp_path / "sentinel.txt"


def _emit_tool_call(log: ActivityLog, *, exec_id: str, key: str, args: dict) -> None:
    log.emit(
        make_event(
            agent_id="agent-1",
            event_type="tool_call",
            execution_id=exec_id,
            step_id="step:0",
            event_kind="tool_call",
            tool_name="sentinel_tool",
            replay_safety="checkpoint",
            idempotency_key=key,
        )
    )


def _emit_tool_result(log: ActivityLog, *, exec_id: str, key: str, payload: str) -> None:
    log.emit(
        make_event(
            agent_id="agent-1",
            event_type="tool_result",
            execution_id=exec_id,
            step_id="step:0",
            event_kind="tool_result",
            tool_name="sentinel_tool",
            replay_safety="checkpoint",
            idempotency_key=key,
            result_status="ok",
            payload_json=payload,
        )
    )


class TestKillBetweenCallAndResult:
    """Worker A dies after tool_call but before tool_result. The fresh
    dispatcher must NOT re-execute the side-effecting tool — it surfaces
    "[INTERRUPTED]" so the LLM can decide whether to ask the user.
    """

    async def test_fresh_worker_does_not_re_execute(
        self, journal_dir: Path, sentinel: Path
    ) -> None:
        # --- Worker A: write a tool_call event WITHOUT a matching tool_result.
        log_a = ActivityLog(logs_path=journal_dir)
        args = {"label": "first-attempt"}
        key = derive_idempotency_key("E1", "step:0", "sentinel_tool", args)
        _emit_tool_call(log_a, exec_id="E1", key=key, args=args)
        # In a real kill, the worker would have already written the
        # sentinel before being killed; emulate that.
        sentinel.write_text("first-attempt\n", encoding="utf-8")
        assert sentinel.read_text().count("first-attempt") == 1

        # --- Worker B: fresh dispatcher pointed at the same journal dir.
        tm, tool = _build_tools_manager(journal_dir, sentinel)
        tc = ToolCallRequest(id="tc1", name="sentinel_tool", arguments=args)
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )

        assert "INTERRUPTED" in result
        # Critical: the side-effecting tool was NOT re-executed.
        assert tool.calls == 0
        # And the sentinel still has the single line from the original run.
        assert sentinel.read_text().strip().splitlines() == ["first-attempt"]


class TestKillAfterResult:
    """Worker A wrote tool_result before dying. The fresh dispatcher must
    reuse the cached result and skip execution entirely.
    """

    async def test_fresh_worker_uses_cached_result(self, journal_dir: Path, sentinel: Path) -> None:
        log_a = ActivityLog(logs_path=journal_dir)
        args = {"label": "cached"}
        key = derive_idempotency_key("E1", "step:0", "sentinel_tool", args)
        _emit_tool_call(log_a, exec_id="E1", key=key, args=args)
        _emit_tool_result(log_a, exec_id="E1", key=key, payload="wrote cached")
        sentinel.write_text("cached\n", encoding="utf-8")

        tm, tool = _build_tools_manager(journal_dir, sentinel)
        tc = ToolCallRequest(id="tc1", name="sentinel_tool", arguments=args)
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )

        assert result == "wrote cached"
        assert tool.calls == 0
        assert sentinel.read_text().strip().splitlines() == ["cached"]


class TestNoPriorJournal:
    """Same args, fresh execution_id: nothing in journal → tool runs."""

    async def test_no_prior_call_executes_normally(self, journal_dir: Path, sentinel: Path) -> None:
        tm, tool = _build_tools_manager(journal_dir, sentinel)
        tc = ToolCallRequest(id="tc1", name="sentinel_tool", arguments={"label": "fresh"})
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E_FRESH", step_id="step:0"
        )
        assert result == "wrote fresh"
        assert tool.calls == 1
        assert sentinel.read_text().strip() == "fresh"
