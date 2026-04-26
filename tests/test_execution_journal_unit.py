"""Pure unit tests for the execution journal helpers."""

import json
import time
from pathlib import Path

from specops_lib.activity import ActivityEvent, ActivityLog
from specops_lib.execution import (
    EVENT_KINDS,
    REPLAY_SAFETIES,
    LocalJournalLookup,
    NullJournal,
    canonical_args,
    derive_idempotency_key,
    journal_fields,
    make_event,
)


class TestDeriveIdempotencyKey:
    def test_stable_for_same_inputs(self) -> None:
        a = derive_idempotency_key("e1", "step:0", "write_file", {"path": "x", "content": "y"})
        b = derive_idempotency_key("e1", "step:0", "write_file", {"path": "x", "content": "y"})
        assert a == b
        assert len(a) == 64

    def test_changes_with_args(self) -> None:
        a = derive_idempotency_key("e1", "step:0", "write_file", {"path": "x"})
        b = derive_idempotency_key("e1", "step:0", "write_file", {"path": "y"})
        assert a != b

    def test_changes_with_step(self) -> None:
        a = derive_idempotency_key("e1", "step:0", "write_file", {"x": 1})
        b = derive_idempotency_key("e1", "step:1", "write_file", {"x": 1})
        assert a != b

    def test_arg_order_irrelevant(self) -> None:
        """Canonical JSON sorts keys, so dict ordering must not affect the key."""
        a = derive_idempotency_key("e1", "step:0", "t", {"a": 1, "b": 2})
        b = derive_idempotency_key("e1", "step:0", "t", {"b": 2, "a": 1})
        assert a == b


class TestEnums:
    def test_event_kinds_are_closed_set(self) -> None:
        assert "execution_started" in EVENT_KINDS
        assert "tool_call" in EVENT_KINDS
        assert "tool_result" in EVENT_KINDS
        assert "step_started" in EVENT_KINDS
        assert "step_completed" in EVENT_KINDS
        assert "hitl_waiting" in EVENT_KINDS
        assert "hitl_resolved" in EVENT_KINDS
        # Closed set: 11 kinds
        assert len(EVENT_KINDS) == 11

    def test_replay_safeties(self) -> None:
        assert set(REPLAY_SAFETIES) == {"safe", "checkpoint", "skip"}


class TestMakeEvent:
    def test_attaches_journal_fields(self) -> None:
        ev = make_event(
            agent_id="a",
            event_type="tool_call",
            execution_id="e1",
            step_id="step:0",
            event_kind="tool_call",
            tool_name="write_file",
            replay_safety="checkpoint",
            idempotency_key="k1",
            payload_json='{"path":"x"}',
        )
        assert isinstance(ev, ActivityEvent)
        assert ev.execution_id == "e1"
        assert ev.event_kind == "tool_call"
        assert ev.replay_safety == "checkpoint"
        assert ev.idempotency_key == "k1"
        assert ev.payload_json == '{"path":"x"}'
        assert ev.event_id  # auto-allocated UUID

    def test_journal_fields_omits_none(self) -> None:
        ev = ActivityEvent(agent_id="a", event_type="message_received")
        assert journal_fields(ev) == {}

    def test_journal_fields_includes_set(self) -> None:
        ev = make_event(
            agent_id="a",
            event_type="tool_call",
            execution_id="e1",
            step_id="step:0",
            event_kind="tool_call",
        )
        fields = journal_fields(ev)
        assert fields["execution_id"] == "e1"
        assert fields["step_id"] == "step:0"
        assert fields["event_kind"] == "tool_call"


class TestCanonicalArgs:
    def test_sorts_keys(self) -> None:
        assert canonical_args({"b": 1, "a": 2}) == '{"a":2,"b":1}'

    def test_handles_unicode(self) -> None:
        # ensure_ascii=False keeps non-ASCII in plain form
        assert canonical_args({"name": "Zürich"}) == '{"name":"Zürich"}'


