"""ApiToolRegistry implementation merging the bundled catalog with user custom entries.

Each entry describes one OpenAPI/Swagger/Postman spec: ``id``, ``name``,
``spec_url``, header template (with ``${VAR}`` placeholders), and a
list of ``required_env`` keys the user must supply before installing.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_PATH = _ROOT / "marketplace" / "api-tools" / "catalog.yaml"


def _load_yaml_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to load API-tool catalog at %s: %s", path, exc)
        return []
    if not isinstance(data, list):
        logger.warning("API-tool catalog at %s is not a list", path)
        return []
    return [item for item in data if isinstance(item, dict)]


def _atomic_write_yaml(path: Path, data: list[dict[str, Any]]) -> None:
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


def _matches_query(entry: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    needle = query.lower()
    haystack = [
        str(entry.get("name", "")),
        str(entry.get("description", "")),
        str(entry.get("author", "")),
        str(entry.get("id", "")),
    ]
    haystack.extend(str(c) for c in (entry.get("categories") or []))
    return any(needle in part.lower() for part in haystack)


class YamlApiToolRegistry:
    """Bundled catalog + custom YAML overlay; same shape as Software registry."""

    def __init__(
        self,
        catalog_path: Path | None = None,
        custom_catalog_path: Path | None = None,
    ) -> None:
        self._catalog_path = catalog_path or _CATALOG_PATH
        self._custom_catalog_path = custom_catalog_path
        self._lock = threading.Lock()

    def list_entries(self) -> list[dict[str, Any]]:
        """Bundled + custom merged. Custom ids do NOT override bundled — they coexist
        because the custom catalog is treated as an "additions" list. Same id wins
        the bundled one (custom skipped) so users can't accidentally shadow defaults."""
        bundled = [{**e, "source": "bundled"} for e in _load_yaml_list(self._catalog_path)]
        custom = [{**e, "source": "self-hosted"} for e in self.list_custom_entries()]
        bundled_ids = {e.get("id") for e in bundled}
        merged = list(bundled)
        for entry in custom:
            if entry.get("id") not in bundled_ids:
                merged.append(entry)
        return merged

    def search(self, query: str = "", limit: int = 50) -> list[dict[str, Any]]:
        """Filter list_entries by query against name/description/author/categories."""
        return [e for e in self.list_entries() if _matches_query(e, query)][:limit]

    def list_custom_entries(self) -> list[dict[str, Any]]:
        if not self._custom_catalog_path:
            return []
        return _load_yaml_list(self._custom_catalog_path)

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        for entry in self.list_entries():
            if entry.get("id") == entry_id:
                return entry
        return None

    def add_custom_entry(self, entry: dict[str, Any]) -> None:
        if not self._custom_catalog_path:
            raise RuntimeError("No custom catalog path configured")
        with self._lock:
            existing = _load_yaml_list(self._custom_catalog_path)
            if any(e.get("id") == entry.get("id") for e in existing):
                raise ValueError(f"API tool '{entry.get('id')}' already exists")
            existing.append(entry)
            _atomic_write_yaml(self._custom_catalog_path, existing)

    def update_custom_entry(self, entry_id: str, entry: dict[str, Any]) -> bool:
        if not self._custom_catalog_path:
            return False
        with self._lock:
            existing = _load_yaml_list(self._custom_catalog_path)
            for i, e in enumerate(existing):
                if e.get("id") == entry_id:
                    existing[i] = {**e, **entry, "id": entry_id}
                    _atomic_write_yaml(self._custom_catalog_path, existing)
                    return True
            return False

    def delete_custom_entry(self, entry_id: str) -> bool:
        if not self._custom_catalog_path:
            return False
        with self._lock:
            existing = _load_yaml_list(self._custom_catalog_path)
            filtered = [e for e in existing if e.get("id") != entry_id]
            if len(filtered) == len(existing):
                return False
            _atomic_write_yaml(self._custom_catalog_path, filtered)
            return True


__all__ = ["YamlApiToolRegistry"]
