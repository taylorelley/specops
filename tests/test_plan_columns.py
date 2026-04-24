"""Tests for adding, editing, and removing columns on plans.

Covers:
- ``POST /api/plans/{plan_id}/columns`` creates a column and appends it.
- ``PUT /api/plans/{plan_id}/columns/{column_id}`` edits title/kind/position.
- ``DELETE /api/plans/{plan_id}/columns/{column_id}`` removes it and guards
  against deleting the last column or a column with tasks.
- All three endpoints refuse to mutate active/completed plans.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("ADMIN_STORAGE_ROOT", str(data_dir))
    monkeypatch.setenv("SPECOPS_ENV", "development")
    monkeypatch.setenv("ADMIN_RUNTIME_BACKEND", "process")
    monkeypatch.setenv("RATELIMIT_ENABLED", "0")
    from specops.core import database as db_module
    from specops_lib.registry import factory as registry_factory

    db_module.get_database.cache_clear()
    registry_factory._plan_template_registry = None  # type: ignore[attr-defined]
    yield data_dir
    db_module.get_database.cache_clear()
    registry_factory._plan_template_registry = None  # type: ignore[attr-defined]


@pytest.fixture
def client(isolated_data_dir: Path):
    from specops.app import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def admin_headers(client: TestClient) -> dict:
    from specops.auth import hash_password
    from specops.core.database import get_database
    from specops.core.store.users import UserStore

    UserStore(get_database()).create_user(
        username="admin", password_hash=hash_password("adminpass"), role="admin"
    )
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "adminpass"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_plan(client: TestClient, headers: dict, name: str = "P") -> dict:
    resp = client.post("/api/plans", headers=headers, json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestAddColumn:
    def test_add_column_appends_to_plan(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        initial_count = len(plan["columns"])
        max_pos = max(c["position"] for c in plan["columns"])

        resp = client.post(
            f"/api/plans/{plan['id']}/columns",
            headers=admin_headers,
            json={"title": "In Review"},
        )
        assert resp.status_code == 200, resp.text
        col = resp.json()
        assert col["title"] == "In Review"
        assert col["kind"] == "standard"
        assert col["position"] == max_pos + 1
        assert col["id"].startswith(f"{plan['id']}-col-")

        refreshed = client.get(f"/api/plans/{plan['id']}", headers=admin_headers).json()
        assert len(refreshed["columns"]) == initial_count + 1
        assert any(c["id"] == col["id"] for c in refreshed["columns"])

    def test_add_review_column_round_trips_kind(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        resp = client.post(
            f"/api/plans/{plan['id']}/columns",
            headers=admin_headers,
            json={"title": "Approval", "kind": "review"},
        )
        assert resp.status_code == 200
        assert resp.json()["kind"] == "review"

    def test_add_column_rejects_empty_title(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        resp = client.post(
            f"/api/plans/{plan['id']}/columns",
            headers=admin_headers,
            json={"title": "   "},
        )
        assert resp.status_code == 400

    def test_add_column_assigns_unique_ids_for_duplicate_titles(
        self, client: TestClient, admin_headers
    ):
        plan = _create_plan(client, admin_headers)
        first = client.post(
            f"/api/plans/{plan['id']}/columns",
            headers=admin_headers,
            json={"title": "Review"},
        ).json()
        second = client.post(
            f"/api/plans/{plan['id']}/columns",
            headers=admin_headers,
            json={"title": "Review"},
        ).json()
        assert first["id"] != second["id"]

    def test_add_column_blocked_when_plan_active(self, client: TestClient, admin_headers):
        """Active plans are frozen — you must pause first to reshape the board."""
        plan = _create_plan(client, admin_headers)
        # Assign an agent and a task so activation succeeds (activation requires
        # no unassigned tasks). Use the plan-agent assignment API to wire it up.
        from specops.core.database import get_database

        with get_database().connection() as conn:
            conn.execute(
                """INSERT INTO agents
                   (id, name, description, color, enabled, status, base_path,
                    agent_token, mode, created_at, updated_at)
                   VALUES ('a1','a1','','',1,'stopped','','tkn-a1','agent',
                           '2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"""
            )
        client.post(f"/api/plans/{plan['id']}/agents/a1", headers=admin_headers)
        client.post(
            f"/api/plans/{plan['id']}/tasks",
            headers=admin_headers,
            json={"column_id": "todo", "title": "x", "agent_id": "a1"},
        )
        activated = client.post(f"/api/plans/{plan['id']}/activate", headers=admin_headers)
        assert activated.status_code == 200, activated.text

        resp = client.post(
            f"/api/plans/{plan['id']}/columns",
            headers=admin_headers,
            json={"title": "Nope"},
        )
        assert resp.status_code == 409
        assert "draft" in resp.json()["detail"]