class TestLocalJournalLookup:
    def _write(self, log: ActivityLog, **kwargs):
        ev = make_event(
            agent_id="agent-1",
            event_type=kwargs.get("event_kind", "tool_call"),
            **kwargs,
        )
        log.emit(ev)
        return ev

    async def test_find_returns_none_when_no_logs(self, tmp_path: Path) -> None:
        lookup = LocalJournalLookup(tmp_path)
        assert await lookup.find_tool_result("e1", "k1") is None
        assert await lookup.find_tool_call("e1", "k1") is None

    async def test_find_tool_result_after_emit(self, tmp_path: Path) -> None:
        log = ActivityLog(logs_path=tmp_path)
        self._write(
            log,
            execution_id="e1",
            step_id="step:0",
            event_kind="tool_call",
            tool_name="write_file",
            replay_safety="checkpoint",
            idempotency_key="K",
        )
        self._write(
            log,
            execution_id="e1",
            step_id="step:0",
            event_kind="tool_result",
            tool_name="write_file",
            replay_safety="checkpoint",
            idempotency_key="K",
            result_status="ok",
            payload_json="OK 5 bytes",
        )

        lookup = LocalJournalLookup(tmp_path)
        result = await lookup.find_tool_result("e1", "K")
        assert result is not None
        assert result["payload_json"] == "OK 5 bytes"

    async def test_find_tool_call_without_result(self, tmp_path: Path) -> None:
        """Mid-flight kill scenario: tool_call written but no tool_result."""
        log = ActivityLog(logs_path=tmp_path)
        self._write(
            log,
            execution_id="e1",
            step_id="step:0",
            event_kind="tool_call",
            tool_name="exec",
            replay_safety="checkpoint",
            idempotency_key="K",
        )
        lookup = LocalJournalLookup(tmp_path)
        assert await lookup.find_tool_call("e1", "K") is not None
        assert await lookup.find_tool_result("e1", "K") is None

    async def test_skips_non_journal_events(self, tmp_path: Path) -> None:
        """Events without execution_id/idempotency_key are not indexed."""
        log = ActivityLog(logs_path=tmp_path)
        log.emit(
            ActivityEvent(
                agent_id="agent-1",
                event_type="message_received",
                channel="cli",
                content="hello",
            )
        )
        lookup = LocalJournalLookup(tmp_path)
        # Loading shouldn't error; index just stays empty.
        assert await lookup.find_tool_result("e1", "k") is None

    async def test_reads_rotated_files(self, tmp_path: Path) -> None:
        """LocalJournalLookup includes rotated activity.{1,2}.jsonl."""
        rotated = tmp_path / "activity.1.jsonl"
        rotated.write_text(
            json.dumps(
                {
                    "agent_id": "a",
                    "event_type": "tool_result",
                    "execution_id": "e1",
                    "step_id": "step:0",
                    "event_kind": "tool_result",
                    "idempotency_key": "RotK",
                    "payload_json": "rotated",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        lookup = LocalJournalLookup(tmp_path)
        result = await lookup.find_tool_result("e1", "RotK")
        assert result is not None
        assert result["payload_json"] == "rotated"

    async def test_refresh_when_file_grows(self, tmp_path: Path) -> None:
        """A second emit after the first lookup must be visible."""
        log = ActivityLog(logs_path=tmp_path)
        lookup = LocalJournalLookup(tmp_path)
        assert await lookup.find_tool_result("e1", "K") is None
        time.sleep(0.01)  # ensure stat() mtime advances
        self._write(
            log,
            execution_id="e1",
            step_id="step:0",
            event_kind="tool_result",
            idempotency_key="K",
            payload_json="late",
        )
        # File mtime changed; refresh path picks it up.
        result = await lookup.find_tool_result("e1", "K")
        assert result is not None


class TestNullJournal:
    async def test_always_returns_none(self) -> None:
        j = NullJournal()
        assert await j.find_tool_result("e1", "k") is None
        assert await j.find_tool_call("e1", "k") is None
        # emit is a no-op
        j.emit(ActivityEvent(agent_id="a", event_type="x"))
