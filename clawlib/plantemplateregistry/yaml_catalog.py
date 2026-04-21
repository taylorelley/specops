"""PlanTemplateRegistry implementation using marketplace YAML catalog."""

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
_CATALOG_PATH = _ROOT / "marketplace" / "plan-templates" / "catalog.yaml"


def _load_yaml_list(path: Path) -> list[dict[str, Any]]:
    """Load a YAML file expected to contain a list of dicts. Returns [] on any error."""
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if not isinstance(data, list):
            logger.warning("Plan template catalog at %s is not a list", path)
            return []
        return data
    except (yaml.YAMLError, OSError) as e:
        logger.warning("Failed to load plan template catalog at %s: %s", path, e)
        return []


def _atomic_write_yaml(path: Path, data: list[dict[str, Any]]) -> None:
    """Write YAML atomically: temp file in the same directory, fsync, then os.replace.

    Avoids leaving a truncated catalog on crash.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.dump(data, allow_unicode=True, sort_keys=False)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
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


class YamlPlanTemplateRegistry:
    """:class:`PlanTemplateRegistry` implementation loading from marketplace YAML catalogs.

    Merges the bundled catalog with an optional user-managed custom catalog.
    **Bundled entries win on id collisions**: :meth:`list_entries` appends a
    custom entry only when its id is not already in the bundled catalog, so a
    custom entry cannot shadow a bundled one — picking a colliding id via
    :meth:`add_custom_entry` silently leaves the bundled entry in the merged
    listing.
    """

    def __init__(
        self,
        catalog_path: Path | None = None,
        custom_catalog_path: Path | None = None,
    ) -> None:
        self._catalog_path = catalog_path or _CATALOG_PATH
        self._custom_catalog_path = custom_catalog_path

    def list_entries(self) -> list[dict[str, Any]]:
        """Return all catalog entries (bundled + custom). Custom entries are appended last."""
        bundled = _load_yaml_list(self._catalog_path)
        if not self._custom_catalog_path:
            return bundled
        custom = _load_yaml_list(self._custom_catalog_path)
        bundled_ids = {e.get("id") for e in bundled}
        merged = list(bundled)
        for entry in custom:
            if entry.get("id") not in bundled_ids:
                merged.append(entry)
        return merged

    def list_custom_entries(self) -> list[dict[str, Any]]:
        """Return only the user-managed custom entries."""
        if not self._custom_catalog_path:
            return []
        return _load_yaml_list(self._custom_catalog_path)

    def add_custom_entry(self, entry: dict[str, Any]) -> None:
        """Append a new entry to the custom catalog YAML file (atomic replace)."""
        if not self._custom_catalog_path:
            raise RuntimeError("No custom catalog path configured")
        existing = _load_yaml_list(self._custom_catalog_path)
        existing.append(entry)
        _atomic_write_yaml(self._custom_catalog_path, existing)

    def update_custom_entry(self, template_id: str, entry: dict[str, Any]) -> bool:
        """Update an existing custom entry by id. Returns True if it was found and updated."""
        if not self._custom_catalog_path:
            return False
        existing = _load_yaml_list(self._custom_catalog_path)
        for i, e in enumerate(existing):
            if e.get("id") == template_id:
                existing[i] = {**e, **entry, "id": template_id}
                _atomic_write_yaml(self._custom_catalog_path, existing)
                return True
        return False

    def delete_custom_entry(self, template_id: str) -> bool:
        """Remove a custom entry by id. Returns True if it was found and removed."""
        if not self._custom_catalog_path:
            return False
        existing = _load_yaml_list(self._custom_catalog_path)
        filtered = [e for e in existing if e.get("id") != template_id]
        if len(filtered) == len(existing):
            return False
        _atomic_write_yaml(self._custom_catalog_path, filtered)
        return True

    def get_entry(self, template_id: str) -> dict[str, Any] | None:
        """Return a single catalog entry by id, or None if not found."""
        for entry in self.list_entries():
            if entry.get("id") == template_id:
                return entry
        return None
