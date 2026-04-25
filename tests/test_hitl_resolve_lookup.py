"""Tests for find_hitl_resolved on both LocalJournalLookup and
ExecutionEventsStore. The runner relies on these lookups for its
resume-side short-circuit; this test pins their semantics directly.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from specops.core.database import Database
from specops.core.store.execution_events import ExecutionEventsStore
from specops_lib.activity import ActivityEvent, ActivityLog
from specops_lib.execution import LocalJournalLookup


def _resolved_event(
    *,
    execution_id: str,
    guardrail: str,
    tool_name: str = "",
    decision: str = "approve",
) -> ActivityEvent:
    return ActivityEvent(
        agent_id="agent-1",
        event_type="hitl_resolved",
        event_id=uuid.uuid4().hex,
        execution_id=execution_id,
        step_id="step:0",
        event_kind="hitl_resolved",
        tool_name=tool_name or None,
        result_status="ok" if decision == "approve" else "error",
        payload_json=json.dumps(
            {
                "guardrail": guardrail,
                "tool_name": tool_name,
                "decision": decision,
                "note": "qa",
            }
        ),
    )


# ---------------------------------------------------------------------------
# LocalJournalLookup
# ---------------------------------------------------------------------------


class TestLocalLookup:
    @pytest.fixture
    def journal(self, tmp_path: Path) -> Path:
        d = tmp_path / "logs"
        d.mkdir()
        return d

    async def test_returns_none_when_no_resolves(self, journal: Path) -> None:
        lookup = LocalJournalLookup(journal)
        assert await lookup.find_hitl_resolved("E1", "g1") is None

    async def test_finds_with_tool_name(self, journal: Path) -> None:
        log = ActivityLog(logs_path=journal)
        log.emit(
            _resolved_event(
                execution_id="E1",
                guardrail="legacy_approval",
                tool_name="send_payment",
                decision="approve",
            )
        )
        lookup = LocalJournalLookup(journal)
        hit = await lookup.find_hitl_resolved("E1", "legacy_approval", "send_payment")
        assert hit is not None
        assert hit["decision"] == "approve"

    async def test_other_tool_not_unblocked(self, journal: Path) -> None:
        log = ActivityLog(logs_path=journal)
        log.emit(
            _resolved_event(
                execution_id="E1",
                guardrail="legacy_approval",
                tool_name="send_payment",
            )
        )
        lookup = LocalJournalLookup(journal)
        miss = await lookup.find_hitl_resolved("E1", "legacy_approval", "delete_user")
        assert miss is None

    async def test_wildcard_tool_name_matches(self, journal: Path) -> None:
        """An event written without a tool_name applies to any tool — used
        for guardrails whose pause is intrinsically tool-agnostic."""
        log = ActivityLog(logs_path=journal)
        log.emit(_resolved_event(execution_id="E1", guardrail="agent_output_guard"))
        lookup = LocalJournalLookup(journal)
        hit = await lookup.find_hitl_resolved("E1", "agent_output_guard", "anything")
        assert hit is not None

    async def test_specific_wins_over_wildcard(self, journal: Path) -> None:
        log = ActivityLog(logs_path=journal)
        log.emit(_resolved_event(execution_id="E1", guardrail="g1", decision="approve"))
        log.emit(
            _resolved_event(execution_id="E1", guardrail="g1", tool_name="t1", decision="reject")
        )
        lookup = LocalJournalLookup(journal)
        hit = await lookup.find_hitl_resolved("E1", "g1", "t1")
        assert hit is not None
        assert hit["decision"] == "reject"


# ---------------------------------------------------------------------------
# ExecutionEventsStore (control-plane DB)
# ---------------------------------------------------------------------------


class TestStoreLookup:
    @pytest.fixture
    def db(self, tmp_path: Path) -> Database:
        return Database(tmp_path / "admin.db")

    def test_returns_none_when_no_resolves(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        assert store.find_hitl_resolved("E1", "g1") is None

    def test_filters_by_tool_name(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        store.insert(
            _resolved_event(
                execution_id="E1",
                guardrail="legacy_approval",
                tool_name="send_payment",
            )
        )
        assert store.find_hitl_resolved("E1", "legacy_approval", "send_payment") is not None
        assert store.find_hitl_resolved("E1", "legacy_approval", "delete_user") is None

    def test_wildcard_match(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        store.insert(_resolved_event(execution_id="E1", guardrail="g_any"))
        assert store.find_hitl_resolved("E1", "g_any", "anything") is not None
