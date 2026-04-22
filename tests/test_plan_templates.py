"""Tests for the plan templates marketplace feature.

Covers:
- YamlPlanTemplateRegistry (bundled + custom YAML merge, CRUD on the custom catalog).
- PlanStore.create_plan_from_template (default and custom columns, task routing).
- /api/plan-templates CRUD endpoints and POST /api/plans with template_id.
"""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from clawlib.plantemplateregistry import YamlPlanTemplateRegistry

# ---------------------------------------------------------------------------
# YamlPlanTemplateRegistry — pure unit tests (no FastAPI, no SQLite)
# ---------------------------------------------------------------------------


class TestYamlPlanTemplateRegistry:
    def _write(self, path: Path, data: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")

    def test_list_entries_merges_bundled_and_custom(self, tmp_path: Path):
        bundled = tmp_path / "bundled.yaml"
        custom = tmp_path / "custom.yaml"
        self._write(bundled, [{"id": "a", "name": "A", "tasks": []}])
        self._write(custom, [{"id": "b", "name": "B", "tasks": []}])
        reg = YamlPlanTemplateRegistry(catalog_path=bundled, custom_catalog_path=custom)
        entries = reg.list_entries()
        assert [e["id"] for e in entries] == ["a", "b"]

    def test_custom_cannot_shadow_bundled_id(self, tmp_path: Path):
        """Custom entries whose id collides with a bundled entry are ignored by list_entries."""
        bundled = tmp_path / "bundled.yaml"
        custom = tmp_path / "custom.yaml"
        self._write(bundled, [{"id": "dup", "name": "Bundled", "tasks": []}])
        self._write(custom, [{"id": "dup", "name": "Custom Override", "tasks": []}])
        reg = YamlPlanTemplateRegistry(catalog_path=bundled, custom_catalog_path=custom)
        entries = reg.list_entries()
        assert len(entries) == 1
        assert entries[0]["name"] == "Bundled"

    def test_add_update_delete_custom_entry(self, tmp_path: Path):
        bundled = tmp_path / "bundled.yaml"
        custom = tmp_path / "custom.yaml"
        self._write(bundled, [])
        reg = YamlPlanTemplateRegistry(catalog_path=bundled, custom_catalog_path=custom)

        reg.add_custom_entry({"id": "x", "name": "X", "tasks": []})
        assert reg.get_entry("x") is not None
        assert [e["id"] for e in reg.list_custom_entries()] == ["x"]

        assert reg.update_custom_entry("x", {"id": "x", "name": "X2", "tasks": []})
        assert reg.get_entry("x")["name"] == "X2"

        assert reg.delete_custom_entry("x") is True
        assert reg.get_entry("x") is None

    def test_update_missing_returns_false(self, tmp_path: Path):
        bundled = tmp_path / "bundled.yaml"
        custom = tmp_path / "custom.yaml"
        self._write(bundled, [])
        reg = YamlPlanTemplateRegistry(catalog_path=bundled, custom_catalog_path=custom)
        assert reg.update_custom_entry("nope", {"id": "nope", "name": "X"}) is False
        assert reg.delete_custom_entry("nope") is False

    def test_missing_catalog_files_return_empty_list(self, tmp_path: Path):
        reg = YamlPlanTemplateRegistry(
            catalog_path=tmp_path / "nope.yaml",
            custom_catalog_path=tmp_path / "also-nope.yaml",
        )
        assert reg.list_entries() == []
        assert reg.list_custom_entries() == []

    def test_add_creates_missing_parent_directory(self, tmp_path: Path):
        bundled = tmp_path / "bundled.yaml"
        self._write(bundled, [])
        custom = tmp_path / "nested" / "dirs" / "custom.yaml"
        reg = YamlPlanTemplateRegistry(catalog_path=bundled, custom_catalog_path=custom)
        reg.add_custom_entry({"id": "x", "name": "X", "tasks": []})
        assert custom.exists()


# ---------------------------------------------------------------------------
# API integration tests — uses TestClient with isolated data dir
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("ADMIN_STORAGE_ROOT", str(data_dir))
    monkeypatch.setenv("CLAWFORCE_ENV", "development")
    monkeypatch.setenv("ADMIN_RUNTIME_BACKEND", "process")
    monkeypatch.setenv("RATELIMIT_ENABLED", "0")
    # Force re-initialisation of cached singletons
    from clawforce.core import database as db_module
    from clawlib.registry import factory as registry_factory

    db_module.get_database.cache_clear()
    registry_factory._plan_template_registry = None  # type: ignore[attr-defined]
    yield data_dir
    db_module.get_database.cache_clear()
    registry_factory._plan_template_registry = None  # type: ignore[attr-defined]


@pytest.fixture
def client(isolated_data_dir: Path):
    from clawforce.app import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def admin_user(client: TestClient):
    from clawforce.auth import hash_password
    from clawforce.core.database import get_database
    from clawforce.core.store.users import UserStore

    UserStore(get_database()).create_user(
        username="testadmin", password_hash=hash_password("testpass"), role="admin"
    )
    return "testadmin", "testpass"


@pytest.fixture
def auth_headers(client: TestClient, admin_user):
    username, password = admin_user
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _seed_agents(agent_ids: list[str]) -> None:
    """Insert minimal agent rows so plan_agents/plan_tasks FKs can reference them."""
    from clawforce.core.database import get_database

    with get_database().connection() as conn:
        for aid in agent_ids:
            conn.execute(
                """INSERT OR IGNORE INTO agents
                   (id, name, description, color, enabled, status, base_path, agent_token, mode, created_at, updated_at)
                   VALUES (?, ?, '', '', 1, 'stopped', '', ?, 'agent', ?, ?)""",
                (
                    aid,
                    aid,
                    f"token-{aid}",
                    "2026-01-01T00:00:00Z",
                    "2026-01-01T00:00:00Z",
                ),
            )


class TestPlanTemplateEndpoints:
    def test_list_returns_bundled_starters(self, client: TestClient, auth_headers):
        resp = client.get("/api/plan-templates", headers=auth_headers)
        assert resp.status_code == 200
        ids = {e["id"] for e in resp.json()}
        # The bundled catalog ships with these starter templates.
        assert {"product-launch", "sprint-planning", "bug-triage", "research-project"} <= ids

    def test_get_single_template(self, client: TestClient, auth_headers):
        resp = client.get("/api/plan-templates/bug-triage", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "bug-triage"
        assert body["columns"], "bug-triage ships with custom columns"

    def test_get_missing_template_404(self, client: TestClient, auth_headers):
        resp = client.get("/api/plan-templates/does-not-exist", headers=auth_headers)
        assert resp.status_code == 404

    def test_add_list_update_delete_custom(self, client: TestClient, auth_headers):
        payload = {
            "id": "my-tmpl",
            "name": "My Template",
            "description": "demo",
            "tasks": [{"title": "t1", "column": "todo"}],
        }
        # Create
        resp = client.post("/api/plan-templates", headers=auth_headers, json=payload)
        assert resp.status_code == 201
        assert resp.json()["id"] == "my-tmpl"

        # Appears in merged list
        resp = client.get("/api/plan-templates", headers=auth_headers)
        assert "my-tmpl" in {e["id"] for e in resp.json()}

        # Appears in custom-only list
        resp = client.get("/api/plan-templates/custom", headers=auth_headers)
        assert [e["id"] for e in resp.json()] == ["my-tmpl"]

        # Update
        resp = client.put(
            "/api/plan-templates/my-tmpl",
            headers=auth_headers,
            json={**payload, "name": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

        # Delete
        resp = client.delete("/api/plan-templates/my-tmpl", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "id": "my-tmpl"}
        resp = client.get("/api/plan-templates/my-tmpl", headers=auth_headers)
        assert resp.status_code == 404

    def test_add_duplicate_id_returns_409(self, client: TestClient, auth_headers):
        # Bundled id collision
        resp = client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={
                "id": "product-launch",
                "name": "Clash",
                "tasks": [{"title": "x", "column": "todo"}],
            },
        )
        assert resp.status_code == 409

    def test_update_url_body_mismatch_400(self, client: TestClient, auth_headers):
        client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={"id": "t1", "name": "T1", "tasks": [{"title": "a", "column": "todo"}]},
        )
        resp = client.put(
            "/api/plan-templates/t1",
            headers=auth_headers,
            json={"id": "different", "name": "T1", "tasks": []},
        )
        assert resp.status_code == 400

    def test_requires_auth(self, client: TestClient):
        assert client.get("/api/plan-templates").status_code == 401
        assert (
            client.post(
                "/api/plan-templates",
                json={"id": "x", "name": "X", "tasks": []},
            ).status_code
            == 401
        )

    @pytest.mark.parametrize(
        "bad_id",
        [
            "",  # empty
            "custom",  # reserved — collides with /api/plan-templates/custom
            "a/b",  # slashes
            "Upper",  # uppercase
            "-leading",  # leading dash
            "trailing-",  # trailing dash
            "has space",  # whitespace
        ],
    )
    def test_rejects_invalid_ids(self, client: TestClient, auth_headers, bad_id):
        resp = client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={"id": bad_id, "name": "X", "tasks": [{"title": "t", "column": "todo"}]},
        )
        # Pydantic validation errors surface as 422.
        assert resp.status_code == 422, resp.text

    def test_accepts_valid_ids(self, client: TestClient, auth_headers):
        for good_id in ["a", "a1", "my-plan", "bug-bash-2024"]:
            resp = client.post(
                "/api/plan-templates",
                headers=auth_headers,
                json={
                    "id": good_id,
                    "name": good_id,
                    "tasks": [{"title": "t", "column": "todo"}],
                },
            )
            assert resp.status_code == 201, resp.text
            client.delete(f"/api/plan-templates/{good_id}", headers=auth_headers)


class TestCreatePlanFromTemplate:
    def test_blank_plan_still_default_columns(self, client: TestClient, auth_headers):
        resp = client.post("/api/plans", headers=auth_headers, json={"name": "Blank"})
        assert resp.status_code == 200
        plan = resp.json()
        assert [c["title"] for c in plan["columns"]] == [
            "Todo",
            "In Progress",
            "Blocked",
            "Done",
        ]
        assert plan["tasks"] == []

    def test_from_template_with_default_columns(self, client: TestClient, auth_headers):
        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "Launch X", "template_id": "product-launch"},
        )
        assert resp.status_code == 200
        plan = resp.json()
        assert [c["title"] for c in plan["columns"]] == [
            "Todo",
            "In Progress",
            "Blocked",
            "Done",
        ]
        assert len(plan["tasks"]) == 5
        # All product-launch tasks route to the Todo column.
        todo_id = next(c["id"] for c in plan["columns"] if c["title"] == "Todo")
        assert {t["column_id"] for t in plan["tasks"]} == {todo_id}

    def test_from_template_with_custom_columns(self, client: TestClient, auth_headers):
        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "Triage", "template_id": "bug-triage"},
        )
        assert resp.status_code == 200
        plan = resp.json()
        assert [c["title"] for c in plan["columns"]] == [
            "Triage",
            "Investigating",
            "Fix in Progress",
            "Verified",
        ]
        # Bundled template seeds at least one task in every column.
        column_by_id = {c["id"]: c["title"] for c in plan["columns"]}
        titles_with_tasks = {column_by_id[t["column_id"]] for t in plan["tasks"]}
        assert titles_with_tasks == {
            "Triage",
            "Investigating",
            "Fix in Progress",
            "Verified",
        }

    def test_from_custom_template(self, client: TestClient, auth_headers):
        # Create a custom template, then create a plan from it.
        resp = client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={
                "id": "mine",
                "name": "Mine",
                "columns": [{"title": "Left"}, {"title": "Right"}],
                "tasks": [
                    {"title": "a", "column": "left"},
                    {"title": "b", "column": "right"},
                    {"title": "c", "column": "right"},
                ],
            },
        )
        assert resp.status_code == 201

        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "From Mine", "template_id": "mine"},
        )
        assert resp.status_code == 200
        plan = resp.json()
        assert [c["title"] for c in plan["columns"]] == ["Left", "Right"]
        left_id = next(c["id"] for c in plan["columns"] if c["title"] == "Left")
        right_id = next(c["id"] for c in plan["columns"] if c["title"] == "Right")
        tasks_by_title = {t["title"]: t["column_id"] for t in plan["tasks"]}
        assert tasks_by_title == {"a": left_id, "b": right_id, "c": right_id}

    def test_unknown_template_id_returns_404(self, client: TestClient, auth_headers):
        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "X", "template_id": "no-such-template"},
        )
        assert resp.status_code == 404

    def test_task_with_unknown_column_falls_back_to_first(self, client: TestClient, auth_headers):
        """Tasks referencing a column that doesn't exist should land in the first column."""
        created = client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={
                "id": "fallback",
                "name": "Fallback",
                "tasks": [{"title": "lost task", "column": "nowhere"}],
            },
        )
        assert created.status_code == 201, created.text
        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "Fallback plan", "template_id": "fallback"},
        )
        assert resp.status_code == 200, resp.text
        plan = resp.json()
        first_col_id = plan["columns"][0]["id"]
        assert plan["tasks"][0]["column_id"] == first_col_id


