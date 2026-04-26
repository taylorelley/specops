"""Tests for ExecutionsStore and ExecutionEventsStore (control-plane DB)."""

from pathlib import Path

import pytest

from specops.core.database import Database
from specops.core.store.execution_events import ExecutionEventsStore
from specops.core.store.executions import Execution, ExecutionsStore
from specops_lib.activity import ActivityEvent
from specops_lib.execution import make_event


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(tmp_path / "admin.db")


class TestExecutionsStore:
    def test_create_and_get(self, db: Database) -> None:
        store = ExecutionsStore(db)
        ex = store.create(
            execution_id="E1",
            agent_id="agent-1",
            session_key="cli:direct",
            channel="cli",
            chat_id="direct",
        )
        assert ex.status == "running"
        fetched = store.get("E1")
        assert isinstance(fetched, Execution)
        assert fetched.id == "E1"
        assert fetched.session_key == "cli:direct"

    def test_list_for_agent_filters_by_status(self, db: Database) -> None:
        store = ExecutionsStore(db)
        store.create(execution_id="E1", agent_id="a")
        store.create(execution_id="E2", agent_id="a")
        store.set_status("E2", "paused")
        running = store.list_for_agent("a", status="running")
        paused = store.list_for_agent("a", status="paused")
        assert {e.id for e in running} == {"E1"}
        assert {e.id for e in paused} == {"E2"}

    def test_list_paused(self, db: Database) -> None:
        store = ExecutionsStore(db)
        store.create(execution_id="E1", agent_id="a")
        store.create(execution_id="E2", agent_id="b")
        store.mark_paused("E1")
        paused = store.list_paused()
        assert len(paused) == 1
        assert paused[0].id == "E1"
        assert paused[0].paused_at  # timestamp populated

    def test_set_last_step(self, db: Database) -> None:
        store = ExecutionsStore(db)
        store.create(execution_id="E1", agent_id="a")
        assert store.set_last_step("E1", "step:3")
        assert store.get("E1").last_step_id == "step:3"

    def test_set_pending_resume(self, db: Database) -> None:
        store = ExecutionsStore(db)
        store.create(execution_id="E1", agent_id="a")
        assert store.set_pending_resume("E1", True)
        assert store.get("E1").pending_resume == 1
        assert store.set_pending_resume("E1", False)
        assert store.get("E1").pending_resume == 0


class TestExecutionEventsStore:
    def _ev(self, **overrides) -> ActivityEvent:
        defaults = dict(
            agent_id="agent-1",
            event_type="tool_call",
            execution_id="E1",
            step_id="step:0",
            event_kind="tool_call",
            tool_name="write_file",
            replay_safety="checkpoint",
            idempotency_key="K1",
        )
        defaults.update(overrides)
        return make_event(**defaults)

    def test_insert_dedups_on_event_id(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        ev = self._ev()
        assert store.insert(ev) is True
        assert store.insert(ev) is False

    def test_skips_event_without_execution_id(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        ev = ActivityEvent(agent_id="a", event_type="message", event_id="x")
        assert store.insert(ev) is False

    def test_list_for_execution_ordered(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        store.insert(self._ev(idempotency_key="K1"))
        store.insert(
            self._ev(
                event_kind="tool_result",
                idempotency_key="K1",
                result_status="ok",
                payload_json="OK",
            )
        )
        events = store.list_for_execution("E1")
        assert len(events) == 2
        assert events[0]["event_kind"] == "tool_call"
        assert events[1]["event_kind"] == "tool_result"

    def test_after_id_pagination(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        store.insert(self._ev(idempotency_key="K1"))
        store.insert(self._ev(event_kind="tool_result", idempotency_key="K1"))
        first = store.list_for_execution("E1")
        cursor = first[0]["id"]
        rest = store.list_for_execution("E1", after_id=cursor)
        assert len(rest) == 1
        assert rest[0]["event_kind"] == "tool_result"

    def test_find_tool_result_by_idempotency_key(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        store.insert(self._ev(idempotency_key="K1"))
        store.insert(
            self._ev(
                event_kind="tool_result",
                idempotency_key="K1",
                result_status="ok",
                payload_json="DONE",
            )
        )
        hit = store.find_tool_result("E1", "K1")
        assert hit is not None
        assert hit["payload_json"] == "DONE"
        assert store.find_tool_result("E1", "no-such") is None

    def test_find_tool_call_only(self, db: Database) -> None:
        store = ExecutionEventsStore(db)
        store.insert(self._ev(idempotency_key="K1"))
        assert store.find_tool_call("E1", "K1") is not None
        assert store.find_tool_result("E1", "K1") is None

    def test_idempotency_key_can_repeat_across_kinds(self, db: Database) -> None:
        """Tool_call and tool_result share an idempotency_key by design.

        Dedup is via event_id (UNIQUE); idempotency_key is a query key,
        not a uniqueness constraint.
        """
        store = ExecutionEventsStore(db)
        ev1 = self._ev(idempotency_key="K1", event_kind="tool_call")
        ev2 = self._ev(idempotency_key="K1", event_kind="tool_result")
        assert ev1.event_id != ev2.event_id
        assert store.insert(ev1) is True
        assert store.insert(ev2) is True
        events = store.list_for_execution("E1")
        kinds = {e["event_kind"] for e in events}
        assert kinds == {"tool_call", "tool_result"}
