"""Executions API: read-side surface for the durable execution journal."""

from __future__ import annotations

import logging

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

logger = logging.getLogger(__name__)

router = APIRouter(tags=["executions"])


class ResumeRequest(BaseModel):
    text: str = ""


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
