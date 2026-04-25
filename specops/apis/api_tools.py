"""API endpoints for the OpenAPI/Swagger api_tool marketplace category.

Mirrors the shape of ``mcp_registry.py``: a registry surface (search,
custom CRUD) plus per-agent install / list / uninstall. Generated tools
are produced inside the SpecialAgent worker at agent start; this module
just persists configuration and pokes the runtime for hot-reload.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from specops.auth import get_current_user
from specops.core.authz import require_agent_read, require_agent_write
from specops.core.domain.runtime import AgentRuntimeBackend
from specops.core.store.agent_config import AgentConfigStore
from specops.core.store.agents import AgentStore
from specops.core.store.shares import ShareStore
from specops.deps import (
    get_agent_config_store,
    get_agent_store,
    get_runtime,
    get_share_store,
)
from specops_lib.config.schema import OpenAPIToolConfig
from specops_lib.registry.factory import get_api_tool_registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["api-tools"])


_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
_RESERVED_IDS = frozenset({"custom", "search", "registry"})


class CustomApiToolRequest(BaseModel):
    """Request body for adding or updating a self-hosted API-tool entry."""

    id: str = Field(..., description="Unique entry id, e.g. internal-billing")
    name: str = Field(..., min_length=1)
    description: str = ""
    author: str = ""
    version: str = ""
    categories: list[str] = Field(default_factory=list)
    homepage: str = ""
    spec_url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    default_max_tools: int = Field(default=64, ge=1, le=256)
    required_env: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if v in _RESERVED_IDS:
            raise ValueError(f"id '{v}' is reserved")
        if not _SLUG_RE.match(v):
            raise ValueError("id must be lowercase letters, digits, dashes, or underscores")
        return v

    @field_validator("spec_url")
    @classmethod
    def _validate_spec_url(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("spec_url must be a valid http(s) URL")
        return v

    @field_validator("required_env")
    @classmethod
    def _strip_required_env(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]


class ApiToolInstallRequest(BaseModel):
    """Request to install an OpenAPI tool to an agent."""

    spec_id: str
    headers: dict[str, str] = Field(default_factory=dict)
    enabled_operations: list[str] | None = None
    max_tools: int = Field(default=64, ge=1, le=256)
    base_url_override: str | None = None
    role_hint: str = ""

    @field_validator("spec_id")
    @classmethod
    def _validate_spec_id(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError("spec_id must be a valid catalog id slug")
        return v


# -- Registry surface ---------------------------------------------------------


@router.get("/api/api-tools/registry")
async def search_api_tools(
    q: str = "",
    limit: int = Query(50, ge=1, le=200),
    _: dict = Depends(get_current_user),
):
    """Search the API-tool catalog (bundled + self-hosted)."""
    return get_api_tool_registry().search(q.strip(), limit=limit)


@router.get("/api/api-tools/custom")
async def list_custom_api_tools(_: dict = Depends(get_current_user)):
    """Return self-hosted custom catalog entries."""
    return get_api_tool_registry().list_custom_entries()


@router.post("/api/api-tools/custom", status_code=status.HTTP_201_CREATED)
async def add_custom_api_tool(
    body: CustomApiToolRequest,
    _: dict = Depends(get_current_user),
):
    """Add a self-hosted entry to the API-tool catalog."""
    registry = get_api_tool_registry()
    if registry.get_entry(body.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"API tool '{body.id}' already exists in the catalog",
        )
    entry = body.model_dump(exclude_none=True)
    registry.add_custom_entry(entry)
    return entry


@router.put("/api/api-tools/custom/{entry_id}")
async def update_custom_api_tool(
    entry_id: str,
    body: CustomApiToolRequest,
    _: dict = Depends(get_current_user),
):
    if body.id != entry_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL id and body id must match",
        )
    registry = get_api_tool_registry()
    if not registry.update_custom_entry(entry_id, body.model_dump(exclude_none=True)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API tool '{entry_id}' not found",
        )
    return body.model_dump(exclude_none=True)


@router.delete("/api/api-tools/custom/{entry_id}")
async def delete_custom_api_tool(
    entry_id: str,
    _: dict = Depends(get_current_user),
):
    registry = get_api_tool_registry()
    if not registry.delete_custom_entry(entry_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API tool '{entry_id}' not found",
        )
    return {"ok": True, "id": entry_id}


@router.get("/api/api-tools/registry/{entry_id}")
async def get_api_tool(
    entry_id: str,
    _: dict = Depends(get_current_user),
):
    entry = get_api_tool_registry().get_entry(entry_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API tool '{entry_id}' not in catalog",
        )
    return entry


# -- Per-agent install / list / uninstall -------------------------------------


@router.get("/api/agents/{agent_id}/api-tools")
async def list_agent_api_tools(
    agent_id: str,
    current: dict = Depends(get_current_user),
    store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    agent_config_store: AgentConfigStore = Depends(get_agent_config_store),
):
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_read(current, agent, share_store)
    cfg = agent_config_store.get_config(agent_id) or {}
    tools_cfg = cfg.get("tools") or {}
    raw = tools_cfg.get("openapi_tools") or tools_cfg.get("openapiTools") or {}
    items = []
    for spec_id, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        items.append(
            {
                "spec_id": spec_id,
                "spec_url": entry.get("spec_url") or entry.get("specUrl") or "",
                "max_tools": entry.get("max_tools") or entry.get("maxTools") or 64,
                "enabled_operations": entry.get("enabled_operations")
                or entry.get("enabledOperations"),
                "role_hint": entry.get("role_hint") or entry.get("roleHint") or "",
            }
        )
    return {"openapi_tools": items}


@router.post("/api/agents/{agent_id}/api-tools/install")
async def install_api_tool(
    agent_id: str,
    body: ApiToolInstallRequest,
    current: dict = Depends(get_current_user),
    store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    agent_config_store: AgentConfigStore = Depends(get_agent_config_store),
    runtime: AgentRuntimeBackend = Depends(get_runtime),
):
    """Install an API-tool spec on an agent.

    Persists the entry under ``tools.openapi_tools[spec_id]`` and, if the
    agent is running, pushes the new config so tools register live.
    """
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_write(current, agent, share_store)

    catalog_entry = get_api_tool_registry().get_entry(body.spec_id)
    if not catalog_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API tool '{body.spec_id}' not in catalog",
        )

    spec_url = catalog_entry.get("spec_url") or ""
    if not spec_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Catalog entry '{body.spec_id}' has no spec_url",
        )

    headers = body.headers or catalog_entry.get("headers") or {}
    cfg_obj = OpenAPIToolConfig(
        spec_id=body.spec_id,
        spec_url=spec_url,
        headers=dict(headers),
        enabled_operations=body.enabled_operations,
        max_tools=body.max_tools,
        base_url_override=body.base_url_override,
        role_hint=body.role_hint,
    )
    cfg_dict: dict[str, Any] = cfg_obj.model_dump(by_alias=False, exclude_none=True)

    persisted = agent_config_store.update_config(
        agent_id,
        {"tools": {"openapi_tools": {body.spec_id: cfg_dict}}},
        replace_keys=None,
    )
    full_openapi_tools = (
        persisted.get("tools", {}).get("openapi_tools")
        or persisted.get("tools", {}).get("openapiTools")
        or {}
    )

    try:
        await runtime.update_config(
            agent_id,
            {"tools": {"openapi_tools": full_openapi_tools}},
        )
    except Exception:
        logger.exception("Failed to push OpenAPI tool config to running agent")
        # Persisted config wins; agent picks it up on restart.
    return {
        "ok": True,
        "spec_id": body.spec_id,
        "spec_url": spec_url,
    }


@router.delete("/api/agents/{agent_id}/api-tools/{spec_id}")
async def uninstall_api_tool(
    agent_id: str,
    spec_id: str,
    current: dict = Depends(get_current_user),
    store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    agent_config_store: AgentConfigStore = Depends(get_agent_config_store),
    runtime: AgentRuntimeBackend = Depends(get_runtime),
):
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_write(current, agent, share_store)

    cfg = agent_config_store.get_config(agent_id) or {}
    tools_cfg = cfg.get("tools") or {}
    openapi_tools = tools_cfg.get("openapi_tools") or tools_cfg.get("openapiTools") or {}
    if spec_id not in openapi_tools:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API tool '{spec_id}' not installed on this agent",
        )
    new_openapi_tools = {k: v for k, v in openapi_tools.items() if k != spec_id}

    persisted = agent_config_store.update_config(
        agent_id,
        {"tools": {"openapi_tools": new_openapi_tools}},
        replace_keys=("tools.openapi_tools",),
    )
    full = (
        persisted.get("tools", {}).get("openapi_tools")
        or persisted.get("tools", {}).get("openapiTools")
        or {}
    )
    try:
        await runtime.update_config(agent_id, {"tools": {"openapi_tools": full}})
    except Exception:
        logger.exception("Failed to push OpenAPI tool removal to running agent")
    return {"ok": True, "spec_id": spec_id}
