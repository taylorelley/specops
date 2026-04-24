"""Centrally-managed LLM provider endpoints.

Admin-only CRUD for provider credentials that agents reference by id via
``config["providers"]["provider_ref"]``. A read-only list endpoint exposes
``(id, name, type)`` to any authenticated user so the agent-config UI can show
a dropdown without leaking secrets.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from specialagent.providers.registry import PROVIDERS
from specops.apis.users import _require_admin
from specops.auth import get_current_user
from specops.core.database import get_database
from specops.core.store.agent_config import AgentConfigStore
from specops.core.store.llm_providers import LLMProviderStore
from specops.deps import get_fernet, get_llm_provider_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["llm-providers"])


class LLMProviderType(BaseModel):
    name: str
    display_name: str
    is_gateway: bool = False
    is_local: bool = False
    requires_api_base: bool = False


class LLMProviderPublic(BaseModel):
    id: str
    name: str
    type: str


class LLMProviderAdmin(BaseModel):
    id: str
    name: str
    type: str
    api_key: str = ""
    api_base: str = ""
    extra_headers: dict[str, str] | None = None
    created_at: str
    updated_at: str


class LLMProviderCreate(BaseModel):
    name: str
    type: str
    api_key: str = ""
    api_base: str = ""
    extra_headers: dict[str, str] | None = None


class LLMProviderUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    api_key: str | None = None
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None


def _non_oauth_types() -> list[LLMProviderType]:
    """Supported provider types for the admin UI: everything except OAuth flows.

    OAuth providers (chatgpt, openai_codex, github_copilot) stay per-agent
    because their tokens are user-session specific.
    """
    out: list[LLMProviderType] = []
    for spec in PROVIDERS:
        if spec.is_oauth:
            continue
        requires_api_base = spec.is_local or spec.name == "custom"
        out.append(
            LLMProviderType(
                name=spec.name,
                display_name=spec.display_name or spec.name,
                is_gateway=spec.is_gateway,
                is_local=spec.is_local,
                requires_api_base=requires_api_base,
            )
        )
    return out


def _as_admin(row: dict) -> LLMProviderAdmin:
    return LLMProviderAdmin(
        id=row["id"],
        name=row["name"],
        type=row["type"],
        api_key=row.get("api_key") or "",
        api_base=row.get("api_base") or "",
        extra_headers=row.get("extra_headers"),
        created_at=row.get("created_at", ""),
        updated_at=row.get("updated_at", ""),
    )


@router.get("/api/admin/llm-providers/types", response_model=list[LLMProviderType])
def list_provider_types(current: dict = Depends(get_current_user)):
    """Enumerate non-OAuth provider types the admin can configure."""
    _require_admin(current)
    return _non_oauth_types()


@router.get("/api/admin/llm-providers", response_model=list[LLMProviderAdmin])
def list_providers_admin(
    current: dict = Depends(get_current_user),
    store: LLMProviderStore = Depends(get_llm_provider_store),
):
    """Admin view — includes redacted api_key and full config metadata."""
    _require_admin(current)
    return [_as_admin(row) for row in store.list(with_secrets=False)]


@router.post(
    "/api/admin/llm-providers",
    response_model=LLMProviderAdmin,
    status_code=status.HTTP_201_CREATED,
)
def create_provider(
    body: LLMProviderCreate,
    current: dict = Depends(get_current_user),
    store: LLMProviderStore = Depends(get_llm_provider_store),
):
    _require_admin(current)
    if not body.name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")
    type_names = {t.name for t in _non_oauth_types()}
    if body.type not in type_names:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown provider type '{body.type}'. Must be one of: {sorted(type_names)}",
        )
    try:
        row = store.create(
            name=body.name.strip(),
            type=body.type,
            api_key=body.api_key or "",
            api_base=body.api_base or "",
            extra_headers=body.extra_headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _as_admin(row)


@router.patch("/api/admin/llm-providers/{provider_id}", response_model=LLMProviderAdmin)
def update_provider(
    provider_id: str,
    body: LLMProviderUpdate,
    current: dict = Depends(get_current_user),
    store: LLMProviderStore = Depends(get_llm_provider_store),
):
    """Patch a provider row.

    Note: changing ``api_key`` / ``api_base`` / ``extra_headers`` does not
    hot-reload credentials for agents already running. The new values take
    effect the next time the agent connects (WebSocket ``get_config``) or when
    the agent's config is pushed via ``PUT /api/agents/{id}/config``.
    """
    _require_admin(current)
    if body.name is not None and not body.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="name must not be empty"
        )
    if body.type is not None:
        type_names = {t.name for t in _non_oauth_types()}
        if body.type not in type_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown provider type '{body.type}'",
            )
    try:
        row = store.update(
            provider_id,
            name=body.name.strip() if body.name else None,
            type=body.type,
            api_key=body.api_key,
            api_base=body.api_base,
            extra_headers=body.extra_headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return _as_admin(row)


@router.delete("/api/admin/llm-providers/{provider_id}")
def delete_provider(
    provider_id: str,
    current: dict = Depends(get_current_user),
    store: LLMProviderStore = Depends(get_llm_provider_store),
):
    _require_admin(current)
    # Hold a single DB connection for the reference scan + delete so another
    # admin cannot race in a new agent_config write between the two steps.
    db = get_database()
    with db.connection() as conn:
        row = conn.execute("SELECT 1 FROM llm_providers WHERE id = ?", (provider_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
        referencing = _scan_agents_referencing(conn, provider_id)
        if referencing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Provider is referenced by one or more agents",
                    "agent_ids": referencing,
                },
            )
        conn.execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
    # ``store`` parameter is kept so permission injection happens through the
    # same dep as the other endpoints; deletion itself ran in the conn above.
    _ = store
    return {"ok": True}


@router.get("/api/llm-providers", response_model=list[LLMProviderPublic])
def list_providers_public(
    _: dict = Depends(get_current_user),
    store: LLMProviderStore = Depends(get_llm_provider_store),
):
    """Read-only list for agent-config dropdowns. Never includes credentials."""
    return [LLMProviderPublic(**row) for row in store.list_public()]


def _scan_agents_referencing(conn, provider_id: str) -> list[str]:
    """Return agent IDs whose persisted config references ``provider_id``.

    Runs inside an existing DB connection (so callers can keep check + delete
    atomic). If a row cannot be decrypted/parsed, the agent is added to the
    returned list so the delete is *blocked* — admins should resolve the broken
    row before we silently strand an agent on a deleted provider.
    """
    db = get_database()
    out: list[str] = []
    rows = conn.execute("SELECT agent_id, config_json FROM agent_config").fetchall()
    # Reuse the shared Fernet instance via deps so decryption matches writes.
    cfg_store = AgentConfigStore(db, fernet=get_fernet())
    for row in rows:
        agent_id = row["agent_id"]
        try:
            cfg = cfg_store.get_config(agent_id) or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not read agent_config for %s while scanning provider references: %s",
                agent_id,
                exc,
            )
            out.append(agent_id)
            continue
        providers = cfg.get("providers") or {}
        if not isinstance(providers, dict):
            continue
        ref = providers.get("provider_ref") or providers.get("providerRef")
        if ref == provider_id:
            out.append(agent_id)
    return out
