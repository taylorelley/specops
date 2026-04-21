"""Tests for the self-hosted skills feature.

Covers:
- :class:`YamlSkillRegistry` — tagging, query matching, install routing, CRUD.
- Self-hosted catalog merging with the remote ``agentskill.sh`` search results.
"""

import threading
from pathlib import Path

import pytest
import yaml

from clawbot.agent.agent_fs import AgentFS
from clawbot.worker.handlers.schema import InstallSkillRequest
from clawbot.worker.handlers.skill import handle_install_skill
from clawlib.skillregistry import YamlSkillRegistry
from clawlib.skillregistry.skills_sh import SkillsShRegistry


class _StubSkillsShRegistry(SkillsShRegistry):
    """Stub that returns canned search results and records install calls."""

    def __init__(self, results: list[dict] | None = None) -> None:
        self._results = results or []
        self.install_calls: list[tuple[str, Path, dict | None]] = []

    async def search_skills(self, query: str, limit: int) -> list[dict]:
        return list(self._results)[:limit]

    async def install_skill(
        self,
        slug: str,
        dest: Path,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        self.install_calls.append((slug, dest, env))
        return 0, "delegated", ""


def _write_yaml(path: Path, data: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")


@pytest.fixture
def sample_custom_entry() -> dict:
    return {
        "slug": "my-pdf-helper",
        "name": "PDF Helper",
        "description": "Internal PDF utilities",
        "author": "Platform Team",
        "version": "1.0.0",
        "categories": ["docs"],
        "homepage": "",
        "repository": "",
        "required_env": [],
        "skill_content": (
            "---\n"
            "name: pdf-helper\n"
            "description: Internal PDF utilities\n"
            "---\n\n"
            "# PDF Helper\n\n"
            "Handles PDFs.\n"
        ),
    }


class TestYamlSkillRegistrySearch:
    @pytest.mark.asyncio
    async def test_search_merges_and_tags_source(self, tmp_path: Path, sample_custom_entry: dict):
        custom_path = tmp_path / "custom_skills.yaml"
        _write_yaml(custom_path, [sample_custom_entry])
        inner = _StubSkillsShRegistry(
            results=[{"slug": "acme/foo@bar", "name": "Foo", "description": "", "downloads": 5}]
        )
        reg = YamlSkillRegistry(custom_catalog_path=custom_path, inner=inner)

        results = await reg.search_skills("", limit=20)

        # Self-hosted entries appear first and are tagged; remote entries also tagged.
        assert results[0]["source"] == "self-hosted"
        assert results[0]["slug"] == "my-pdf-helper"
        # The raw skill_content must not leak to search results — it can be large.
        assert "skill_content" not in results[0]
        assert results[1]["source"] == "agentskill.sh"
        assert results[1]["slug"] == "acme/foo@bar"

    @pytest.mark.asyncio
    async def test_search_filters_custom_by_query(self, tmp_path: Path, sample_custom_entry: dict):
        other = {
            **sample_custom_entry,
            "slug": "other",
            "name": "Other",
            "description": "Spreadsheets",
        }
        custom_path = tmp_path / "custom_skills.yaml"
        _write_yaml(custom_path, [sample_custom_entry, other])
        inner = _StubSkillsShRegistry(results=[])
        reg = YamlSkillRegistry(custom_catalog_path=custom_path, inner=inner)

        results = await reg.search_skills("pdf", limit=20)
        slugs = [r["slug"] for r in results]
        assert "my-pdf-helper" in slugs
        assert "other" not in slugs

    @pytest.mark.asyncio
    async def test_search_survives_remote_failure(self, tmp_path: Path, sample_custom_entry: dict):
        custom_path = tmp_path / "custom_skills.yaml"
        _write_yaml(custom_path, [sample_custom_entry])

        class _BrokenInner(SkillsShRegistry):
            async def search_skills(self, query: str, limit: int) -> list[dict]:
                raise RuntimeError("network down")

            async def install_skill(self, slug: str, dest: Path, env=None):
                return 0, "", ""

        reg = YamlSkillRegistry(custom_catalog_path=custom_path, inner=_BrokenInner())
        results = await reg.search_skills("", limit=20)
        assert [r["slug"] for r in results] == ["my-pdf-helper"]


class TestYamlSkillRegistryInstall:
    @pytest.mark.asyncio
    async def test_install_self_hosted_writes_skill_md(
        self, tmp_path: Path, sample_custom_entry: dict
    ):
        custom_path = tmp_path / "custom_skills.yaml"
        _write_yaml(custom_path, [sample_custom_entry])
        inner = _StubSkillsShRegistry()
        reg = YamlSkillRegistry(custom_catalog_path=custom_path, inner=inner)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        rc, stdout, stderr = await reg.install_skill("my-pdf-helper", workspace)

        assert rc == 0
        assert stderr == ""
        skill_file = workspace / ".agents" / "skills" / "my-pdf-helper" / "SKILL.md"
        assert skill_file.exists()
        assert skill_file.read_text() == sample_custom_entry["skill_content"]
        assert inner.install_calls == []  # did not delegate

    @pytest.mark.asyncio
    async def test_install_non_custom_delegates_to_inner(self, tmp_path: Path):
        custom_path = tmp_path / "custom_skills.yaml"
        _write_yaml(custom_path, [])
        inner = _StubSkillsShRegistry()
        reg = YamlSkillRegistry(custom_catalog_path=custom_path, inner=inner)

        rc, stdout, stderr = await reg.install_skill("acme/foo@bar", tmp_path)
        assert rc == 0
        assert stdout == "delegated"
        assert len(inner.install_calls) == 1
        assert inner.install_calls[0][0] == "acme/foo@bar"


class TestYamlSkillRegistryCrud:
    def test_add_get_update_delete(self, tmp_path: Path, sample_custom_entry: dict):
        custom_path = tmp_path / "custom_skills.yaml"
        reg = YamlSkillRegistry(custom_catalog_path=custom_path)

        reg.add_custom_entry(sample_custom_entry)
        assert reg.get_entry("my-pdf-helper") is not None
        assert [e["slug"] for e in reg.list_custom_entries()] == ["my-pdf-helper"]

        updated = {**sample_custom_entry, "name": "PDF Helper 2"}
        assert reg.update_custom_entry("my-pdf-helper", updated)
        assert reg.get_entry("my-pdf-helper")["name"] == "PDF Helper 2"

        assert reg.delete_custom_entry("my-pdf-helper") is True
        assert reg.get_entry("my-pdf-helper") is None

    def test_missing_catalog_returns_empty(self, tmp_path: Path):
        reg = YamlSkillRegistry(custom_catalog_path=tmp_path / "nope.yaml")
        assert reg.list_custom_entries() == []
        assert reg.get_entry("anything") is None

    def test_update_missing_returns_false(self, tmp_path: Path):
        custom_path = tmp_path / "custom_skills.yaml"
        _write_yaml(custom_path, [])
        reg = YamlSkillRegistry(custom_catalog_path=custom_path)
        assert reg.update_custom_entry("nope", {"slug": "nope", "name": "N"}) is False
        assert reg.delete_custom_entry("nope") is False

    def test_add_without_custom_path_raises(self):
        reg = YamlSkillRegistry(custom_catalog_path=None)
        with pytest.raises(RuntimeError):
            reg.add_custom_entry({"slug": "x", "name": "X"})


class TestWorkerHandlerSanitization:
    """Regression tests for path-traversal hardening in the worker install handler."""

    @pytest.mark.asyncio
    async def test_install_rejects_traversal_via_at_slug(self, tmp_path: Path):
        fs = AgentFS(tmp_path)
        req = InstallSkillRequest(
            slug="evil@../../outside",
            skill_content="---\nname: x\ndescription: y\n---\n",
        )
        result = await handle_install_skill(fs, req)

        # The install must have stayed inside .agents/skills/.
        skills_root = (fs.workspace_path / ".agents" / "skills").resolve()
        written = skills_root / result["data"]["slug"]
        assert written.resolve().is_relative_to(skills_root)
        # And must not have escaped to a sibling of the workspace.
        assert not (tmp_path / "outside").exists()

    @pytest.mark.asyncio
    async def test_install_rejects_dotdot_name(self, tmp_path: Path):
        fs = AgentFS(tmp_path)
        # A bare ".." slug: _slug_to_skill_name returns "_._._" after replaces, but
        # a slug ending in "@.." would yield "..". The sanitizer must neutralize it.
        req = InstallSkillRequest(
            slug="foo@..",
            skill_content="---\nname: x\ndescription: y\n---\n",
        )
        result = await handle_install_skill(fs, req)
        assert result["data"]["slug"] == "skill"
        assert (fs.workspace_path / ".agents" / "skills" / "skill" / "SKILL.md").exists()


class TestYamlSkillRegistryHardening:
    """Regression tests for the defensive guards added during code review."""

    def test_loader_filters_non_dict_entries(self, tmp_path: Path):
        """Raw strings / ints in the catalog must be skipped, not crash callers."""
        path = tmp_path / "custom_skills.yaml"
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
        reg = YamlSkillRegistry(custom_catalog_path=path)
        entries = reg.list_custom_entries()
        assert [e["slug"] for e in entries] == ["good", "also-good"]
        # get_entry must not blow up on the bad entries
        assert reg.get_entry("good") is not None
        assert reg.get_entry("missing") is None

    @pytest.mark.asyncio
    async def test_search_tolerates_non_dict_entries(self, tmp_path: Path):
        """search_skills must not AttributeError when the catalog has junk entries."""
        path = tmp_path / "custom_skills.yaml"
        path.write_text(
            yaml.dump([{"slug": "ok", "name": "OK"}, "junk"], sort_keys=False),
            encoding="utf-8",
        )
        reg = YamlSkillRegistry(custom_catalog_path=path, inner=_StubSkillsShRegistry())
        results = await reg.search_skills("", limit=10)
        assert [r["slug"] for r in results] == ["ok"]

    @pytest.mark.asyncio
    async def test_install_rejects_unsafe_stored_slug(self, tmp_path: Path):
        """A corrupt catalog entry with a path-traversal slug must not be installed."""
        path = tmp_path / "custom_skills.yaml"
        _write_yaml(
            path,
            [
                {
                    "slug": "../../etc",
                    "name": "Evil",
                    "skill_content": "---\nname: x\ndescription: y\n---\n",
                }
            ],
        )
        inner = _StubSkillsShRegistry()
        reg = YamlSkillRegistry(custom_catalog_path=path, inner=inner)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        rc, _, stderr = await reg.install_skill("../../etc", workspace)
        assert rc == 1
        assert "unsafe slug" in stderr
        assert inner.install_calls == []
        # And nothing was written outside the skills dir
        assert not (tmp_path / "etc").exists()

    @pytest.mark.asyncio
    async def test_install_missing_content_returns_explicit_error(
        self, tmp_path: Path, sample_custom_entry: dict
    ):
        """Catalog entry without skill_content should not silently fall back to npx."""
        entry = {**sample_custom_entry, "skill_content": ""}
        path = tmp_path / "custom_skills.yaml"
        _write_yaml(path, [entry])
        inner = _StubSkillsShRegistry()
        reg = YamlSkillRegistry(custom_catalog_path=path, inner=inner)

        rc, _, stderr = await reg.install_skill("my-pdf-helper", tmp_path)
        assert rc == 1
        assert "missing SKILL.md content" in stderr
        assert inner.install_calls == []  # did NOT fall through to agentskill.sh

    def test_mutators_are_thread_safe(self, tmp_path: Path):
        """Concurrent adds should not lose entries thanks to the per-instance lock."""
        path = tmp_path / "custom_skills.yaml"
        reg = YamlSkillRegistry(custom_catalog_path=path)

        def add(i: int) -> None:
            reg.add_custom_entry({"slug": f"s{i}", "name": f"n{i}"})

        threads = [threading.Thread(target=add, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        slugs = sorted(e["slug"] for e in reg.list_custom_entries())
        assert slugs == sorted(f"s{i}" for i in range(20))