class TestAgentPreassignment:
    def test_plan_level_agents_preassigned(self, client: TestClient, auth_headers):
        _seed_agents(["agent-1", "agent-2"])
        created = client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={
                "id": "with-agents",
                "name": "Has Agents",
                "agent_ids": ["agent-1", "agent-2"],
                "tasks": [{"title": "t", "column": "todo"}],
            },
        )
        assert created.status_code == 201, created.text
        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "New plan", "template_id": "with-agents"},
        )
        assert resp.status_code == 200, resp.text
        plan = resp.json()
        assert sorted(plan["agent_ids"]) == ["agent-1", "agent-2"]

    def test_task_level_agent_is_applied(self, client: TestClient, auth_headers):
        _seed_agents(["agent-1"])
        created = client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={
                "id": "task-owner",
                "name": "Task Owner",
                "tasks": [
                    {"title": "owned", "column": "todo", "agent_id": "agent-1"},
                    {"title": "unowned", "column": "todo"},
                ],
            },
        )
        assert created.status_code == 201, created.text
        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "P", "template_id": "task-owner"},
        )
        assert resp.status_code == 200, resp.text
        plan = resp.json()
        by_title = {t["title"]: t["agent_id"] for t in plan["tasks"]}
        assert by_title["owned"] == "agent-1"
        assert by_title["unowned"] == ""
        # A task-only agent must also end up on the plan's agents list.
        assert plan["agent_ids"] == ["agent-1"]

    def test_missing_plan_agent_is_silently_skipped(self, client: TestClient, auth_headers):
        _seed_agents(["real-agent"])
        created = client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={
                "id": "stale-plan-agents",
                "name": "Stale",
                "agent_ids": ["real-agent", "ghost-agent"],
                "tasks": [{"title": "t", "column": "todo"}],
            },
        )
        assert created.status_code == 201, created.text
        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "P", "template_id": "stale-plan-agents"},
        )
        assert resp.status_code == 200, resp.text
        plan = resp.json()
        assert plan["agent_ids"] == ["real-agent"]

    def test_missing_task_agent_leaves_task_unassigned(self, client: TestClient, auth_headers):
        _seed_agents(["real-agent"])
        created = client.post(
            "/api/plan-templates",
            headers=auth_headers,
            json={
                "id": "stale-task-agent",
                "name": "Stale Task",
                "tasks": [
                    {"title": "lost owner", "column": "todo", "agent_id": "ghost"},
                    {"title": "good owner", "column": "todo", "agent_id": "real-agent"},
                ],
            },
        )
        assert created.status_code == 201, created.text
        resp = client.post(
            "/api/plans",
            headers=auth_headers,
            json={"name": "P", "template_id": "stale-task-agent"},
        )
        assert resp.status_code == 200, resp.text
        plan = resp.json()
        by_title = {t["title"]: t["agent_id"] for t in plan["tasks"]}
        assert by_title["lost owner"] == ""
        assert by_title["good owner"] == "real-agent"
        assert plan["agent_ids"] == ["real-agent"]

    def test_add_template_with_agents_roundtrip(self, client: TestClient, auth_headers):
        _seed_agents(["a1"])
        payload = {
            "id": "rt",
            "name": "RT",
            "agent_ids": ["a1"],
            "tasks": [{"title": "t1", "column": "todo", "agent_id": "a1"}],
        }
        resp = client.post("/api/plan-templates", headers=auth_headers, json=payload)
        assert resp.status_code == 201
        assert resp.json()["agent_ids"] == ["a1"]
        assert resp.json()["tasks"][0]["agent_id"] == "a1"

        resp = client.get("/api/plan-templates/rt", headers=auth_headers)
        assert resp.json()["agent_ids"] == ["a1"]
        assert resp.json()["tasks"][0]["agent_id"] == "a1"
