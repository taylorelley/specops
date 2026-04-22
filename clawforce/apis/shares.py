"""Sharing endpoints for claws (agents) and plans.

Permission levels (least → most privileged):
    viewer   - read only
    editor   - read and modify
    manager  - editor + share/unshare, change other users' permissions
    owner    - manager + delete, transfer ownership (owner is the owner_user_id)

Owner and admin bypass every check. Managers can modify shares but cannot
target the owner (nobody can share with themselves).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from clawforce.auth import get_current_user
from clawforce.core.authz import require_agent_manage
from clawforce.core.plan_access import require_plan_manage
from clawforce.core.store.agents import AgentStore
from clawforce.core.store.plans import PlanStore
from clawforce.core.store.shares import ShareStore
from clawforce.core.store.users import UserStore
from clawforce.deps import (
    get_agent_store,
    get_plan_store,
    get_share_store,
    get_user_store,
)

router = APIRouter(tags=["shares"])

_ALLOWED_PERMISSIONS = {"viewer", "editor", "manager"}


class ShareUpdate(BaseModel):
    permission: str


def _require_permission_value(permission: str) -> str:
    if permission not in _ALLOWED_PERMISSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid permission '{permission}'. Expected viewer, editor, or manager.",
        )
    return permission


def _serialize_share(share, username: str) -> dict:
    data = share.model_dump()
    data["username"] = username
    return data


# ---------------------------------------------------------------------------
# Agent shares
# ---------------------------------------------------------------------------


@router.get("/api/agents/{agent_id}/shares")
def list_agent_shares(
    agent_id: str,
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    user_store: UserStore = Depends(get_user_store),
):
    agent = agent_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_manage(current, agent, share_store)
    shares = share_store.list_agent_shares(agent_id)
    username_by_id = {u.id: u.username for u in user_store.list_users()}
    return [_serialize_share(s, username_by_id.get(s.user_id, "")) for s in shares]


@router.put("/api/agents/{agent_id}/shares/{user_id}")
def set_agent_share(
    agent_id: str,
    user_id: str,
    body: ShareUpdate,
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    user_store: UserStore = Depends(get_user_store),
):
    agent = agent_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_manage(current, agent, share_store)
    permission = _require_permission_value(body.permission)
    target = user_store.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if agent.owner_user_id and agent.owner_user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share a resource with its owner",
        )
    share = share_store.set_agent_share(
        agent_id=agent_id,
        user_id=user_id,
        permission=permission,
        granted_by=current.get("id", ""),
    )
    return _serialize_share(share, target.username)


@router.delete("/api/agents/{agent_id}/shares/{user_id}")
def remove_agent_share(
    agent_id: str,
    user_id: str,
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
):
    agent = agent_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_manage(current, agent, share_store)
    share_store.remove_agent_share(agent_id, user_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Plan shares
# ---------------------------------------------------------------------------


@router.get("/api/plans/{plan_id}/shares")
def list_plan_shares(
    plan_id: str,
    current: dict = Depends(get_current_user),
    plan_store: PlanStore = Depends(get_plan_store),
    share_store: ShareStore = Depends(get_share_store),
    user_store: UserStore = Depends(get_user_store),
):
    plan = plan_store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    require_plan_manage({"type": "user", **current}, plan, share_store)
    shares = share_store.list_plan_shares(plan_id)
    username_by_id = {u.id: u.username for u in user_store.list_users()}
    return [_serialize_share(s, username_by_id.get(s.user_id, "")) for s in shares]


@router.put("/api/plans/{plan_id}/shares/{user_id}")
def set_plan_share(
    plan_id: str,
    user_id: str,
    body: ShareUpdate,
    current: dict = Depends(get_current_user),
    plan_store: PlanStore = Depends(get_plan_store),
    share_store: ShareStore = Depends(get_share_store),
    user_store: UserStore = Depends(get_user_store),
):
    plan = plan_store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    require_plan_manage({"type": "user", **current}, plan, share_store)
    permission = _require_permission_value(body.permission)
    target = user_store.get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if plan.owner_user_id and plan.owner_user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot share a resource with its owner",
        )
    share = share_store.set_plan_share(
        plan_id=plan_id,
        user_id=user_id,
        permission=permission,
        granted_by=current.get("id", ""),
    )
    return _serialize_share(share, target.username)


@router.delete("/api/plans/{plan_id}/shares/{user_id}")
def remove_plan_share(
    plan_id: str,
    user_id: str,
    current: dict = Depends(get_current_user),
    plan_store: PlanStore = Depends(get_plan_store),
    share_store: ShareStore = Depends(get_share_store),
):
    plan = plan_store.get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    require_plan_manage({"type": "user", **current}, plan, share_store)
    share_store.remove_plan_share(plan_id, user_id)
    return {"ok": True}
