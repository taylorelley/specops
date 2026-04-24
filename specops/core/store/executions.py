"""Executions store: lifecycle of one in-flight turn (per inbound message)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from specops.core.database import Database


class Execution(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    agent_id: str
    plan_id: str = ""
    session_key: str = ""
    channel: str = ""
    chat_id: str = ""
    status: str = "running"
    last_step_id: str = ""
    error_message: str = ""
    pending_resume: int = 0
    created_at: str = ""
    updated_at: str = ""
    paused_at: str = ""


class ExecutionsStore:
    """CRUD for the ``executions`` table."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def create(
        self,
        *,
        execution_id: str,
        agent_id: str,
        session_key: str = "",
        channel: str = "",
        chat_id: str = "",
        plan_id: str = "",
    ) -> Execution:
        now = datetime.now(timezone.utc).isoformat()
        with self._db.connection() as conn:
            conn.execute(
                """INSERT INTO executions (
                    id, agent_id, plan_id, session_key, channel, chat_id,
                    status, last_step_id, error_message, pending_resume,
                    created_at, updated_at, paused_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'running', '', '', 0, ?, ?, '')""",
                (execution_id, agent_id, plan_id, session_key, channel, chat_id, now, now),
            )
        return Execution(
            id=execution_id,
            agent_id=agent_id,
            plan_id=plan_id,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            status="running",
            created_at=now,
            updated_at=now,
        )

    def get(self, execution_id: str) -> Execution | None:
        with self._db.connection() as conn:
            row = conn.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
            return Execution.model_validate(dict(row)) if row else None

    def list_for_agent(
        self,
        agent_id: str,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Execution]:
        with self._db.connection() as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM executions
                       WHERE agent_id = ? AND status = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (agent_id, status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM executions
                       WHERE agent_id = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (agent_id, limit),
                ).fetchall()
            return [Execution.model_validate(dict(r)) for r in rows]

    def list_paused(self, *, limit: int = 200) -> list[Execution]:
        with self._db.connection() as conn:
            rows = conn.execute(
                """SELECT * FROM executions WHERE status = 'paused'
                   ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [Execution.model_validate(dict(r)) for r in rows]

    def set_status(
        self,
        execution_id: str,
        status: str,
        *,
        error_message: str = "",
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._db.connection() as conn:
            cur = conn.execute(
                """UPDATE executions
                   SET status = ?, error_message = ?, updated_at = ?
                   WHERE id = ?""",
                (status, error_message, now, execution_id),
            )
            return cur.rowcount > 0

    def mark_paused(self, execution_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._db.connection() as conn:
            cur = conn.execute(
                """UPDATE executions
                   SET status = 'paused', paused_at = ?, updated_at = ?
                   WHERE id = ?""",
                (now, now, execution_id),
            )
            return cur.rowcount > 0

    def set_last_step(self, execution_id: str, step_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._db.connection() as conn:
            cur = conn.execute(
                """UPDATE executions SET last_step_id = ?, updated_at = ?
                   WHERE id = ?""",
                (step_id, now, execution_id),
            )
            return cur.rowcount > 0

    def set_pending_resume(self, execution_id: str, pending: bool) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._db.connection() as conn:
            cur = conn.execute(
                """UPDATE executions SET pending_resume = ?, updated_at = ?
                   WHERE id = ?""",
                (1 if pending else 0, now, execution_id),
            )
            return cur.rowcount > 0

    def delete(self, execution_id: str) -> bool:
        with self._db.connection() as conn:
            cur = conn.execute("DELETE FROM executions WHERE id = ?", (execution_id,))
            return cur.rowcount > 0


__all__ = ["Execution", "ExecutionsStore"]
