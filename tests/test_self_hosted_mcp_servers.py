"""Tests for the self-hosted MCP servers feature.

Covers:
- :class:`YamlMCPRegistry` — tagging, query matching, CRUD.
- Self-hosted catalog merging with the official ``registry.modelcontextprotocol.io`` search.
"""

import threading
from pathlib import Path

import pytest
import yaml

from clawlib.mcpregistry import OfficialMCPRegistry, YamlMCPRegistry


class _StubOfficialMCPRegistry(OfficialMCPRegistry):
    """Stub that returns canned search results without touching the network."""

    def __init__(
        self,
        results: list[dict] | None = None,
        detail: dict | None = None,
    ) -> None:
        # Skip OfficialMCPRegistry.__init__ to avoid creating a real HTTP client.
        self._results = results or []
        self._detail = detail

    async def search_mcp_servers(self, query: str, limit: int) -> list[dict]:
        return list(self._results)[:limit]

    async def get_mcp_server(self, slug: str) -> dict | None:
        return dict(self._detail) if self._detail else None


def _write_yaml(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")


@pytest.fixture
def sample_custom_entry() -> dict:
    return {
        "slug": "my-internal-mcp",
        "name": "Internal MCP",
        "description": "Local Postgres bridge",
        "author": "Platform Team",
        "version": "1.0.0",
        "categories": ["data"],
        "homepage": "",
        "repository": "",
        "required_env": ["DATABASE_URL"],
        "install_config": {"command": "uvx", "args": ["my-internal-mcp"]},
    }


class TestYamlMCPRegistrySearch:
    @pytest.mark.asyncio
    async def test_search_merges_and_tags_source(self, tmp_path: Path, sample_custom_entry: dict):
        custom_path = tmp_path / "custom_mcp.yaml"
        _write_yaml(custom_path, [sample_custom_entry])
        inner = _StubOfficialMCPRegistry(
            results=[{"id": "io.acme/foo", "name": "Foo", "description": "", "downloads": 5}]
        )
        reg = YamlMCPRegistry(custom_catalog_path=custom_path, inner=inner)

        results = await reg.search_mcp_servers("", limit=20)

        assert results[0]["source"] == "self-hosted"
        assert results[0]["slug"] == "my-internal-mcp"
        # The install_config and required_env must be preserved for the install modal.
        assert results[0]["install_config"] == {"command": "uvx", "args": ["my-internal-mcp"]}
        assert results[0]["required_env"] == ["DATABASE_URL"]
        assert results[1]["source"] == "official"
        assert results[1]["id"] == "io.acme/foo"

    @pytest.mark.asyncio
    async def test_search_filters_custom_by_query(self, tmp_path: Path, sample_custom_entry: dict):
        other = {
            **sample_custom_entry,
            "slug": "other",
            "name": "Other",
            "description": "Unrelated",
        }
        custom_path = tmp_path / "custom_mcp.yaml"
        _write_yaml(custom_path, [sample_custom_entry, other])
        inner = _StubOfficialMCPRegistry(results=[])
        reg = YamlMCPRegistry(custom_catalog_path=custom_path, inner=inner)

        results = await reg.search_mcp_servers("postgres", limit=20)
        slugs = [r["slug"] for r in results]
        assert "my-internal-mcp" in slugs
        assert "other" not in slugs

    @pytest.mark.asyncio
    async def test_search_survives_remote_failure(self, tmp_path: Path, sample_custom_entry: dict):
        custom_path = tmp_path / "custom_mcp.yaml"
        _write_yaml(custom_path, [sample_custom_entry])

        class _BrokenInner(_StubOfficialMCPRegistry):
            async def search_mcp_servers(self, query: str, limit: int) -> list[dict]:
                raise RuntimeError("network down")

        reg = YamlMCPRegistry(custom_catalog_path=custom_path, inner=_BrokenInner())
        results = await reg.search_mcp_servers("", limit=20)
        assert [r["slug"] for r in results] == ["my-internal-mcp"]


class TestYamlMCPRegistryGet:
    @pytest.mark.asyncio
    async def test_get_returns_self_hosted_entry(self, tmp_path: Path, sample_custom_entry: dict):
        custom_path = tmp_path / "custom_mcp.yaml"
        _write_yaml(custom_path, [sample_custom_entry])
        inner = _StubOfficialMCPRegistry()
        reg = YamlMCPRegistry(custom_catalog_path=custom_path, inner=inner)

        got = await reg.get_mcp_server("my-internal-mcp")
        assert got is not None
        assert got["source"] == "self-hosted"
        assert got["install_config"] == {"command": "uvx", "args": ["my-internal-mcp"]}
        assert got["required_env"] == ["DATABASE_URL"]

    @pytest.mark.asyncio
    async def test_get_falls_through_to_official(self, tmp_path: Path):
        custom_path = tmp_path / "custom_mcp.yaml"
        _write_yaml(custom_path, [])
        inner = _StubOfficialMCPRegistry(
            detail={"id": "io.acme/foo", "name": "Foo", "description": ""}
        )
        reg = YamlMCPRegistry(custom_catalog_path=custom_path, inner=inner)

        got = await reg.get_mcp_server("io.acme/foo")
        assert got is not None
        assert got["id"] == "io.acme/foo"
        assert got["source"] == "official"

    @pytest.mark.asyncio
    async def test_get_returns_none_for_unknown(self, tmp_path: Path):
        custom_path = tmp_path / "custom_mcp.yaml"
        _write_yaml(custom_path, [])
        inner = _StubOfficialMCPRegistry(detail=None)
        reg = YamlMCPRegistry(custom_catalog_path=custom_path, inner=inner)

        assert await reg.get_mcp_server("nope") is None


class TestYamlMCPRegistryCrud:
    def test_add_get_update_delete(self, tmp_path: Path, sample_custom_entry: dict):
        custom_path = tmp_path / "custom_mcp.yaml"
        reg = YamlMCPRegistry(custom_catalog_path=custom_path)

        reg.add_custom_entry(sample_custom_entry)
        assert reg.get_entry("my-internal-mcp") is not None
        assert [e["slug"] for e in reg.list_custom_entries()] == ["my-internal-mcp"]

        updated = {**sample_custom_entry, "name": "Internal MCP v2"}
        assert reg.update_custom_entry("my-internal-mcp", updated)
        assert reg.get_entry("my-internal-mcp")["name"] == "Internal MCP v2"

        assert reg.delete_custom_entry("my-internal-mcp") is True
        assert reg.get_entry("my-internal-mcp") is None

    def test_missing_catalog_returns_empty(self, tmp_path: Path):
        reg = YamlMCPRegistry(custom_catalog_path=tmp_path / "nope.yaml")
        assert reg.list_custom_entries() == []
        assert reg.get_entry("anything") is None

    def test_update_missing_returns_false(self, tmp_path: Path):
        custom_path = tmp_path / "custom_mcp.yaml"
        _write_yaml(custom_path, [])
        reg = YamlMCPRegistry(custom_catalog_path=custom_path)
        assert reg.update_custom_entry("nope", {"slug": "nope", "name": "N"}) is False
        assert reg.delete_custom_entry("nope") is False

    def test_add_without_custom_path_raises(self):
        reg = YamlMCPRegistry(custom_catalog_path=None)
        with pytest.raises(RuntimeError):
            reg.add_custom_entry({"slug": "x", "name": "X"})


class TestYamlMCPRegistryHardening:
    """Regression tests for defensive guards against malformed catalogs."""

    def test_loader_filters_non_dict_entries(self, tmp_path: Path):
        path = tmp_path / "custom_mcp.yaml"
        path.write_text(
            yaml.dump(
                [
                    {"slug": "good", "name": "Good"},
                    "oops-a-string",
                    42,
                    {"slug": "also-good", "name": "Also"},
                ],
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        reg = YamlMCPRegistry(custom_catalog_path=path)
        entries = reg.list_custom_entries()
        assert [e["slug"] for e in entries] == ["good", "also-good"]
        assert reg.get_entry("good") is not None
        assert reg.get_entry("missing") is None

    @pytest.mark.asyncio
    async def test_search_tolerates_non_dict_entries(self, tmp_path: Path):
        path = tmp_path / "custom_mcp.yaml"
        path.write_text(
            yaml.dump([{"slug": "ok", "name": "OK"}, "junk"], sort_keys=False),
            encoding="utf-8",
        )
        reg = YamlMCPRegistry(custom_catalog_path=path, inner=_StubOfficialMCPRegistry())
        results = await reg.search_mcp_servers("", limit=10)
        assert [r["slug"] for r in results] == ["ok"]

    def test_mutators_are_thread_safe(self, tmp_path: Path):
        """Concurrent adds should not lose entries thanks to the per-instance lock."""
        path = tmp_path / "custom_mcp.yaml"
        reg = YamlMCPRegistry(custom_catalog_path=path)

        def add(i: int) -> None:
            reg.add_custom_entry(
                {
                    "slug": f"s{i}",
                    "name": f"n{i}",
                    "install_config": {"command": "echo", "args": []},
                }
            )

        threads = [threading.Thread(target=add, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        slugs = sorted(e["slug"] for e in reg.list_custom_entries())
        assert slugs == sorted(f"s{i}" for i in range(20))
