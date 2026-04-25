"""Execution-events store: durable journal table backing crash recovery."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from specops.core.database import Database
from specops_lib.activity import ActivityEvent


class ExecutionEventsStore:
    """Persist and read journal events.

    ``insert`` is idempotent on ``event_id``. ``find_tool_result`` /
    ``find_tool_call`` back the resume path: the tool dispatcher uses
    them to skip a previously-completed call, or surface an
    "interrupted" sentinel for ``checkpoint``-safety tools where the
    call started but never finished.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(self, event: ActivityEvent) -> bool:
        if not event.execution_id or not event.event_kind or not event.event_id:
            return False
        created_at = datetime.now(timezone.utc).isoformat()
        ts = event.timestamp or created_at
        with self._db.connection() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO execution_events (
                    execution_id, event_id, step_id, event_kind,
                    replay_safety, idempotency_key, tool_name,
                    result_status, duration_ms, payload_json,
                    timestamp, agent_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.execution_id,
                    event.event_id,
                    event.step_id or "",
                    event.event_kind,
                    event.replay_safety,
                    event.idempotency_key,
                    event.tool_name,
                    event.result_status,
                    event.duration_ms,
                    event.payload_json,
                    ts,
                    event.agent_id or "",
                    created_at,
                ),
            )
            return cur.rowcount > 0

    def list_for_execution(
        self,
        execution_id: str,
        *,
        after_id: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        with self._db.connection() as conn:
            if after_id is not None:
                rows = conn.execute(
                    """SELECT * FROM execution_events
                       WHERE execution_id = ? AND id > ?
                       ORDER BY id ASC LIMIT ?""",
                    (execution_id, after_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM execution_events
                       WHERE execution_id = ?
                       ORDER BY id ASC LIMIT ?""",
                    (execution_id, limit),
                ).fetchall()
            return [_row_to_dict(r) for r in rows]

    def find_tool_result(
        self,
        execution_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        with self._db.connection() as conn:
            row = conn.execute(
                """SELECT * FROM execution_events
                   WHERE execution_id = ?
                     AND idempotency_key = ?
                     AND event_kind = 'tool_result'
                   ORDER BY id DESC LIMIT 1""",
                (execution_id, idempotency_key),
            ).fetchone()
            return _row_to_dict(row) if row else None

    def find_tool_call(
        self,
        execution_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        if not idempotency_key:
            return None
        with self._db.connection() as conn:
            row = conn.execute(
                """SELECT * FROM execution_events
                   WHERE execution_id = ?
                     AND idempotency_key = ?
                     AND event_kind = 'tool_call'
                   ORDER BY id DESC LIMIT 1""",
                (execution_id, idempotency_key),
            ).fetchone()
            return _row_to_dict(row) if row else None

    def find_hitl_resolved(
        self,
        execution_id: str,
        guardrail_name: str,
        tool_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the most recent ``hitl_resolved`` event matching the
        guardrail (and optional tool name) or ``None``.

        ``tool_name`` disambiguates the shared ``legacy_approval``
        guardrail name across multiple pending approvals. Pass ``None``
        to match any tool.
        """
        if not guardrail_name:
            return None
        with self._db.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM execution_events
                   WHERE execution_id = ? AND event_kind = 'hitl_resolved'
                   ORDER BY id DESC""",
                (execution_id,),
            ).fetchall()
        wildcard: dict[str, Any] | None = None
        for row in rows:
            payload = _parse_payload(row["payload_json"])
            if payload.get("guardrail") != guardrail_name:
                continue
            row_tool = payload.get("tool_name") or ""
            merged = {**_row_to_dict(row), **payload}
            if tool_name and row_tool == tool_name:
                return merged
            if not row_tool and wildcard is None:
                wildcard = merged
        return wildcard


def _row_to_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "execution_id": row["execution_id"],
        "event_id": row["event_id"],
        "step_id": row["step_id"] or "",
        "event_kind": row["event_kind"],
        "replay_safety": row["replay_safety"],
        "idempotency_key": row["idempotency_key"],
        "tool_name": row["tool_name"],
        "result_status": row["result_status"],
        "duration_ms": row["duration_ms"],
        "payload_json": row["payload_json"],
        "timestamp": row["timestamp"],
        "agent_id": row["agent_id"] or "",
    }


def _parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


__all__ = ["ExecutionEventsStore"]
