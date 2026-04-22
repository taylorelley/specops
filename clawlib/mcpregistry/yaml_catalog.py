"""MCPRegistry implementation that merges the official registry with self-hosted entries.

Self-hosted MCP servers are admin-managed entries stored in a YAML catalog. Each entry
carries its own ``install_config`` (either ``{"command": ..., "args": [...]}`` or
``{"url": ...}``) which the install flow uses verbatim — no ``registry.modelcontextprotocol.io``
call is made for self-hosted slugs.
"""

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml

from clawlib.mcpregistry.official_mcp import OfficialMCPRegistry

logger = logging.getLogger(__name__)


def _load_yaml_list(path: Path) -> list[dict[str, Any]]:
    """Load a YAML file expected to contain a list of dicts.

    Non-dict entries are silently dropped so downstream ``entry.get(...)`` calls
    don't crash; a warning is emitted listing the skipped items.
    """
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to load custom MCP servers catalog at %s: %s", path, e)
        return []
    if not isinstance(data, list):
        logger.warning("Custom MCP servers catalog at %s is not a list", path)
        return []
    cleaned: list[dict[str, Any]] = []
    skipped: list[Any] = []
    for item in data:
        if isinstance(item, dict):
            cleaned.append(item)
        else:
            skipped.append(item)
    if skipped:
        logger.warning(
            "Custom MCP servers catalog at %s: skipped %d non-dict entries (e.g. %r)",
            path,
            len(skipped),
            skipped[:3],
        )
    return cleaned


def _atomic_write_yaml(path: Path, data: list[dict[str, Any]]) -> None:
    """Write YAML atomically via a temp file in the same directory, fsync, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.dump(data, allow_unicode=True, sort_keys=False)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(serialized)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Shape a self-hosted catalog entry to match the MCPRegistryServer wire shape."""
    slug = entry.get("slug", "")
    return {
        "id": slug,
        "slug": slug,
        "name": entry.get("name", slug),
        "description": entry.get("description", ""),
        "repository": entry.get("repository", ""),
        "homepage": entry.get("homepage", ""),
        "version": entry.get("version", ""),
        "license": entry.get("license", ""),
        "author": entry.get("author", ""),
        "verified": False,
        "is_verified": False,
        "downloads": 0,
        "created_at": "",
        "updated_at": "",
        "categories": entry.get("categories") or [],
        "capabilities": [],
        "install_config": entry.get("install_config") or {},
        "config_schema": [],
        "required_env": entry.get("required_env") or [],
        "source": "self-hosted",
    }


def _matches_query(entry: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    needle = query.lower()
    haystack_parts = [
        str(entry.get("name", "")),
        str(entry.get("description", "")),
        str(entry.get("author", "")),
        str(entry.get("slug", "")),
    ]
    haystack_parts.extend(str(c) for c in (entry.get("categories") or []))
    return any(needle in part.lower() for part in haystack_parts)


class YamlMCPRegistry:
    """MCPRegistry that wraps :class:`OfficialMCPRegistry` and merges a self-hosted YAML catalog.

    Self-hosted entries are surfaced in :meth:`search_mcp_servers` tagged with
    ``source="self-hosted"``; official registry results are tagged
    ``source="official"``. :meth:`get_mcp_server` resolves self-hosted slugs from
    the catalog and delegates everything else to the inner registry.
    """

    def __init__(
        self,
        custom_catalog_path: Path | None = None,
        inner: OfficialMCPRegistry | None = None,
    ) -> None:
        self._custom_catalog_path = custom_catalog_path
        self._inner = inner or OfficialMCPRegistry()
        # Serializes the read-modify-write sequence in the mutator methods so
        # concurrent callers can't interleave load + mutate + atomic-write.
        self._catalog_lock = threading.Lock()

    # -- Search ---------------------------------------------------------------

    async def search_mcp_servers(self, query: str, limit: int) -> list[dict]:
        """Merge self-hosted entries into the official registry search results.

        Self-hosted entries that match ``query`` are listed first (followed by
        remote results), each tagged with a ``source`` field. ``limit`` applies
        to the combined result count.
        """
        query = (query or "").strip()
        custom = self.list_custom_entries()
        custom_matches = [_public_entry(entry) for entry in custom if _matches_query(entry, query)]

        remaining = max(0, limit - len(custom_matches))
        remote: list[dict] = []
        if remaining > 0:
            try:
                remote = await self._inner.search_mcp_servers(query, remaining)
            except Exception:
                logger.exception("Official MCP registry search failed; returning self-hosted only")
                remote = []
            for entry in remote:
                entry["source"] = "official"

        return [*custom_matches, *remote][:limit]

    # -- Details --------------------------------------------------------------

    async def get_mcp_server(self, slug: str) -> dict | None:
        """Return a self-hosted or official MCP server by slug."""
        entry = self.get_entry(slug)
        if entry is not None:
            return _public_entry(entry)
        remote = await self._inner.get_mcp_server(slug)
        if remote is None:
            return None
        remote["source"] = "official"
        return remote

    # -- Custom CRUD ----------------------------------------------------------

    def list_custom_entries(self) -> list[dict[str, Any]]:
        """Return raw self-hosted catalog entries (including stored install_config)."""
        if not self._custom_catalog_path:
            return []
        return _load_yaml_list(self._custom_catalog_path)

    def get_entry(self, slug: str) -> dict[str, Any] | None:
        """Return a self-hosted catalog entry by slug, or None if not found."""
        for entry in self.list_custom_entries():
            if entry.get("slug") == slug:
                return entry
        return None

    def add_custom_entry(self, entry: dict[str, Any]) -> None:
        """Append a new entry to the custom catalog YAML file."""
        if not self._custom_catalog_path:
            raise RuntimeError("No custom catalog path configured")
        with self._catalog_lock:
            existing = _load_yaml_list(self._custom_catalog_path)
            existing.append(entry)
            _atomic_write_yaml(self._custom_catalog_path, existing)

    def update_custom_entry(self, slug: str, entry: dict[str, Any]) -> bool:
        """Update an existing custom entry by slug. Returns True if found and updated."""
        if not self._custom_catalog_path:
            return False
        with self._catalog_lock:
            existing = _load_yaml_list(self._custom_catalog_path)
            for i, e in enumerate(existing):
                if e.get("slug") == slug:
                    existing[i] = {**e, **entry, "slug": slug}
                    _atomic_write_yaml(self._custom_catalog_path, existing)
                    return True
            return False

    def delete_custom_entry(self, slug: str) -> bool:
        """Remove a custom entry by slug. Returns True if it was found and removed."""
        if not self._custom_catalog_path:
            return False
        with self._catalog_lock:
            existing = _load_yaml_list(self._custom_catalog_path)
            filtered = [e for e in existing if e.get("slug") != slug]
            if len(filtered) == len(existing):
                return False
            _atomic_write_yaml(self._custom_catalog_path, filtered)
            return True
