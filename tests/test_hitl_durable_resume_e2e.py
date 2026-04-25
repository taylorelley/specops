"""Phase 4 — durable HITL resume.

Simulates the full pause-die-approve-resume cycle in-process:

    Worker A (ToolsManager #1) — receives the same execution_id, hits
    an ``escalate`` guardrail, emits ``hitl_waiting`` and pauses.

    [worker A goes away]

    Admin writes a ``hitl_resolved`` event into the journal (this is
    what the ``/api/executions/{id}/resolve`` endpoint does on the
    control plane).

    Worker B (ToolsManager #2) — fresh dispatcher pointed at the same
    journal. The runner sees ``hitl_resolved(approve)`` and skips the
    escalate guardrail; the tool runs once and the call completes.

The reject path returns a ``raise`` outcome regardless of the
configured ``on_fail`` so the LLM (and downstream reporting) sees a
clean rejection.
"""

from __future__ import annotations

import json
import uuid
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
from specops_lib.activity import ActivityEvent, ActivityLog
from specops_lib.bus import MessageBus
from specops_lib.config.schema import ExecToolConfig, ToolApprovalConfig, WebSearchConfig
from specops_lib.execution import LocalJournalLookup
from specops_lib.guardrails import CallableGuardrail, GuardrailResult


class SentinelTool(Tool):
    """Side-effecting tool: writes one line to the sentinel file per call."""

    replay_safety = "checkpoint"
    sentinel_path: Path

    def __init__(self, sentinel_path: Path) -> None:
        type(self).sentinel_path = sentinel_path
        self.calls = 0

    @property
    def name(self) -> str:
        return "send_payment"

    @property
    def description(self) -> str:
        return "send payment"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"to": {"type": "string"}, "amount": {"type": "number"}},
            "required": ["to", "amount"],
        }

    async def execute(self, to: str = "", amount: float = 0, **_: Any) -> str:
        self.calls += 1
        with open(type(self).sentinel_path, "a", encoding="utf-8") as f:
            f.write(f"{to}:{amount}\n")
        return f"sent {amount} to {to}"


def _make_escalate_guardrail() -> CallableGuardrail:
    """Always-fail guardrail mimicking the synthesised legacy_approval."""

    def _check(_content: str) -> GuardrailResult:
        return GuardrailResult(
            passed=False, message="Tool requires human approval (legacy ToolApprovalConfig)."
        )

    return CallableGuardrail(_check, name="legacy_approval", on_fail="escalate", max_retries=1)


def _build_worker(
    *,
    logs_path: Path,
    sentinel_path: Path,
) -> tuple[ToolsManager, SentinelTool, GuardrailRunner]:
    bus = MessageBus()
    tools = ToolRegistry()
    mcp = ToolRegistry()
    tool = SentinelTool(sentinel_path)
    tools.register(tool)
    journal = LocalJournalLookup(logs_path)

    captured_events: list[dict] = []

    async def on_event(ev_type: str, channel: str, content: str, **kwargs: Any) -> None:
        ev = ActivityEvent(
            agent_id="agent-1",
            event_type=ev_type,
            channel=channel,
            content=content,
            **kwargs,
        )
        # Emit through ActivityLog so the on-disk journal sees it.
        log = ActivityLog(logs_path=logs_path)
        log.emit(ev)
        captured_events.append({"event_type": ev_type, **kwargs})

    runner = GuardrailRunner(on_event=on_event, journal_lookup=journal)
    tm = ToolsManager(
        tools=tools,
        mcp=mcp,
        approval=ToolApprovalManager(bus=bus, config=ToolApprovalConfig()),
        bus=bus,
        subagents=MagicMock(),
        file_service=MagicMock(),
        workspace=logs_path.parent,
        exec_config=ExecToolConfig(),
        web_search_config=WebSearchConfig(),
        restrict_to_workspace=False,
        ssrf_protection=False,
        max_tool_output_chars=8192,
        on_event=on_event,
        journal_lookup=journal,
        guardrail_runner=runner,
        tool_guardrails={"send_payment": [_make_escalate_guardrail()]},
    )
    return tm, tool, runner


