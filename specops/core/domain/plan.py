"""Plan, task, and column data models."""

import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from specops.core.domain.agent import Base

ColumnKind = Literal["standard", "review"]
"""Column types. A "review" column gates task progression on human approval."""

ReviewStatus = Literal["pending", "approved", "rejected"]


class PlanTask(Base):
    """A single task on a plan board.

    Review fields are only meaningful when the task is (or has been) sitting in
    a column of kind ``review``. ``requires_review`` defaults to True so tasks
    in a review-gated plan respect the gate; a human can flip it False on a
    per-task basis to bypass review for that task.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    column_id: str = ""
    agent_id: str = ""
    position: int = 0
    requires_review: bool = True
    review_status: ReviewStatus | None = None
    reviewed_by: str = ""
    reviewed_at: str = ""
    review_note: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PlanColumn(Base):
    """A column on a plan Kanban board.

    ``kind`` is "standard" for normal columns. A "review" column requires a
    human approval before any task with ``requires_review=True`` can be moved
    out of it — see ``specops.apis.plans`` for the enforcement path.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    position: int = 0
    kind: ColumnKind = "standard"


class TaskComment(Base):
    """A comment on a plan task (human or agent)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    author_type: str = ""  # "admin" or "agent"
    author_id: str = ""
    author_name: str = ""
    content: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _default_plan_columns(plan_id: str | None = None) -> list[PlanColumn]:
    """Default Kanban columns: Todo, In Progress, Blocked, Done.

    If plan_id is provided, column IDs are prefixed with the plan ID to ensure uniqueness.
    """
    prefix = f"{plan_id}-" if plan_id else ""
    return [
        PlanColumn(id=f"{prefix}col-todo", title="Todo", position=0),
        PlanColumn(id=f"{prefix}col-in-progress", title="In Progress", position=1),
        PlanColumn(id=f"{prefix}col-blocked", title="Blocked", position=2),
        PlanColumn(id=f"{prefix}col-done", title="Done", position=3),
    ]


def _slugify_column_title(title: str) -> str:
    """Lowercase, hyphenate, strip non-alphanumerics — matches the 'col-<short>' id convention."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "col"


def columns_from_template(plan_id: str, template_columns: list[dict] | None) -> list[PlanColumn]:
    """Produce plan columns from a template definition.

    If template_columns is empty or None, returns the four default columns.
    Otherwise, each entry must have a ``title``; ``position`` is optional and
    defaults to its index in the list. ``kind`` is optional and defaults to
    ``"standard"``; set it to ``"review"`` to mark the column as a human review
    gate. Column IDs follow the ``{plan_id}-col-{slug}`` convention so
    ``PlanStore._resolve_column_id`` keeps working for short-name task
    references.

    Duplicate or slug-equivalent titles (e.g., "Review" and "review") are
    deduplicated with a numeric suffix (``-2``, ``-3``, …) so the resulting ids
    stay unique inside ``plan_columns``.
    """
    if not template_columns:
        return _default_plan_columns(plan_id)
    out: list[PlanColumn] = []
    used_slugs: set[str] = set()
    for idx, col in enumerate(template_columns):
        title = str(col.get("title", "")).strip() or f"Column {idx + 1}"
        position = col.get("position")
        if position is None:
            position = idx
        base_slug = _slugify_column_title(title)
        slug = base_slug
        suffix = 2
        while slug in used_slugs:
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        used_slugs.add(slug)
        raw_kind = str(col.get("kind", "standard") or "standard").strip().lower()
        kind: ColumnKind = "review" if raw_kind == "review" else "standard"
        out.append(
            PlanColumn(
                id=f"{plan_id}-col-{slug}",
                title=title,
                position=int(position),
                kind=kind,
            )
        )
    return out


class PlanDef(Base):
    """A plan with Kanban columns and tasks. Agents assigned collaborate via shared workspace.

    Status lifecycle: draft -> active -> (paused | completed).
    - draft: Created, not yet activated. Use activate to start.
    - active: Running. Assigned agents receive context and work on tasks.
    - paused: Admin paused the plan. Agents should stop working on it until re-activated.
    - completed: Plan finished.

    Capabilities:
    - Agent (assigned to plan): create plans (auto-assigned), read plans, activate plans,
      create/update tasks, add/read artifacts. Cannot: pause plans, assign/remove agents,
      delete plans/tasks/artifacts, update plan metadata.
    - Admin: full control (activate, deactivate, assign agents, delete, etc.).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    owner_user_id: str = ""
    name: str = ""
    description: str = ""
    status: str = "draft"
    columns: list[PlanColumn] = Field(default_factory=_default_plan_columns)
    tasks: list[PlanTask] = Field(default_factory=list)
    agent_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
