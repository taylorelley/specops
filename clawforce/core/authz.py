"""Resource-level authorization for claws (agents).

Permission tiers, least → most privileged:
    viewer < editor < manager < owner

Admins (``user.role == "admin"``) bypass every check and always resolve to
``owner``. A caller with no ownership, no admin role, and no share row gets
``None`` and is rejected.
"""

from fastapi import HTTPException, status

from clawforce.core.domain.agent import AgentDef
from clawforce.core.domain.share import at_least
from clawforce.core.store.shares import ShareStore


def _is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


def effective_agent_permission(user: dict, agent: AgentDef, share_store: ShareStore) -> str | None:
    """Return the caller's effective permission on ``agent``.

    Returns one of ``"owner"``, ``"manager"``, ``"editor"``, ``"viewer"``, or
    ``None`` if the caller has no access at all.
    """
    if _is_admin(user):
        return "owner"
    user_id = user.get("id") or ""
    if not user_id:
        return None
    if agent.owner_user_id and agent.owner_user_id == user_id:
        return "owner"
    # Unowned agents fall back to a share-only check; admins already returned.
    return share_store.get_agent_permission(agent.id, user_id)


def _require_agent_permission(
    user: dict, agent: AgentDef, share_store: ShareStore, required: str
) -> str:
    effective = effective_agent_permission(user, agent, share_store)
    if not at_least(effective, required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this agent",
        )
    return effective or required


def require_agent_read(user: dict, agent: AgentDef, share_store: ShareStore) -> str:
    return _require_agent_permission(user, agent, share_store, "viewer")


def require_agent_write(user: dict, agent: AgentDef, share_store: ShareStore) -> str:
    return _require_agent_permission(user, agent, share_store, "editor")


def require_agent_manage(user: dict, agent: AgentDef, share_store: ShareStore) -> str:
    return _require_agent_permission(user, agent, share_store, "manager")


def require_agent_owner(user: dict, agent: AgentDef, share_store: ShareStore) -> str:
    return _require_agent_permission(user, agent, share_store, "owner")


# ---- Legacy compatibility helpers (deprecated) ----


def can_access_agent(user: dict, agent: AgentDef) -> bool:
    """Legacy helper retained for callers that predate share-aware checks.

    Prefer ``effective_agent_permission`` + the ``require_agent_*`` helpers.
    """
    if _is_admin(user):
        return True
    return bool(agent.owner_user_id) and agent.owner_user_id == user.get("id")


def require_agent_access(user: dict, agent: AgentDef) -> None:
    """Legacy helper — equivalent to ``require_agent_read`` without shares."""
    if not can_access_agent(user, agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this agent"
        )
