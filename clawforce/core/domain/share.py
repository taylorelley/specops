"""Share records for claws (agents) and plans.

A share is a grant of a permission level to a specific user on a specific
resource. Ownership is tracked on the resource itself (``owner_user_id``) and
never appears as a share row.
"""

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from clawforce.core.domain.agent import Base

SharePermission = Literal["viewer", "editor", "manager"]

# Ordering for "at least" checks — higher index = more privileged.
_PERMISSION_RANK: dict[str, int] = {
    "viewer": 1,
    "editor": 2,
    "manager": 3,
    "owner": 4,
}


def permission_rank(permission: str) -> int:
    """Return the rank of a permission. Unknown values return 0."""
    return _PERMISSION_RANK.get(permission, 0)


def at_least(actual: str | None, required: str) -> bool:
    """True when actual permission meets or exceeds required.

    Unknown ``required`` values fail closed (return False) so callers cannot
    accidentally grant access by passing a typo like ``"edit"`` instead of
    ``"editor"``. Unknown ``actual`` values likewise fail closed.
    """
    if actual is None:
        return False
    if required not in _PERMISSION_RANK:
        return False
    if actual not in _PERMISSION_RANK:
        return False
    return _PERMISSION_RANK[actual] >= _PERMISSION_RANK[required]


class AgentShare(Base):
    """A share grant on an agent."""

    agent_id: str = ""
    user_id: str = ""
    permission: SharePermission = "viewer"
    granted_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PlanShare(Base):
    """A share grant on a plan."""

    plan_id: str = ""
    user_id: str = ""
    permission: SharePermission = "viewer"
    granted_by: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
