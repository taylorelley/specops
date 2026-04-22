"""Plan access control with tiered permissions.

Permission tiers, least → most privileged:
    viewer < editor < manager < owner

Admins (``user.role == "admin"``) bypass every check. Agents authenticated via
``get_user_or_agent`` must be assigned to the plan (present in
``plan.agent_ids``) — their write scope is governed elsewhere (e.g. "agents can
only move their own tasks"); here we only gate whether they see the plan at
all.
"""

from fastapi import HTTPException, status

from clawforce.core.domain.share import at_least
from clawforce.core.store.shares import ShareStore


def _is_admin_user(caller: dict) -> bool:
    return caller.get("type") == "user" and caller.get("role") == "admin"


def effective_plan_permission(caller: dict, plan, share_store: ShareStore) -> str | None:
    """Return the caller's effective permission on ``plan``, or None if no access."""
    if caller.get("type") == "agent":
        if plan and caller.get("agent_id") in (plan.agent_ids or []):
            return "editor"
        return None
    if _is_admin_user(caller):
        return "owner"
    user_id = caller.get("id") or ""
    if not user_id:
        return None
    if getattr(plan, "owner_user_id", "") == user_id and user_id:
        return "owner"
    return share_store.get_plan_permission(plan.id, user_id)


def _require_plan_permission(caller: dict, plan, share_store: ShareStore, required: str) -> str:
    effective = effective_plan_permission(caller, plan, share_store)
    if not at_least(effective, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this plan",
        )
    return effective or required


def require_plan_read(caller: dict, plan, share_store: ShareStore) -> str:
    return _require_plan_permission(caller, plan, share_store, "viewer")


def require_plan_write(caller: dict, plan, share_store: ShareStore) -> str:
    return _require_plan_permission(caller, plan, share_store, "editor")


def require_plan_manage(caller: dict, plan, share_store: ShareStore) -> str:
    return _require_plan_permission(caller, plan, share_store, "manager")


def require_plan_owner(caller: dict, plan, share_store: ShareStore) -> str:
    return _require_plan_permission(caller, plan, share_store, "owner")


# ---- Legacy helper (still used in a few places) ----


def require_plan_access(plan, caller: dict) -> None:
    """Raise 403 if caller cannot read the plan.

    Users with role=admin always pass. Regular users must own or have a share on
    the plan. Agents must be assigned to the plan. This is a compatibility
    wrapper over the share-aware helpers and does NOT look up shares itself; it
    preserves the historic behavior where user-type callers had blanket read
    access. New call sites should prefer ``require_plan_read``.
    """
    if caller.get("type") == "user":
        return
    if (
        caller.get("type") == "agent"
        and plan
        and caller.get("agent_id") not in (plan.agent_ids or [])
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent is not assigned to this plan",
        )
