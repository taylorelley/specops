"""PlanTemplateRegistry implementation using marketplace YAML catalog."""

import logging
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


class YamlPlanTemplateRegistry:
    """PlanTemplateRegistry implementation loading from marketplace YAML catalog.

    Merges the bundled catalog with an optional user-managed custom catalog.
    Custom entries with the same id override bundled ones.
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
        """Append a new entry to the custom catalog YAML file."""
        if not self._custom_catalog_path:
            raise RuntimeError("No custom catalog path configured")
        existing = _load_yaml_list(self._custom_catalog_path)
        existing.append(entry)
        self._custom_catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self._custom_catalog_path.write_text(
            yaml.dump(existing, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def update_custom_entry(self, template_id: str, entry: dict[str, Any]) -> bool:
        """Update an existing custom entry by id. Returns True if it was found and updated."""
        if not self._custom_catalog_path:
            return False
        existing = _load_yaml_list(self._custom_catalog_path)
        for i, e in enumerate(existing):
            if e.get("id") == template_id:
                existing[i] = {**e, **entry, "id": template_id}
                self._custom_catalog_path.write_text(
                    yaml.dump(existing, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
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
        self._custom_catalog_path.write_text(
            yaml.dump(filtered, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return True

    def get_entry(self, template_id: str) -> dict[str, Any] | None:
        """Return a single catalog entry by id, or None if not found."""
        for entry in self.list_entries():
            if entry.get("id") == template_id:
                return entry
        return None
