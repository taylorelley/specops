"""Plan CRUD and task/agent operations backed by SQLite."""

import sqlite3
from datetime import datetime, timezone

from clawforce.core.database import Database
from clawforce.core.domain.plan import (
    PlanColumn,
    PlanDef,
    PlanTask,
    TaskComment,
    _default_plan_columns,
    columns_from_template,
)
from clawforce.core.store.base import BaseRepository


class PlanStore(BaseRepository[PlanDef]):
    """CRUD for plans persisted in SQLite. Columns and tasks in separate tables."""

    table_name = "plans"
    model_class = PlanDef

    def __init__(self, db: Database) -> None:
        super().__init__(db)

    def _get_columns(self, plan_id: str) -> list[PlanColumn]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT id, title, position FROM plan_columns WHERE plan_id = ? ORDER BY position",
                (plan_id,),
            ).fetchall()
            return [PlanColumn.model_validate(dict(r)) for r in rows]

    def _get_tasks(self, plan_id: str) -> list[PlanTask]:
        with self._db.connection() as conn:
            rows = conn.execute(
                """SELECT id, title, description, column_id, agent_id, position, created_at, updated_at
                   FROM plan_tasks WHERE plan_id = ? ORDER BY position, created_at""",
                (plan_id,),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["column_id"] = d.get("column_id") or ""
                d["agent_id"] = d.get("agent_id") or ""
                out.append(PlanTask.model_validate(d))
            return out

    def _get_assigned_agents(self, plan_id: str) -> list[str]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT agent_id FROM plan_agents WHERE plan_id = ?", (plan_id,)
            ).fetchall()
            return [r["agent_id"] for r in rows]

    def _resolve_column_id(self, plan: PlanDef, column_id: str) -> str:
        """Resolve a column_id to the actual column ID in the plan.

        Accepts exact match, suffix match (e.g., 'col-todo'), or short name (e.g., 'todo').
        Returns the first column's ID as fallback.
        """
        matched = next((c for c in plan.columns if c.id == column_id), None)
        if not matched:
            matched = next(
                (
                    c
                    for c in plan.columns
                    if c.id.endswith(f"-{column_id}") or c.id.endswith(column_id)
                ),
                None,
            )
        if matched:
            return matched.id
        return plan.columns[0].id if plan.columns else f"{plan.id}-col-todo"

    def _touch_plan(self, plan_id: str) -> None:
        with self._db.connection() as conn:
            conn.execute(
                "UPDATE plans SET updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), plan_id),
            )

    def list_plans(self, visible_to_user_id: str | None = None) -> list[PlanDef]:
        """List plans. If ``visible_to_user_id`` is given, restrict to plans the
        user owns or has a share on. Pass ``None`` to list every plan (admin).
        """
        if visible_to_user_id is None:
            plans = self.list_all()
        else:
            with self._db.connection() as conn:
                rows = conn.execute(
                    """SELECT p.* FROM plans p
                       WHERE p.owner_user_id = ?
                          OR EXISTS (
                              SELECT 1 FROM plan_shares s
                              WHERE s.plan_id = p.id AND s.user_id = ?
                          )""",
                    (visible_to_user_id, visible_to_user_id),
                ).fetchall()
                plans = [self._row_to_model(r) for r in rows]
        for p in plans:
            p.columns = self._get_columns(p.id)
            p.tasks = self._get_tasks(p.id)
            p.agent_ids = self._get_assigned_agents(p.id)
        return plans

    def get_plan(self, plan_id: str) -> PlanDef | None:
        plan = self.get_by_id(plan_id)
        if not plan:
            return None
        plan.columns = self._get_columns(plan_id)
        plan.tasks = self._get_tasks(plan_id)
        plan.agent_ids = self._get_assigned_agents(plan_id)
        return plan

    def create_plan(self, name: str, description: str = "", owner_user_id: str = "") -> PlanDef:
        plan = PlanDef(name=name, description=description, owner_user_id=owner_user_id)
        d = plan.model_dump(by_alias=False)
        d.pop("columns", None)
        d.pop("tasks", None)
        d.pop("agent_ids", None)
        cols = list(d.keys())
        placeholders = ", ".join("?" for _ in cols)
        with self._db.connection() as conn:
            conn.execute(
                f"INSERT INTO plans ({', '.join(cols)}) VALUES ({placeholders})",
                [d[k] for k in cols],
            )
            for col in _default_plan_columns(plan.id):
                conn.execute(
                    "INSERT INTO plan_columns (id, plan_id, title, position) VALUES (?, ?, ?, ?)",
                    (col.id, plan.id, col.title, col.position),
                )
        plan.columns = _default_plan_columns(plan.id)
        plan.tasks = []
        plan.agent_ids = []
        return plan

    def create_plan_from_template(
        self,
        name: str,
        description: str,
        template: dict,
        owner_user_id: str = "",
    ) -> PlanDef:
        """Create a plan using the columns and tasks from a plan template.

        If the template declares ``columns``, those replace the four defaults.
        Each task's ``column`` is resolved against the plan's actual columns
        via ``_resolve_column_id`` (supports short names and title suffix match).

        Agent preassignment:
        - Plan-level ``agent_ids`` are assigned to the new plan.
        - Task-level ``agent_id`` values are applied to each task and also
          assigned to the plan (a task agent must be on the plan to work it).
        - Agent ids that do not exist are silently skipped — a stale template
          should not block plan creation.

        All inserts happen inside a single transaction so a mid-flight failure
        rolls back and leaves no half-built plan behind.
        """
        plan = PlanDef(name=name, description=description, owner_user_id=owner_user_id)
        d = plan.model_dump(by_alias=False)
        d.pop("columns", None)
        d.pop("tasks", None)
        d.pop("agent_ids", None)
        cols = list(d.keys())
        placeholders = ", ".join("?" for _ in cols)

        template_columns = template.get("columns") or []
        resolved_columns = columns_from_template(plan.id, template_columns)
        template_tasks = template.get("tasks") or []

        # Union of agents to consider preassigning: plan-level + any referenced by tasks.
        plan_agent_candidates: list[str] = [
            a for a in (template.get("agent_ids") or []) if isinstance(a, str) and a
        ]
        for raw in template_tasks:
            task_agent = str(raw.get("agent_id", "") or "")
            if task_agent and task_agent not in plan_agent_candidates:
                plan_agent_candidates.append(task_agent)

        with self._db.connection() as conn:
            conn.execute(
                f"INSERT INTO plans ({', '.join(cols)}) VALUES ({placeholders})",
                [d[k] for k in cols],
            )
            for col in resolved_columns:
                conn.execute(
                    "INSERT INTO plan_columns (id, plan_id, title, position) VALUES (?, ?, ?, ?)",
                    (col.id, plan.id, col.title, col.position),
                )

            plan.columns = resolved_columns
            plan.tasks = []
            plan.agent_ids = []

            assigned_agents = self._assign_agents_in_conn(conn, plan.id, plan_agent_candidates)
            plan.agent_ids = list(assigned_agents)

            position_by_column: dict[str, int] = {}
            for raw in template_tasks:
                title = str(raw.get("title", "")).strip()
                if not title:
                    continue
                description_text = str(raw.get("description", ""))
                column_ref = str(raw.get("column", "") or "")
                column_id = (
                    self._resolve_column_id(plan, column_ref)
                    if column_ref
                    else (plan.columns[0].id if plan.columns else f"{plan.id}-col-todo")
                )
                position = position_by_column.get(column_id, 0)
                position_by_column[column_id] = position + 1
                raw_task_agent = str(raw.get("agent_id", "") or "")
                task_agent_id = raw_task_agent if raw_task_agent in assigned_agents else ""
                task = PlanTask(
                    title=title,
                    description=description_text,
                    column_id=column_id,
                    agent_id=task_agent_id,
                    position=position,
                )
                conn.execute(
                    """INSERT INTO plan_tasks (id, plan_id, column_id, agent_id, title, description, position, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.id,
                        plan.id,
                        task.column_id or None,
                        task.agent_id or None,
                        task.title,
                        task.description,
                        task.position,
                        task.created_at,
                        task.updated_at,
                    ),
                )
                plan.tasks.append(task)

            if template_tasks:
                conn.execute(
                    "UPDATE plans SET updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), plan.id),
                )
        return plan

    def _assign_agents_in_conn(self, conn, plan_id: str, agent_ids: list[str]) -> set[str]:
        """Assign only the agent ids that currently exist, within an existing connection.

        Silently drops ids that have no matching ``agents`` row so stale template
        references don't block plan creation.
        """
        if not agent_ids:
            return set()
        placeholders = ",".join("?" for _ in agent_ids)
        rows = conn.execute(
            f"SELECT id FROM agents WHERE id IN ({placeholders})",
            agent_ids,
        ).fetchall()
        existing = {r["id"] for r in rows}
        for aid in agent_ids:
            if aid in existing:
                try:
                    conn.execute(
                        "INSERT INTO plan_agents (plan_id, agent_id) VALUES (?, ?)",
                        (plan_id, aid),
                    )
                except sqlite3.IntegrityError:
                    pass
        return existing

    def _assign_existing_agents(self, plan_id: str, agent_ids: list[str]) -> set[str]:
        """Same as ``_assign_agents_in_conn`` but opens its own connection."""
        if not agent_ids:
            return set()
        with self._db.connection() as conn:
            placeholders = ",".join("?" for _ in agent_ids)
            rows = conn.execute(
                f"SELECT id FROM agents WHERE id IN ({placeholders})",
                agent_ids,
            ).fetchall()
            existing = {r["id"] for r in rows}
            for aid in agent_ids:
                if aid in existing:
                    try:
                        conn.execute(
                            "INSERT INTO plan_agents (plan_id, agent_id) VALUES (?, ?)",
                            (plan_id, aid),
                        )
                    except sqlite3.IntegrityError:
                        pass
        return existing

    def update_plan(self, plan_id: str, **kwargs: object) -> PlanDef | None:
        plan = self.get_plan(plan_id)
        if not plan:
            return None
        allowed = {"name", "description", "status"}
        for k, v in kwargs.items():
            if k in allowed and hasattr(plan, k):
                setattr(plan, k, v)
        plan.updated_at = datetime.now(timezone.utc).isoformat()
        self._update(
            plan_id,
            name=plan.name,
            description=plan.description,
            status=plan.status,
            updated_at=plan.updated_at,
        )
        return plan

    def delete_plan(self, plan_id: str) -> bool:
        return self.delete(plan_id)

    def add_task(
        self,
        plan_id: str,
        column_id: str,
        title: str = "",
        description: str = "",
        agent_id: str = "",
    ) -> PlanTask | None:
        plan = self.get_plan(plan_id)
        if not plan:
            return None
        column_id = (
            self._resolve_column_id(plan, column_id)
            if column_id
            else (plan.columns[0].id if plan.columns else f"{plan_id}-col-todo")
        )
        max_pos = max(
            (t.position for t in plan.tasks if t.column_id == column_id),
            default=-1,
        )
        task = PlanTask(
            title=title,
            description=description,
            column_id=column_id,
            agent_id=agent_id,
            position=max_pos + 1,
        )
        with self._db.connection() as conn:
            conn.execute(
                """INSERT INTO plan_tasks (id, plan_id, column_id, agent_id, title, description, position, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.id,
                    plan_id,
                    task.column_id or None,
                    task.agent_id or None,
                    task.title,
                    task.description,
                    task.position,
                    task.created_at,
                    task.updated_at,
                ),
            )
            conn.execute(
                "UPDATE plans SET updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), plan_id),
            )
        return task

    def update_task(
        self,
        plan_id: str,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        column_id: str | None = None,
        agent_id: str | None = None,
        position: int | None = None,
    ) -> PlanTask | None:
        plan = self.get_plan(plan_id)
        if not plan:
            return None
        for t in plan.tasks:
            if t.id == task_id:
                if title is not None:
                    t.title = title
                if description is not None:
                    t.description = description
                if column_id is not None:
                    t.column_id = self._resolve_column_id(plan, column_id)
                if agent_id is not None:
                    t.agent_id = agent_id
                if position is not None:
                    t.position = position
                t.updated_at = datetime.now(timezone.utc).isoformat()
                with self._db.connection() as conn:
                    conn.execute(
                        """UPDATE plan_tasks SET title = ?, description = ?, column_id = ?, agent_id = ?, position = ?, updated_at = ?
                           WHERE id = ?""",
                        (
                            t.title,
                            t.description,
                            t.column_id or None,
                            t.agent_id or None,
                            t.position,
                            t.updated_at,
                            task_id,
                        ),
                    )
                    conn.execute(
                        "UPDATE plans SET updated_at = ? WHERE id = ?",
                        (datetime.now(timezone.utc).isoformat(), plan_id),
                    )
                return t
        return None

    def move_task(
        self, plan_id: str, task_id: str, column_id: str, position: int
    ) -> PlanTask | None:
        return self.update_task(plan_id, task_id, column_id=column_id, position=position)

    def delete_task(self, plan_id: str, task_id: str) -> bool:
        with self._db.connection() as conn:
            cursor = conn.execute("DELETE FROM plan_tasks WHERE id = ?", (task_id,))
            if cursor.rowcount > 0:
                conn.execute(
                    "UPDATE plans SET updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), plan_id),
                )
            return cursor.rowcount > 0

    def assign_agent(self, plan_id: str, agent_id: str) -> bool:
        plan = self.get_by_id(plan_id)
        if not plan:
            return False
        with self._db.connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO plan_agents (plan_id, agent_id) VALUES (?, ?)",
                    (plan_id, agent_id),
                )
            except sqlite3.IntegrityError:
                return True  # already assigned
            conn.execute(
                "UPDATE plans SET updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), plan_id),
            )
        return True

    def remove_agent(self, plan_id: str, agent_id: str) -> bool:
        plan = self.get_by_id(plan_id)
        if not plan:
            return False
        with self._db.connection() as conn:
            conn.execute(
                "DELETE FROM plan_agents WHERE plan_id = ? AND agent_id = ?",
                (plan_id, agent_id),
            )
            conn.execute(
                "UPDATE plan_tasks SET agent_id = NULL WHERE plan_id = ? AND agent_id = ?",
                (plan_id, agent_id),
            )
            conn.execute(
                "UPDATE plans SET updated_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), plan_id),
            )
        return True

    def add_comment(
        self,
        plan_id: str,
        task_id: str,
        *,
        author_type: str,
        author_id: str,
        author_name: str,
        content: str,
    ) -> TaskComment | None:
        plan = self.get_plan(plan_id)
        if not plan or not any(t.id == task_id for t in plan.tasks):
            return None
        comment = TaskComment(
            task_id=task_id,
            author_type=author_type,
            author_id=author_id,
            author_name=author_name,
            content=content,
        )
        with self._db.connection() as conn:
            conn.execute(
                """INSERT INTO task_comments (id, plan_id, task_id, author_type, author_id, author_name, content, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    comment.id,
                    plan_id,
                    task_id,
                    comment.author_type,
                    comment.author_id,
                    comment.author_name,
                    comment.content,
                    comment.created_at,
                ),
            )
        return comment

    def list_comments(self, plan_id: str, task_id: str) -> list[TaskComment]:
        with self._db.connection() as conn:
            rows = conn.execute(
                """SELECT id, task_id, author_type, author_id, author_name, content, created_at
                   FROM task_comments WHERE plan_id = ? AND task_id = ? ORDER BY created_at""",
                (plan_id, task_id),
            ).fetchall()
            return [TaskComment.model_validate(dict(r)) for r in rows]

    def delete_comment(self, plan_id: str, comment_id: str) -> bool:
        with self._db.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM task_comments WHERE plan_id = ? AND id = ?",
                (plan_id, comment_id),
            )
            return cursor.rowcount > 0