class TestUpdateColumn:
    def test_update_column_title(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        col = plan["columns"][0]
        resp = client.put(
            f"/api/plans/{plan['id']}/columns/{col['id']}",
            headers=admin_headers,
            json={"title": "Backlog"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Backlog"

    def test_update_column_kind_to_review(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        col = plan["columns"][0]
        resp = client.put(
            f"/api/plans/{plan['id']}/columns/{col['id']}",
            headers=admin_headers,
            json={"kind": "review"},
        )
        assert resp.status_code == 200
        assert resp.json()["kind"] == "review"

    def test_update_column_rejects_blank_title(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        col = plan["columns"][0]
        resp = client.put(
            f"/api/plans/{plan['id']}/columns/{col['id']}",
            headers=admin_headers,
            json={"title": "   "},
        )
        assert resp.status_code == 400

    def test_update_ignores_explicit_null_fields(self, client: TestClient, admin_headers):
        """Clients that send ``{"title": null}`` should no-op that field, not 500."""
        plan = _create_plan(client, admin_headers)
        col = plan["columns"][0]
        resp = client.put(
            f"/api/plans/{plan['id']}/columns/{col['id']}",
            headers=admin_headers,
            json={"title": None, "kind": None, "position": None},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["title"] == col["title"]
        assert body["kind"] == col["kind"]
        assert body["position"] == col["position"]

    def test_update_missing_column_returns_404(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        resp = client.put(
            f"/api/plans/{plan['id']}/columns/does-not-exist",
            headers=admin_headers,
            json={"title": "X"},
        )
        assert resp.status_code == 404


class TestDeleteColumn:
    def test_delete_empty_column(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        # Add a throwaway column so the plan still has other columns after delete.
        added = client.post(
            f"/api/plans/{plan['id']}/columns",
            headers=admin_headers,
            json={"title": "Temp"},
        ).json()
        resp = client.delete(
            f"/api/plans/{plan['id']}/columns/{added['id']}", headers=admin_headers
        )
        assert resp.status_code == 200

        refreshed = client.get(f"/api/plans/{plan['id']}", headers=admin_headers).json()
        assert all(c["id"] != added["id"] for c in refreshed["columns"])

    def test_cannot_delete_column_with_tasks(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        client.post(
            f"/api/plans/{plan['id']}/tasks",
            headers=admin_headers,
            json={"column_id": "todo", "title": "work"},
        )
        todo_col = next(c for c in plan["columns"] if c["title"] == "Todo")
        resp = client.delete(
            f"/api/plans/{plan['id']}/columns/{todo_col['id']}", headers=admin_headers
        )
        assert resp.status_code == 409
        assert "tasks" in resp.json()["detail"].lower()

    def test_cannot_delete_last_column(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        # Delete every column except one (none have tasks yet).
        columns = plan["columns"]
        for col in columns[:-1]:
            r = client.delete(f"/api/plans/{plan['id']}/columns/{col['id']}", headers=admin_headers)
            assert r.status_code == 200, r.text
        last = columns[-1]
        resp = client.delete(f"/api/plans/{plan['id']}/columns/{last['id']}", headers=admin_headers)
        assert resp.status_code == 409
        assert "last column" in resp.json()["detail"].lower()

    def test_delete_missing_column_returns_404(self, client: TestClient, admin_headers):
        plan = _create_plan(client, admin_headers)
        resp = client.delete(f"/api/plans/{plan['id']}/columns/no-such-id", headers=admin_headers)
        assert resp.status_code == 404


class TestPausedPlanAllowsColumnEdits:
    def test_paused_plan_can_add_column(self, client: TestClient, admin_headers):
        """Pausing a plan should re-enable column management."""
        from specops.core.database import get_database

        plan = _create_plan(client, admin_headers)
        with get_database().connection() as conn:
            conn.execute(
                """INSERT INTO agents
                   (id, name, description, color, enabled, status, base_path,
                    agent_token, mode, created_at, updated_at)
                   VALUES ('a1','a1','','',1,'stopped','','tkn-a1','agent',
                           '2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')"""
            )
        client.post(f"/api/plans/{plan['id']}/agents/a1", headers=admin_headers)
        client.post(
            f"/api/plans/{plan['id']}/tasks",
            headers=admin_headers,
            json={"column_id": "todo", "title": "x", "agent_id": "a1"},
        )
        client.post(f"/api/plans/{plan['id']}/activate", headers=admin_headers)
        client.post(f"/api/plans/{plan['id']}/deactivate", headers=admin_headers)

        resp = client.post(
            f"/api/plans/{plan['id']}/columns",
            headers=admin_headers,
            json={"title": "Paused Addition"},
        )
        assert resp.status_code == 200, resp.text
