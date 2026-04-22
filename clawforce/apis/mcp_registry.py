"""API endpoints for the MCP server registry (registry.modelcontextprotocol.io + self-hosted YAML catalog)."""

import logging
import re
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from clawforce.auth import get_current_user
from clawforce.core.authz import require_agent_read, require_agent_write
from clawforce.core.domain.runtime import AgentRuntimeBackend
from clawforce.core.runtimes._worker_runtime import WorkerRuntimeBase
from clawforce.core.store.agent_config import AgentConfigStore
from clawforce.core.store.agents import AgentStore
from clawforce.core.store.shares import ShareStore
from clawforce.deps import (
    get_agent_config_store,
    get_agent_store,
    get_mcp_registry,
    get_runtime,
    get_share_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp-registry"])


@router.get("/api/mcp-registry/search")
async def search_mcp_registry(
    q: str = "",
    limit: int = Query(50, ge=1, le=100),
    _: dict = Depends(get_current_user),
    registry=Depends(get_mcp_registry),
):
    """Search the MCP server registry (official registry + self-hosted YAML catalog)."""
    try:
        servers = await registry.search_mcp_servers(q.strip(), limit=limit)
    except Exception as e:
        logger.exception("MCP Registry search failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MCP Registry error: {e!s}"
        )

    # Stable ordering: self-hosted first, then by downloads desc.
    def _sort_key(entry: dict) -> tuple[int, int]:
        return (
            0 if entry.get("source") == "self-hosted" else 1,
            -int(entry.get("downloads", 0) or 0),
        )

    servers.sort(key=_sort_key)
    return servers


# Slug rule for self-hosted MCP servers: filesystem/URL-safe. Mirrors the skills
# rule to keep validation consistent across the marketplace surfaces.
_CUSTOM_MCP_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
# "servers" and "custom" collide with the registry route prefixes.
_RESERVED_CUSTOM_MCP_SLUGS = frozenset({"custom", "search", "servers"})


class CustomMCPRequest(BaseModel):
    """Request body for adding or updating a self-hosted MCP server entry."""

    slug: str = Field(..., description="Unique slug, e.g. my-internal-mcp")
    name: str = Field(..., min_length=1)
    description: str = ""
    author: str = ""
    version: str = ""
    categories: list[str] = Field(default_factory=list)
    homepage: str = ""
    repository: str = ""
    license: str = ""
    required_env: list[str] = Field(default_factory=list)
    install_config: dict[str, Any] = Field(
        ...,
        description="Either {'command': str, 'args': list[str]} or {'url': str}.",
    )

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not v:
            raise ValueError("slug must not be empty")
        if v in _RESERVED_CUSTOM_MCP_SLUGS:
            raise ValueError(f"slug '{v}' is reserved and cannot be used")
        if not _CUSTOM_MCP_SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase letters, digits, dashes or underscores "
                "(no leading/trailing separator, no slashes)"
            )
        return v

    @field_validator("required_env")
    @classmethod
    def _strip_required_env(cls, v: list[str]) -> list[str]:
        return [s.strip() for s in v if s and s.strip()]

    @field_validator("install_config")
    @classmethod
    def _validate_install_config(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("install_config must be an object")
        has_command = "command" in v
        has_url = "url" in v
        if has_command == has_url:
            raise ValueError("install_config must contain exactly one of 'command' or 'url'")
        if has_command:
            command = v.get("command")
            if not isinstance(command, str) or not command.strip():
                raise ValueError("install_config.command must be a non-empty string")
            args = v.get("args", [])
            if not isinstance(args, list) or any(not isinstance(a, str) for a in args):
                raise ValueError("install_config.args must be a list of strings")
            return {"command": command.strip(), "args": list(args)}
        url = v.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("install_config.url must be a non-empty string")
        trimmed = url.strip()
        parsed = urlparse(trimmed)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("install_config.url must be a valid http(s) URL with host")
        return {"url": trimmed}


@router.get("/api/mcp-registry/custom")
async def list_custom_mcp_servers(
    _: dict = Depends(get_current_user),
    registry=Depends(get_mcp_registry),
):
    """Return admin-managed self-hosted MCP server entries."""
    return registry.list_custom_entries()


@router.post("/api/mcp-registry/custom", status_code=status.HTTP_201_CREATED)
async def add_custom_mcp_server(
    body: CustomMCPRequest,
    _: dict = Depends(get_current_user),
    registry=Depends(get_mcp_registry),
):
    """Add a self-hosted MCP server to the admin catalog."""
    if registry.get_entry(body.slug):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"MCP server slug '{body.slug}' already exists in the catalog",
        )
    entry = body.model_dump(exclude_none=True)
    registry.add_custom_entry(entry)
    return entry


@router.put("/api/mcp-registry/custom/{slug}")
async def update_custom_mcp_server(
    slug: str,
    body: CustomMCPRequest,
    _: dict = Depends(get_current_user),
    registry=Depends(get_mcp_registry),
):
    """Update a self-hosted MCP server entry by slug."""
    if body.slug != slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL slug and body slug must match",
        )
    entry = body.model_dump(exclude_none=True)
    entry["slug"] = slug
    updated = registry.update_custom_entry(slug, entry)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Self-hosted MCP server '{slug}' not found",
        )
    return entry


@router.delete("/api/mcp-registry/custom/{slug}")
async def delete_custom_mcp_server(
    slug: str,
    _: dict = Depends(get_current_user),
    registry=Depends(get_mcp_registry),
):
    """Delete a self-hosted MCP server by slug."""
    removed = registry.delete_custom_entry(slug)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Self-hosted MCP server '{slug}' not found",
        )
    return {"ok": True, "slug": slug}


