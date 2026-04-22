"""Share CRUD for claws (agents) and plans backed by SQLite."""

from datetime import datetime, timezone

from clawforce.core.database import Database
from clawforce.core.domain.share import (
    AgentShare,
    PlanShare,
    SharePermission,
)

_VALID_PERMISSIONS = frozenset({"viewer", "editor", "manager"})


def _require_permission(permission: str) -> str:
    if permission not in _VALID_PERMISSIONS:
        raise ValueError(
            f"Invalid permission '{permission}'. Expected one of: {sorted(_VALID_PERMISSIONS)}"
        )
    return permission


class ShareStore:
    """CRUD for agent_shares and plan_shares tables."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ---- Agent shares ----

    def list_agent_shares(self, agent_id: str) -> list[AgentShare]:
        with self._db.connection() as conn:
            rows = conn.execute(
                """SELECT agent_id, user_id, permission, granted_by, created_at
                   FROM agent_shares WHERE agent_id = ? ORDER BY created_at""",
                (agent_id,),
            ).fetchall()
            return [AgentShare.model_validate(dict(r)) for r in rows]

    def get_agent_permission(self, agent_id: str, user_id: str) -> SharePermission | None:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT permission FROM agent_shares WHERE agent_id = ? AND user_id = ?",
                (agent_id, user_id),
            ).fetchone()
            return row["permission"] if row else None

    def set_agent_share(
        self,
        agent_id: str,
        user_id: str,
        permission: str,
        granted_by: str = "",
    ) -> AgentShare:
        perm = _require_permission(permission)
        now = _now()
        with self._db.connection() as conn:
            # ON CONFLICT preserves the original created_at, so the returned row
            # is the source of truth for both new and updated shares.
            conn.execute(
                """INSERT INTO agent_shares (agent_id, user_id, permission, granted_by, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(agent_id, user_id) DO UPDATE SET
                       permission = excluded.permission,
                       granted_by = excluded.granted_by""",
                (agent_id, user_id, perm, granted_by, now),
            )
            row = conn.execute(
                """SELECT agent_id, user_id, permission, granted_by, created_at
                   FROM agent_shares WHERE agent_id = ? AND user_id = ?""",
                (agent_id, user_id),
            ).fetchone()
        return AgentShare.model_validate(dict(row))

    def remove_agent_share(self, agent_id: str, user_id: str) -> bool:
        with self._db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM agent_shares WHERE agent_id = ? AND user_id = ?",
                (agent_id, user_id),
            )
            return cursor.rowcount > 0

    def list_agent_ids_shared_with(self, user_id: str) -> list[str]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT agent_id FROM agent_shares WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return [r["agent_id"] for r in rows]

    # ---- Plan shares ----

    def list_plan_shares(self, plan_id: str) -> list[PlanShare]:
        with self._db.connection() as conn:
            rows = conn.execute(
                """SELECT plan_id, user_id, permission, granted_by, created_at
                   FROM plan_shares WHERE plan_id = ? ORDER BY created_at""",
                (plan_id,),
            ).fetchall()
            return [PlanShare.model_validate(dict(r)) for r in rows]

    def get_plan_permission(self, plan_id: str, user_id: str) -> SharePermission | None:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT permission FROM plan_shares WHERE plan_id = ? AND user_id = ?",
                (plan_id, user_id),
            ).fetchone()
            return row["permission"] if row else None

    def set_plan_share(
        self,
        plan_id: str,
        user_id: str,
        permission: str,
        granted_by: str = "",
    ) -> PlanShare:
        perm = _require_permission(permission)
        now = _now()
        with self._db.connection() as conn:
            conn.execute(
                """INSERT INTO plan_shares (plan_id, user_id, permission, granted_by, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(plan_id, user_id) DO UPDATE SET
                       permission = excluded.permission,
                       granted_by = excluded.granted_by""",
                (plan_id, user_id, perm, granted_by, now),
            )
            row = conn.execute(
                """SELECT plan_id, user_id, permission, granted_by, created_at
                   FROM plan_shares WHERE plan_id = ? AND user_id = ?""",
                (plan_id, user_id),
            ).fetchone()
        return PlanShare.model_validate(dict(row))

    def remove_plan_share(self, plan_id: str, user_id: str) -> bool:
        with self._db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM plan_shares WHERE plan_id = ? AND user_id = ?",
                (plan_id, user_id),
            )
            return cursor.rowcount > 0

    def list_plan_ids_shared_with(self, user_id: str) -> list[str]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT plan_id FROM plan_shares WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return [r["plan_id"] for r in rows]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
