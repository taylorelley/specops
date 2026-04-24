"""Tests for the human-review column type and task review gating.

Covers:
- Column ``kind`` round-trips through the template registry and store.
- Task ``requires_review`` / ``review_status`` round-trip.
- ``PUT /api/plans/{plan_id}/tasks/{task_id}`` enforces the review gate when
  agents try to move a task out of a review column.
- ``POST /api/plans/{plan_id}/tasks/{task_id}/review`` records a human decision.
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


def _seed_agent(agent_id: str) -> str:
    """Insert an agent row and return its token so we can call the API as it."""
    from specops.core.database import get_database

    token = f"tkn-{agent_id}"
    with get_database().connection() as conn:
        conn.execute(
            """INSERT INTO agents
               (id, name, description, color, enabled, status, base_path, agent_token, mode, created_at, updated_at)
               VALUES (?, ?, '', '', 1, 'stopped', '', ?, 'agent', ?, ?)""",
            (agent_id, agent_id, token, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
    return token


def _agent_headers(agent_id: str) -> dict:
    token = _seed_agent(agent_id)
    return {"Authorization": f"Bearer {token}"}


class TestColumnKindAndTaskFields:
    def test_default_columns_have_standard_kind(self, client: TestClient, admin_headers):
        resp = client.post("/api/plans", headers=admin_headers, json={"name": "Plain"})
        assert resp.status_code == 200
        plan = resp.json()
        assert {c["kind"] for c in plan["columns"]} == {"standard"}

    def test_review_column_kind_round_trips_from_template(
        self, client: TestClient, admin_headers
    ):
        # Register a custom template that declares a review column.
        created = client.post(
            "/api/plan-templates",
            headers=admin_headers,
            json={
                "id": "with-review",
                "name": "With Review",
                "columns": [
                    {"title": "Todo"},
                    {"title": "Review", "kind": "review"},
                    {"title": "Done"},
                ],
                "tasks": [{"title": "work", "column": "todo"}],
            },
        )
        assert created.status_code == 201, created.text

        resp = client.post(
            "/api/plans",
            headers=admin_headers,
            json={"name": "p1", "template_id": "with-review"},
        )
        assert resp.status_code == 200
        plan = resp.json()
        by_title = {c["title"]: c for c in plan["columns"]}
        assert by_title["Todo"]["kind"] == "standard"
        assert by_title["Review"]["kind"] == "review"
        assert by_title["Done"]["kind"] == "standard"

    def test_tasks_default_to_requires_review_true(self, client: TestClient, admin_headers):
        plan_id = client.post(
            "/api/plans", headers=admin_headers, json={"name": "p"}
        ).json()["id"]
        columns = client.get(f"/api/plans/{plan_id}", headers=admin_headers).json()["columns"]
        resp = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=admin_headers,
            json={"column_id": columns[0]["id"], "title": "t"},
        )
        assert resp.status_code == 200
        task = resp.json()
        assert task["requires_review"] is True
        assert task["review_status"] is None


def _make_review_plan(client: TestClient, admin_headers: dict) -> tuple[str, dict]:
    """Create a plan with Todo / Review / Done columns and return (plan_id, columns_by_title)."""
    client.post(
        "/api/plan-templates",
        headers=admin_headers,
        json={
            "id": "review-flow",
            "name": "Review Flow",
            "columns": [
                {"title": "Todo"},
                {"title": "Review", "kind": "review"},
                {"title": "Done"},
            ],
            "tasks": [],
        },
    )
    plan = client.post(
        "/api/plans",
        headers=admin_headers,
        json={"name": "P", "template_id": "review-flow"},
    ).json()
    columns = {c["title"]: c for c in plan["columns"]}
    return plan["id"], columns


class TestReviewGateEnforcement:
    def test_entering_review_column_pends_task(self, client: TestClient, admin_headers):
        plan_id, cols = _make_review_plan(client, admin_headers)
        agent_id = "agent-worker"
        agent_headers = _agent_headers(agent_id)

        client.post(f"/api/plans/{plan_id}/agents/{agent_id}", headers=admin_headers)
        task = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=admin_headers,
            json={"column_id": cols["Todo"]["id"], "title": "t", "agent_id": agent_id},
        ).json()

        resp = client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"column_id": cols["Review"]["id"]},
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["column_id"] == cols["Review"]["id"]
        assert updated["review_status"] == "pending"

    def test_agent_cannot_move_task_out_of_review_without_approval(
        self, client: TestClient, admin_headers
    ):
        plan_id, cols = _make_review_plan(client, admin_headers)
        agent_id = "agent-worker"
        agent_headers = _agent_headers(agent_id)
        client.post(f"/api/plans/{plan_id}/agents/{agent_id}", headers=admin_headers)
        task = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=admin_headers,
            json={"column_id": cols["Todo"]["id"], "title": "t", "agent_id": agent_id},
        ).json()
        # Agent moves the task into Review (OK — pends).
        client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"column_id": cols["Review"]["id"]},
        )
        # Agent now tries to push it to Done without any human approval.
        resp = client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"column_id": cols["Done"]["id"]},
        )
        assert resp.status_code == 409, resp.text

    def test_approval_unblocks_agent_progression(self, client: TestClient, admin_headers):
        plan_id, cols = _make_review_plan(client, admin_headers)
        agent_id = "agent-worker"
        agent_headers = _agent_headers(agent_id)
        client.post(f"/api/plans/{plan_id}/agents/{agent_id}", headers=admin_headers)
        task = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=admin_headers,
            json={"column_id": cols["Todo"]["id"], "title": "t", "agent_id": agent_id},
        ).json()
        client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"column_id": cols["Review"]["id"]},
        )
        # Human approves.
        approve = client.post(
            f"/api/plans/{plan_id}/tasks/{task['id']}/review",
            headers=admin_headers,
            json={"decision": "approved", "note": "lgtm"},
        )
        assert approve.status_code == 200, approve.text
        body = approve.json()
        assert body["review_status"] == "approved"
        assert body["review_note"] == "lgtm"
        # Agent can now move to Done; server also clears stale review state
        # since the task left the review column.
        resp = client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"column_id": cols["Done"]["id"]},
        )
        assert resp.status_code == 200, resp.text
        moved = resp.json()
        assert moved["column_id"] == cols["Done"]["id"]
        assert moved["review_status"] is None

    def test_requires_review_false_bypasses_gate(self, client: TestClient, admin_headers):
        plan_id, cols = _make_review_plan(client, admin_headers)
        agent_id = "agent-worker"
        agent_headers = _agent_headers(agent_id)
        client.post(f"/api/plans/{plan_id}/agents/{agent_id}", headers=admin_headers)
        task = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=admin_headers,
            json={"column_id": cols["Todo"]["id"], "title": "skip", "agent_id": agent_id},
        ).json()
        # Human opts this task out of review.
        out = client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=admin_headers,
            json={"requires_review": False},
        )
        assert out.status_code == 200
        assert out.json()["requires_review"] is False
        # Move to Review — should NOT pend because requires_review is False.
        client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"column_id": cols["Review"]["id"]},
        )
        # Agent can move out freely.
        resp = client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"column_id": cols["Done"]["id"]},
        )
        assert resp.status_code == 200

    def test_agent_cannot_toggle_requires_review(self, client: TestClient, admin_headers):
        plan_id, cols = _make_review_plan(client, admin_headers)
        agent_id = "agent-worker"
        agent_headers = _agent_headers(agent_id)
        client.post(f"/api/plans/{plan_id}/agents/{agent_id}", headers=admin_headers)
        task = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=admin_headers,
            json={"column_id": cols["Todo"]["id"], "title": "t", "agent_id": agent_id},
        ).json()
        resp = client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"requires_review": False},
        )
        assert resp.status_code == 403


class TestReviewEndpoint:
    def test_review_rejects_non_review_column(self, client: TestClient, admin_headers):
        plan_id, cols = _make_review_plan(client, admin_headers)
        task = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=admin_headers,
            json={"column_id": cols["Todo"]["id"], "title": "t"},
        ).json()
        resp = client.post(
            f"/api/plans/{plan_id}/tasks/{task['id']}/review",
            headers=admin_headers,
            json={"decision": "approved"},
        )
        assert resp.status_code == 409

    def test_review_requires_human_auth(self, client: TestClient, admin_headers):
        plan_id, cols = _make_review_plan(client, admin_headers)
        agent_id = "agent-worker"
        agent_headers = _agent_headers(agent_id)
        client.post(f"/api/plans/{plan_id}/agents/{agent_id}", headers=admin_headers)
        task = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=admin_headers,
            json={"column_id": cols["Todo"]["id"], "title": "t", "agent_id": agent_id},
        ).json()
        client.put(
            f"/api/plans/{plan_id}/tasks/{task['id']}",
            headers=agent_headers,
            json={"column_id": cols["Review"]["id"]},
        )
        # Agent tries to approve its own task — must be rejected at auth layer.
        resp = client.post(
            f"/api/plans/{plan_id}/tasks/{task['id']}/review",
            headers=agent_headers,
            json={"decision": "approved"},
        )
        assert resp.status_code in (401, 403)
