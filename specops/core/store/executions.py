"""Executions store: lifecycle of one in-flight turn (per inbound message)."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from specops.core.database import Database
from specops.core.store.base import BaseRepository


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


class ExecutionsStore(BaseRepository[Execution]):
    """CRUD for the ``executions`` table.

    Inherits ``get_by_id`` / ``list_all`` / ``delete`` / ``_update``
    from :class:`BaseRepository`; the specialised lifecycle methods
    (``create``, ``mark_paused``, ``set_status``, ``set_last_step``,
    ``set_pending_resume``, ``list_for_agent``, ``list_paused``)
    layer on top.
    """

    table_name = "executions"
    model_class = Execution

    def __init__(self, db: Database) -> None:
        super().__init__(db)

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
        # Thin wrapper over BaseRepository.get_by_id for callers that
        # spell the lookup as ``store.get(...)``.
        return self.get_by_id(execution_id)

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
        return self._update(
            execution_id,
            status=status,
            error_message=error_message,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def mark_paused(self, execution_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        return self._update(execution_id, status="paused", paused_at=now, updated_at=now)

    def set_last_step(self, execution_id: str, step_id: str) -> bool:
        return self._update(
            execution_id,
            last_step_id=step_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def set_pending_resume(self, execution_id: str, pending: bool) -> bool:
        return self._update(
            execution_id,
            pending_resume=1 if pending else 0,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )


__all__ = ["Execution", "ExecutionsStore"]