def _write_resolve_event(
    *, logs_path: Path, execution_id: str, decision: str, tool_name: str = "send_payment"
) -> None:
    """Write a hitl_resolved event into the on-disk journal — this is
    what ``POST /api/executions/{id}/resolve`` does in production."""
    payload = json.dumps(
        {
            "guardrail": "legacy_approval",
            "tool_name": tool_name,
            "decision": decision,
            "note": "approved by qa" if decision == "approve" else "rejected for testing",
            "approver_id": "u1",
        }
    )
    log = ActivityLog(logs_path=logs_path)
    log.emit(
        ActivityEvent(
            agent_id="agent-1",
            event_type="hitl_resolved",
            event_id=uuid.uuid4().hex,
            execution_id=execution_id,
            step_id="step:0",
            event_kind="hitl_resolved",
            tool_name=tool_name,
            result_status="ok" if decision == "approve" else "error",
            payload_json=payload,
        )
    )


@pytest.fixture
def journal_dir(tmp_path: Path) -> Path:
    d = tmp_path / "logs"
    d.mkdir()
    return d


@pytest.fixture
def sentinel(tmp_path: Path) -> Path:
    return tmp_path / "sent.txt"


class TestDurableResumeApprove:
    async def test_full_pause_die_approve_resume_cycle(
        self, journal_dir: Path, sentinel: Path
    ) -> None:
        # ─── Worker A ────────────────────────────────────────────
        tm_a, tool_a, _ = _build_worker(logs_path=journal_dir, sentinel_path=sentinel)
        tc = ToolCallRequest(
            id="tc1", name="send_payment", arguments={"to": "alice", "amount": 100}
        )
        _id, result_a = await tm_a.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )
        assert "[GUARDRAIL escalate" in result_a
        assert tool_a.calls == 0  # tool did not run
        # Journal saw hitl_waiting (via the on_event capture).

        # ─── /resolve writes hitl_resolved(approve) ──────────────
        _write_resolve_event(logs_path=journal_dir, execution_id="E1", decision="approve")

        # ─── Worker B (fresh dispatcher) ─────────────────────────
        tm_b, tool_b, _ = _build_worker(logs_path=journal_dir, sentinel_path=sentinel)
        tc2 = ToolCallRequest(
            id="tc2", name="send_payment", arguments={"to": "alice", "amount": 100}
        )
        _id, result_b = await tm_b.execute_tool(
            tc2, channel="cli", chat_id="d", execution_id="E1", step_id="step:0"
        )

        # Tool ran exactly once on the fresh worker; output looks normal.
        assert tool_b.calls == 1
        assert "sent 100" in result_b
        # Sentinel has exactly one line.
        assert sentinel.read_text().strip().splitlines() == ["alice:100"]


class TestDurableResumeReject:
    async def test_reject_propagates_as_raise(self, journal_dir: Path, sentinel: Path) -> None:
        tm_a, _, _ = _build_worker(logs_path=journal_dir, sentinel_path=sentinel)
        tc = ToolCallRequest(id="tc1", name="send_payment", arguments={"to": "bob", "amount": 50})
        await tm_a.execute_tool(tc, channel="cli", chat_id="d", execution_id="E2", step_id="step:0")

        _write_resolve_event(logs_path=journal_dir, execution_id="E2", decision="reject")

        tm_b, tool_b, _ = _build_worker(logs_path=journal_dir, sentinel_path=sentinel)
        tc2 = ToolCallRequest(id="tc2", name="send_payment", arguments={"to": "bob", "amount": 50})
        _id, result_b = await tm_b.execute_tool(
            tc2, channel="cli", chat_id="d", execution_id="E2", step_id="step:0"
        )

        # Reject propagates as a raise marker; tool never runs.
        assert "[GUARDRAIL raise" in result_b
        assert "rejected" in result_b.lower()
        assert tool_b.calls == 0


class TestToolNameDisambiguation:
    """legacy_approval is shared across tools — resolving for tool A
    must not silently unblock tool B."""

    async def test_resolve_for_tool_a_does_not_unblock_tool_b(
        self, journal_dir: Path, sentinel: Path
    ) -> None:
        # Approve a *different* tool first.
        _write_resolve_event(
            logs_path=journal_dir,
            execution_id="E3",
            decision="approve",
            tool_name="some_other_tool",
        )
        tm, tool, _ = _build_worker(logs_path=journal_dir, sentinel_path=sentinel)
        tc = ToolCallRequest(id="tc1", name="send_payment", arguments={"to": "x", "amount": 1})
        _id, result = await tm.execute_tool(
            tc, channel="cli", chat_id="d", execution_id="E3", step_id="step:0"
        )
        # Still pauses — the resolve was for a different tool name.
        assert "[GUARDRAIL escalate" in result
        assert tool.calls == 0