@router.get("/api/mcp-registry/servers/{server_id:path}")
async def get_mcp_server(
    server_id: str,
    _: dict = Depends(get_current_user),
    registry=Depends(get_mcp_registry),
):
    """Get details for a specific MCP server from the registry."""
    try:
        server = await registry.get_mcp_server(server_id)
    except Exception as e:
        logger.exception("MCP Registry get_server failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"MCP Registry error: {e!s}"
        )

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Server not found in MCP Registry"
        )

    return server


class MCPInstallRequest(BaseModel):
    """Request to install an MCP server to an agent."""

    server_id: str
    server_name: str
    command: str = ""
    args: list[str] = []
    env: dict[str, str] = {}
    url: str = ""
    # Config schema declared by the registry entry.
    # Stored in the server config so the UI can render config inputs.
    config_schema: list[dict] = []


@router.get("/api/agents/{agent_id}/mcp-servers")
async def list_mcp_servers(
    agent_id: str,
    current: dict = Depends(get_current_user),
    store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    runtime: AgentRuntimeBackend = Depends(get_runtime),
):
    """Get list of installed MCP servers and their connection status for an agent.

    Returns server status including name, connection status, tool count, and any errors.
    """
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_read(current, agent, share_store)

    runtime_status = await runtime.get_status(agent_id)
    mcp_servers = runtime_status.mcp or {}

    return {
        "agent_id": agent_id,
        "agent_status": runtime_status.status,
        "servers": mcp_servers,
    }


@router.get("/api/agents/{agent_id}/mcp-servers/{server_key}/tools")
async def list_mcp_server_tools(
    agent_id: str,
    server_key: str,
    current: dict = Depends(get_current_user),
    store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    runtime: AgentRuntimeBackend = Depends(get_runtime),
):
    """Get list of tools provided by a specific MCP server.

    The agent must be running to retrieve tools. Returns tool definitions including
    name, description, and parameters.
    """
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_read(current, agent, share_store)

    runtime_status = await runtime.get_status(agent_id)
    if runtime_status.status != "running":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Agent is not running (status: {runtime_status.status}). Start the agent first.",
        )

    mcp_servers = runtime_status.mcp or {}
    if server_key not in mcp_servers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_key}' not found or not connected",
        )

    # Only WorkerRuntimeBase supports WebSocket-based tool retrieval
    if not isinstance(runtime, WorkerRuntimeBase):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Tool retrieval not supported for this runtime backend",
        )

    try:
        tools_defs = await runtime._ws_request(
            agent_id, "get_mcp_tools", server_key=server_key, timeout=10.0
        )
        if tools_defs and tools_defs.get("ok"):
            return {
                "agent_id": agent_id,
                "server_key": server_key,
                "tools": tools_defs.get("data", {}).get("tools", []),
            }
        return {
            "agent_id": agent_id,
            "server_key": server_key,
            "tools": [],
            "error": tools_defs.get("error", "Failed to fetch tools")
            if tools_defs
            else "Unknown error",
        }
    except Exception as e:
        logger.exception(f"Failed to get MCP tools for server {server_key}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to get MCP tools: {str(e)}",
        )


@router.post("/api/agents/{agent_id}/mcp-servers/install")
async def install_mcp_server(
    agent_id: str,
    body: MCPInstallRequest,
    current: dict = Depends(get_current_user),
    store: AgentStore = Depends(get_agent_store),
    share_store: ShareStore = Depends(get_share_store),
    agent_config_store: AgentConfigStore = Depends(get_agent_config_store),
    runtime: AgentRuntimeBackend = Depends(get_runtime),
):
    """Install an MCP server to an agent's config.

    The server config is added to tools.mcp_servers and the agent hot-reloads it.
    """
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    require_agent_write(current, agent, share_store)

    runtime_status = await runtime.get_status(agent_id)
    if runtime_status.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent is not running (status: {runtime_status.status}). Start the agent first.",
        )

    server_key = body.server_name.replace("/", "_").replace(".", "_").replace("@", "")
    if not server_key:
        server_key = body.server_id.replace("/", "_").replace(".", "_").replace("@", "")

    mcp_config: dict = {}
    if body.url:
        mcp_config["url"] = body.url
        if body.env:
            mcp_config["env"] = body.env
    elif body.command:
        mcp_config["command"] = body.command
        mcp_config["args"] = body.args
        mcp_config["env"] = body.env
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'url' or 'command' must be provided",
        )

    if body.config_schema:
        mcp_config["configSchema"] = body.config_schema

    # Persist to the DB store first (source of truth for restarts).
    # Use replace_keys so the full mcp_servers dict is stored atomically.
    persisted = agent_config_store.update_config(
        agent_id,
        {"tools": {"mcp_servers": {server_key: mcp_config}}},
        replace_keys=None,  # merge is fine here — we're only adding, not removing
    )

    # Push the full persisted mcp_servers to the running agent so it hot-reloads.
    # apply_update replaces mcp_servers entirely (to support deletions), so we must
    # send the complete desired state — not just the new server.
    full_mcp_servers = persisted.get("tools", {}).get("mcp_servers", {})
    config_update = {"tools": {"mcp_servers": full_mcp_servers}}

    try:
        updated = await runtime.update_config(agent_id, config_update)
    except Exception as e:
        logger.exception("Failed to install MCP server")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to update config: {e!s}"
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Config update failed (agent may have stopped)",
        )

    return {
        "ok": True,
        "server_key": server_key,
        "message": f"MCP server '{server_key}' installed and connected.",
    }
