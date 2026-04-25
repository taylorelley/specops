"""Executions API: read-side surface for the durable execution journal."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from specops.auth import get_current_user
from specops.core.authz import require_agent_read, require_agent_write
from specops.core.store.agents import AgentStore
from specops.core.store.execution_events import ExecutionEventsStore
from specops.core.store.executions import ExecutionsStore
from specops.core.store.shares import ShareStore
from specops.core.ws import ConnectionManager
from specops.deps import (
    get_agent_store,
    get_execution_events_store,
    get_executions_store,
    get_share_store,
    get_ws_manager,
)
from specops_lib.activity import ActivityEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["executions"])


class ResumeRequest(BaseModel):
    text: str = ""


class ResolveRequest(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = ""
    approver_id: str = ""


def _check_agent_read(
    agent_id: str,
    current: dict,
    agent_store: AgentStore,
    share_store: ShareStore,
) -> None:
    agent = agent_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_read(current, agent, share_store)


@router.get("/api/agents/{agent_id}/executions")
async def list_agent_executions(
    agent_id: str,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    executions_store: ExecutionsStore = Depends(get_executions_store),
):
    _check_agent_read(agent_id, current, agent_store, share_store)
    rows = executions_store.list_for_agent(agent_id, status=status_filter, limit=limit)
    return {"executions": [r.model_dump() for r in rows]}


@router.get("/api/executions")
async def list_executions_global(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    executions_store: ExecutionsStore = Depends(get_executions_store),
):
    """List executions across all agents the caller can read.

    The Pending Approvals UI uses this with ``status=paused`` to show
    every execution waiting on a human decision.
    """
    if status_filter == "paused":
        rows = executions_store.list_paused(limit=limit)
    else:
        # Generic path: enumerate via per-agent listing for visible agents.
        visible_to = None if current.get("role") == "admin" else current.get("id")
        agents = agent_store.list_agents(visible_to_user_id=visible_to)
        rows = []
        for a in agents:
            rows.extend(executions_store.list_for_agent(a.id, status=status_filter, limit=limit))
        rows.sort(key=lambda e: e.created_at, reverse=True)
        rows = rows[:limit]
    # RBAC filter: drop executions on agents the caller can't read.
    out = []
    for ex in rows:
        agent = agent_store.get_agent(ex.agent_id)
        if not agent:
            continue
        try:
            require_agent_read(current, agent, share_store)
        except HTTPException:
            continue
        out.append(ex.model_dump())
    return {"executions": out}


@router.get("/api/executions/{execution_id}")
async def get_execution(
    execution_id: str,
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    executions_store: ExecutionsStore = Depends(get_executions_store),
):
    execution = executions_store.get(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    _check_agent_read(execution.agent_id, current, agent_store, share_store)
    return execution.model_dump()


@router.post("/api/executions/{execution_id}/resolve")
async def resolve_execution(
    execution_id: str,
    body: ResolveRequest,
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    executions_store: ExecutionsStore = Depends(get_executions_store),
    execution_events_store: ExecutionEventsStore = Depends(get_execution_events_store),
    ws_manager: ConnectionManager = Depends(get_ws_manager),
):
    """Resolve a paused execution.

    Writes a ``hitl_resolved`` event into the journal, flips
    ``executions.status`` to ``running`` (approve) or ``failed``
    (reject), and — if the worker is connected — sends a
    ``{type: "resume", execution_id}`` message so it picks up where it
    left off. If no worker is connected the execution is flagged
    ``pending_resume`` and a worker spun up later will resume on
    register.
    """
    execution = executions_store.get(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    if execution.status not in ("paused", "running"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Execution is {execution.status}; cannot resolve",
        )
    agent = agent_store.get_agent(execution.agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_write(current, agent, share_store)

    last_waiting = _last_event(execution_events_store, execution_id, kinds=("hitl_waiting",))
    guardrail_name = ""
    position = ""
    tool_name = None
    if last_waiting:
        payload = _parse_payload(last_waiting.get("payload_json"))
        guardrail_name = str(payload.get("guardrail") or "")
        position = str(payload.get("position") or "")
        tool_name = payload.get("tool_name")

    resolved_payload = {
        "guardrail": guardrail_name,
        "position": position,
        "tool_name": tool_name,
        "decision": body.decision,
        "note": body.note,
        "approver_id": body.approver_id or current.get("id", ""),
    }
    ev = ActivityEvent(
        agent_id=execution.agent_id,
        event_type="hitl_resolved",
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_id=uuid.uuid4().hex,
        execution_id=execution_id,
        step_id=execution.last_step_id or "",
        event_kind="hitl_resolved",
        tool_name=tool_name,
        result_status="ok" if body.decision == "approve" else "error",
        payload_json=json.dumps(resolved_payload),
    )
    execution_events_store.insert(ev)

    if body.decision == "reject":
        executions_store.set_status(
            execution_id, "failed", error_message=body.note or "rejected by human"
        )
        return {"ok": True, "decision": "reject", "resumed": False}

    executions_store.set_status(execution_id, "running")
    delivered = await ws_manager.send_to_agent(
        execution.agent_id,
        {
            "type": "resume",
            "execution_id": execution_id,
            "text": "[Resume after approval]",
            "channel": execution.channel,
            "chat_id": execution.chat_id,
            "session_key": execution.session_key,
        },
    )
    if not delivered:
        executions_store.set_pending_resume(execution_id, True)
        return {"ok": True, "decision": "approve", "resumed": False, "queued": True}
    executions_store.set_pending_resume(execution_id, False)
    return {"ok": True, "decision": "approve", "resumed": True}


def _last_event(
    store: ExecutionEventsStore,
    execution_id: str,
    *,
    kinds: tuple[str, ...],
) -> dict | None:
    for row in reversed(store.list_for_execution(execution_id)):
        if row.get("event_kind") in kinds:
            return row
    return None


def _parse_payload(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@router.post("/api/executions/{execution_id}/resume")
async def resume_execution(
    execution_id: str,
    body: ResumeRequest,
    request: Request,
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    executions_store: ExecutionsStore = Depends(get_executions_store),
    ws_manager: ConnectionManager = Depends(get_ws_manager),
):
    """Phase 1 admin hand-crank: re-deliver the original message to the
    worker with the same execution_id. The journal short-circuits any
    completed tool calls; ``checkpoint``-safety tools whose call started
    but never finished surface an "[INTERRUPTED]" message to the LLM.

    Phase 4 supersedes this endpoint with ``/resolve`` for HITL flows.
    """
    execution = executions_store.get(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    agent = agent_store.get_agent(execution.agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_write(current, agent, share_store)

    text = body.text or "[Resume previous turn]"
    delivered = await ws_manager.send_to_agent(
        execution.agent_id,
        {
            "type": "resume",
            "execution_id": execution_id,
            "text": text,
            "channel": execution.channel,
            "chat_id": execution.chat_id,
            "session_key": execution.session_key,
        },
    )
    if not delivered:
        executions_store.set_pending_resume(execution_id, True)
        return {"ok": True, "resumed": False, "queued": True}
    executions_store.set_status(execution_id, "running")
    executions_store.set_pending_resume(execution_id, False)
    return {"ok": True, "resumed": True}


@router.get("/api/executions/{execution_id}/events")
async def list_execution_events(
    execution_id: str,
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
    current: dict = Depends(get_current_user),
    agent_store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    executions_store: ExecutionsStore = Depends(get_executions_store),
    execution_events_store: ExecutionEventsStore = Depends(get_execution_events_store),
):
    execution = executions_store.get(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    _check_agent_read(execution.agent_id, current, agent_store, share_store)
    events = execution_events_store.list_for_execution(execution_id, after_id=after_id, limit=limit)
    return {"execution_id": execution_id, "events": events}
