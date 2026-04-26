"""Tests for the YamlApiToolRegistry: bundled+custom merge, search, CRUD."""

from pathlib import Path

import pytest
import yaml

from specops_lib.apitoolregistry import YamlApiToolRegistry


@pytest.fixture
def bundled_path(tmp_path: Path) -> Path:
    p = tmp_path / "bundled.yaml"
    p.write_text(
        yaml.dump(
            [
                {
                    "id": "stripe",
                    "name": "Stripe",
                    "description": "Payments API",
                    "spec_url": "https://example.com/stripe.json",
                    "categories": ["payments"],
                },
                {
                    "id": "github",
                    "name": "GitHub",
                    "description": "Source control API",
                    "spec_url": "https://example.com/github.json",
                    "categories": ["devtools"],
                },
            ]
        )
    )
    return p


@pytest.fixture
def custom_path(tmp_path: Path) -> Path:
    return tmp_path / "custom.yaml"


@pytest.fixture
def registry(bundled_path: Path, custom_path: Path) -> YamlApiToolRegistry:
    return YamlApiToolRegistry(catalog_path=bundled_path, custom_catalog_path=custom_path)


class TestListSearch:
    def test_lists_bundled_with_source(self, registry: YamlApiToolRegistry) -> None:
        entries = registry.list_entries()
        assert {e["id"] for e in entries} == {"stripe", "github"}
        assert all(e["source"] == "bundled" for e in entries)

    def test_search_by_name(self, registry: YamlApiToolRegistry) -> None:
        results = registry.search("stripe", limit=10)
        assert len(results) == 1
        assert results[0]["id"] == "stripe"

    def test_search_by_category(self, registry: YamlApiToolRegistry) -> None:
        results = registry.search("payments", limit=10)
        assert {r["id"] for r in results} == {"stripe"}

    def test_empty_query_returns_all(self, registry: YamlApiToolRegistry) -> None:
        results = registry.search("", limit=10)
        assert len(results) == 2


class TestCustomCRUD:
    def test_add_custom(self, registry: YamlApiToolRegistry) -> None:
        registry.add_custom_entry(
            {
                "id": "internal",
                "name": "Internal API",
                "description": "Custom",
                "spec_url": "https://internal.example.com/api.json",
                "categories": [],
            }
        )
        entries = registry.list_entries()
        assert {e["id"] for e in entries} == {"stripe", "github", "internal"}
        custom = next(e for e in entries if e["id"] == "internal")
        assert custom["source"] == "self-hosted"

    def test_duplicate_id_rejected(self, registry: YamlApiToolRegistry) -> None:
        registry.add_custom_entry({"id": "internal", "name": "x", "spec_url": "https://x"})
        with pytest.raises(ValueError):
            registry.add_custom_entry({"id": "internal", "name": "y", "spec_url": "https://y"})

    def test_bundled_id_not_overridden(self, registry: YamlApiToolRegistry) -> None:
        """A custom entry with the same id as a bundled one must not shadow defaults."""
        # add_custom_entry succeeds (no id collision in custom file alone) ...
        registry.add_custom_entry(
            {"id": "stripe", "name": "Custom Stripe", "spec_url": "https://x"}
        )
        # ... but list_entries keeps the bundled version.
        entries = registry.list_entries()
        stripe = next(e for e in entries if e["id"] == "stripe")
        assert stripe["name"] == "Stripe"
        assert stripe["source"] == "bundled"

    def test_update_custom(self, registry: YamlApiToolRegistry) -> None:
        registry.add_custom_entry({"id": "internal", "name": "Old", "spec_url": "https://x"})
        assert registry.update_custom_entry(
            "internal",
            {"id": "internal", "name": "New", "spec_url": "https://x"},
        )
        entry = registry.get_entry("internal")
        assert entry is not None and entry["name"] == "New"

    def test_update_missing_returns_false(self, registry: YamlApiToolRegistry) -> None:
        assert registry.update_custom_entry("missing", {"id": "missing", "spec_url": "x"}) is False

    def test_delete_custom(self, registry: YamlApiToolRegistry) -> None:
        registry.add_custom_entry({"id": "internal", "name": "x", "spec_url": "https://x"})
        assert registry.delete_custom_entry("internal")
        assert registry.get_entry("internal") is None

    def test_delete_missing_returns_false(self, registry: YamlApiToolRegistry) -> None:
        assert registry.delete_custom_entry("nope") is False

    def test_get_entry_finds_bundled_or_custom(self, registry: YamlApiToolRegistry) -> None:
        assert registry.get_entry("stripe") is not None
        assert registry.get_entry("missing") is None
