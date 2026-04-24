"""Resolve an agent config's provider_ref against the admin LLMProviderStore.

Agents reference a centrally-managed provider by id in
``config["providers"]["provider_ref"]``. Before the config is handed to the
worker (either on WebSocket bootstrap in ``apis/control.py`` or on hot-reload
via ``runtime.apply_config``), the control plane looks up that row and writes
the resolved credentials into ``config["providers"][<type>]`` so the worker
code keeps reading the same ``ProviderConfig`` fields as before.
"""

from __future__ import annotations

from typing import Any

from specops.core.store.llm_providers import LLMProviderStore


def resolve_provider_ref(config: dict[str, Any], store: LLMProviderStore) -> dict[str, Any]:
    """Return a new config dict with ``provider_ref`` resolved into per-type creds.

    No-op when ``providers.provider_ref`` is missing or empty. The returned dict
    keeps ``provider_ref`` so the UI can round-trip the selection.
    """
    if not isinstance(config, dict):
        return config
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return config
    ref = providers.get("provider_ref") or providers.get("providerRef")
    if not ref:
        return config

    entry = store.get(str(ref), with_secrets=True)
    if not entry:
        return config

    provider_type = entry.get("type") or ""
    if not provider_type:
        return config

    # The provider row is authoritative — fully overwrite the slot so any stale
    # inline api_base / extra_headers from a prior config are cleared.
    merged_slot: dict[str, Any] = {"api_key": entry.get("api_key") or ""}
    api_base = entry.get("api_base")
    if api_base:
        merged_slot["api_base"] = api_base
    extra_headers = entry.get("extra_headers")
    if extra_headers:
        merged_slot["extra_headers"] = extra_headers

    new_providers = dict(providers)
    new_providers[provider_type] = merged_slot

    new_config = dict(config)
    new_config["providers"] = new_providers
    return new_config
