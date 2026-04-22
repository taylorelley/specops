"""Integration tests for multiuser roles and sharing on claws and plans."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("ADMIN_STORAGE_ROOT", str(data_dir))
    monkeypatch.setenv("CLAWFORCE_ENV", "development")
    monkeypatch.setenv("ADMIN_RUNTIME_BACKEND", "process")
    monkeypatch.setenv("RATELIMIT_ENABLED", "0")
    from clawforce.core import database as db_module

    db_module.get_database.cache_clear()
    yield data_dir
    db_module.get_database.cache_clear()


@pytest.fixture
def client(isolated_data_dir: Path):
    from clawforce.app import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _make_user(username: str, password: str, role: str) -> tuple[str, str]:
    from clawforce.auth import hash_password
    from clawforce.core.database import get_database
    from clawforce.core.store.users import UserStore

    UserStore(get_database()).create_user(
        username=username, password_hash=hash_password(password), role=role
    )
    return username, password


def _login(client: TestClient, username: str, password: str) -> dict:
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict:
    _make_user("root", "rootpass", "admin")
    return _login(client, "root", "rootpass")


@pytest.fixture
def alice_headers(client: TestClient) -> dict:
    _make_user("alice", "alicepass", "user")
    return _login(client, "alice", "alicepass")


@pytest.fixture
def bob_headers(client: TestClient) -> dict:
    _make_user("bob", "bobpass", "user")
    return _login(client, "bob", "bobpass")


@pytest.fixture
def carol_headers(client: TestClient) -> dict:
    _make_user("carol", "carolpass", "user")
    return _login(client, "carol", "carolpass")


def _user_id(client: TestClient, headers: dict) -> str:
    resp = client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200
    return resp.json()["id"]


class TestUsersEndpoint:
    def test_list_users_public_for_regular_user(
        self, client: TestClient, admin_headers, alice_headers
    ):
        # Admin creates bob via admin endpoint
        bob = client.post(
            "/api/users",
            headers=admin_headers,
            json={"username": "bob", "password": "bobpass", "role": "user"},
        )
        assert bob.status_code == 201

        resp = client.get("/api/users", headers=alice_headers)
        assert resp.status_code == 200
        body = resp.json()
        usernames = {u["username"] for u in body}
        assert {"root", "alice", "bob"} <= usernames
        # Only id + username exposed
        for u in body:
            assert set(u.keys()) == {"id", "username"}

    def test_admin_list_includes_role(self, client: TestClient, admin_headers):
        resp = client.get("/api/users/admin", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert all("role" in u for u in body)

    def test_regular_user_cannot_see_admin_list(
        self, client: TestClient, admin_headers, alice_headers
    ):
        resp = client.get("/api/users/admin", headers=alice_headers)
        assert resp.status_code == 403

    def test_create_user_rejects_invalid_role(self, client: TestClient, admin_headers):
        resp = client.post(
            "/api/users",
            headers=admin_headers,
            json={"username": "weird", "password": "x", "role": "super_admin"},
        )
        assert resp.status_code == 400

    def test_regular_user_cannot_create_user(
        self, client: TestClient, admin_headers, alice_headers
    ):
        resp = client.post(
            "/api/users",
            headers=alice_headers,
            json={"username": "mallory", "password": "x", "role": "user"},
        )
        assert resp.status_code == 403

    def test_cannot_demote_last_admin(self, client: TestClient, admin_headers):
        root_id = _user_id(client, admin_headers)
        resp = client.patch(
            f"/api/users/{root_id}",
            headers=admin_headers,
            json={"role": "user"},
        )
        assert resp.status_code == 409


class TestMultiuserPlans:
    def test_regular_user_cannot_see_other_users_plan(
        self, client: TestClient, admin_headers, alice_headers, bob_headers
    ):
        created = client.post(
            "/api/plans",
            headers=alice_headers,
            json={"name": "Alice's plan"},
        )
        assert created.status_code == 200
        plan_id = created.json()["id"]

        resp = client.get("/api/plans", headers=bob_headers)
        assert resp.status_code == 200
        assert all(p["id"] != plan_id for p in resp.json())

        direct = client.get(f"/api/plans/{plan_id}", headers=bob_headers)
        assert direct.status_code == 403

    def test_owner_sees_own_plan(self, client: TestClient, alice_headers):
        created = client.post("/api/plans", headers=alice_headers, json={"name": "mine"})
        plan_id = created.json()["id"]
        resp = client.get("/api/plans", headers=alice_headers)
        assert any(p["id"] == plan_id for p in resp.json())

    def test_admin_sees_every_plan(self, client: TestClient, admin_headers, alice_headers):
        client.post("/api/plans", headers=alice_headers, json={"name": "Alice plan"})
        resp = client.get("/api/plans", headers=admin_headers)
        assert resp.status_code == 200
        assert any(p["name"] == "Alice plan" for p in resp.json())

    def test_viewer_share_read_only(self, client: TestClient, alice_headers, bob_headers):
        plan_id = client.post(
            "/api/plans", headers=alice_headers, json={"name": "Shared plan"}
        ).json()["id"]
        bob_id = _user_id(client, bob_headers)

        share = client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "viewer"},
        )
        assert share.status_code == 200

        resp = client.get(f"/api/plans/{plan_id}", headers=bob_headers)
        assert resp.status_code == 200

        # viewer cannot update metadata
        upd = client.put(
            f"/api/plans/{plan_id}",
            headers=bob_headers,
            json={"name": "hacked"},
        )
        assert upd.status_code == 403

    def test_editor_can_update(self, client: TestClient, alice_headers, bob_headers):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        bob_id = _user_id(client, bob_headers)
        client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "editor"},
        ).raise_for_status()

        upd = client.put(
            f"/api/plans/{plan_id}",
            headers=bob_headers,
            json={"name": "renamed"},
        )
        assert upd.status_code == 200
        assert upd.json()["name"] == "renamed"

        # Editor still cannot delete
        delete = client.delete(f"/api/plans/{plan_id}", headers=bob_headers)
        assert delete.status_code == 403

    def test_editor_cannot_share(
        self,
        client: TestClient,
        alice_headers,
        bob_headers,
        carol_headers,
    ):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        bob_id = _user_id(client, bob_headers)
        carol_id = _user_id(client, carol_headers)
        client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "editor"},
        ).raise_for_status()

        resp = client.put(
            f"/api/plans/{plan_id}/shares/{carol_id}",
            headers=bob_headers,
            json={"permission": "viewer"},
        )
        assert resp.status_code == 403

    def test_manager_can_share_but_not_delete(
        self,
        client: TestClient,
        alice_headers,
        bob_headers,
        carol_headers,
    ):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        bob_id = _user_id(client, bob_headers)
        carol_id = _user_id(client, carol_headers)
        client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "manager"},
        ).raise_for_status()

        # Bob (manager) can share with Carol
        shared = client.put(
            f"/api/plans/{plan_id}/shares/{carol_id}",
            headers=bob_headers,
            json={"permission": "viewer"},
        )
        assert shared.status_code == 200

        # Bob still cannot delete
        delete = client.delete(f"/api/plans/{plan_id}", headers=bob_headers)
        assert delete.status_code == 403

    def test_owner_can_delete(self, client: TestClient, alice_headers):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        delete = client.delete(f"/api/plans/{plan_id}", headers=alice_headers)
        assert delete.status_code == 200

    def test_cannot_share_with_owner(self, client: TestClient, alice_headers):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        alice_id = _user_id(client, alice_headers)
        resp = client.put(
            f"/api/plans/{plan_id}/shares/{alice_id}",
            headers=alice_headers,
            json={"permission": "viewer"},
        )
        assert resp.status_code == 400

    def test_revoke_share_blocks_access(self, client: TestClient, alice_headers, bob_headers):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        bob_id = _user_id(client, bob_headers)
        client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "viewer"},
        ).raise_for_status()

        read = client.get(f"/api/plans/{plan_id}", headers=bob_headers)
        assert read.status_code == 200

        client.delete(
            f"/api/plans/{plan_id}/shares/{bob_id}", headers=alice_headers
        ).raise_for_status()

        read_again = client.get(f"/api/plans/{plan_id}", headers=bob_headers)
        assert read_again.status_code == 403


class TestMultiuserAgents:
    def test_regular_user_cannot_see_other_users_agent(
        self, client: TestClient, alice_headers, bob_headers
    ):
        created = client.post("/api/agents", headers=alice_headers, json={"name": "alpha"})
        assert created.status_code in (200, 201)
        agent_id = created.json()["id"]

        listed = client.get("/api/agents", headers=bob_headers)
        assert listed.status_code == 200
        assert all(a["id"] != agent_id for a in listed.json())

        resp = client.get(f"/api/agents/{agent_id}", headers=bob_headers)
        assert resp.status_code == 403

    def test_admin_sees_all_agents(self, client: TestClient, admin_headers, alice_headers):
        client.post("/api/agents", headers=alice_headers, json={"name": "a1"})
        resp = client.get("/api/agents", headers=admin_headers)
        assert resp.status_code == 200
        assert any(a["name"] == "a1" for a in resp.json())

    def test_share_agent_as_viewer(self, client: TestClient, alice_headers, bob_headers):
        agent_id = client.post(
            "/api/agents", headers=alice_headers, json={"name": "shared"}
        ).json()["id"]
        bob_id = _user_id(client, bob_headers)

        share = client.put(
            f"/api/agents/{agent_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "viewer"},
        )
        assert share.status_code == 200

        read = client.get(f"/api/agents/{agent_id}", headers=bob_headers)
        assert read.status_code == 200
        # Viewer cannot rename
        upd = client.put(
            f"/api/agents/{agent_id}",
            headers=bob_headers,
            json={"name": "new"},
        )
        assert upd.status_code == 403

    def test_editor_can_update_agent(self, client: TestClient, alice_headers, bob_headers):
        agent_id = client.post(
            "/api/agents", headers=alice_headers, json={"name": "shared"}
        ).json()["id"]
        bob_id = _user_id(client, bob_headers)
        client.put(
            f"/api/agents/{agent_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "editor"},
        ).raise_for_status()

        upd = client.put(
            f"/api/agents/{agent_id}",
            headers=bob_headers,
            json={"description": "changed"},
        )
        assert upd.status_code == 200

        delete = client.delete(f"/api/agents/{agent_id}", headers=bob_headers)
        assert delete.status_code == 403

    def test_manager_can_reshare_agent(
        self,
        client: TestClient,
        alice_headers,
        bob_headers,
        carol_headers,
    ):
        agent_id = client.post("/api/agents", headers=alice_headers, json={"name": "a"}).json()[
            "id"
        ]
        bob_id = _user_id(client, bob_headers)
        carol_id = _user_id(client, carol_headers)
        client.put(
            f"/api/agents/{agent_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "manager"},
        ).raise_for_status()

        shared = client.put(
            f"/api/agents/{agent_id}/shares/{carol_id}",
            headers=bob_headers,
            json={"permission": "viewer"},
        )
        assert shared.status_code == 200


class TestRoleValidation:
    def test_cli_valid_roles(self):
        from clawforce.core.store.users import VALID_ROLES

        assert VALID_ROLES == frozenset({"admin", "user"})

    def test_create_user_with_invalid_role_raises(self, isolated_data_dir: Path):
        from clawforce.core.database import get_database
        from clawforce.core.store.users import UserStore

        store = UserStore(get_database())
        with pytest.raises(ValueError):
            store.create_user(username="x", password_hash="h", role="super_admin")


class TestPermissionHelper:
    def test_at_least_rejects_unknown_required(self):
        from clawforce.core.domain.share import at_least

        # Typo in required must not grant access.
        assert at_least("manager", "edit") is False
        assert at_least("owner", "bogus") is False

    def test_at_least_rejects_unknown_actual(self):
        from clawforce.core.domain.share import at_least

        assert at_least("bogus", "viewer") is False

    def test_at_least_normal_ordering(self):
        from clawforce.core.domain.share import at_least

        assert at_least("owner", "viewer") is True
        assert at_least("editor", "manager") is False


class TestPlanTaskAuthz:
    def test_non_share_user_cannot_add_task(self, client: TestClient, alice_headers, bob_headers):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        col_id = client.get(f"/api/plans/{plan_id}", headers=alice_headers).json()["columns"][0][
            "id"
        ]
        resp = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=bob_headers,
            json={"column_id": col_id, "title": "mine"},
        )
        assert resp.status_code == 403

    def test_viewer_cannot_add_task(self, client: TestClient, alice_headers, bob_headers):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        col_id = client.get(f"/api/plans/{plan_id}", headers=alice_headers).json()["columns"][0][
            "id"
        ]
        bob_id = _user_id(client, bob_headers)
        client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "viewer"},
        ).raise_for_status()
        resp = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=bob_headers,
            json={"column_id": col_id, "title": "attempt"},
        )
        assert resp.status_code == 403

    def test_editor_can_add_and_delete_task(self, client: TestClient, alice_headers, bob_headers):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        col_id = client.get(f"/api/plans/{plan_id}", headers=alice_headers).json()["columns"][0][
            "id"
        ]
        bob_id = _user_id(client, bob_headers)
        client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "editor"},
        ).raise_for_status()

        create = client.post(
            f"/api/plans/{plan_id}/tasks",
            headers=bob_headers,
            json={"column_id": col_id, "title": "bob task"},
        )
        assert create.status_code == 200
        task_id = create.json()["id"]

        delete = client.delete(f"/api/plans/{plan_id}/tasks/{task_id}", headers=bob_headers)
        assert delete.status_code == 200


class TestEffectivePermissionOnResponses:
    def test_plan_get_returns_effective_permission_for_owner(
        self, client: TestClient, alice_headers
    ):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        resp = client.get(f"/api/plans/{plan_id}", headers=alice_headers)
        assert resp.status_code == 200
        assert resp.json()["effective_permission"] == "owner"

    def test_plan_list_includes_effective_permission_for_viewer(
        self, client: TestClient, alice_headers, bob_headers
    ):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        bob_id = _user_id(client, bob_headers)
        client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "viewer"},
        ).raise_for_status()
        plans = client.get("/api/plans", headers=bob_headers).json()
        entry = next(p for p in plans if p["id"] == plan_id)
        assert entry["effective_permission"] == "viewer"

    def test_agent_list_includes_effective_permission(self, client: TestClient, alice_headers):
        agent_id = client.post("/api/agents", headers=alice_headers, json={"name": "own"}).json()[
            "id"
        ]
        agents = client.get("/api/agents", headers=alice_headers).json()
        entry = next(a for a in agents if a["id"] == agent_id)
        assert entry["effective_permission"] == "owner"


class TestSetShareReturnsPersistedRow:
    def test_plan_share_update_preserves_created_at(
        self, client: TestClient, alice_headers, bob_headers
    ):
        plan_id = client.post("/api/plans", headers=alice_headers, json={"name": "p"}).json()["id"]
        bob_id = _user_id(client, bob_headers)
        first = client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "viewer"},
        ).json()
        upgraded = client.put(
            f"/api/plans/{plan_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "editor"},
        ).json()
        assert upgraded["permission"] == "editor"
        # The returned created_at must be the original (DB-preserved), not a new one.
        assert upgraded["created_at"] == first["created_at"]


class TestSelfDemotionBlocked:
    def test_admin_cannot_demote_themselves_even_if_other_admins_exist(
        self, client: TestClient, admin_headers
    ):
        # Create another admin so count_admins > 1.
        client.post(
            "/api/users",
            headers=admin_headers,
            json={"username": "secondary", "password": "pw", "role": "admin"},
        ).raise_for_status()
        root_id = _user_id(client, admin_headers)
        resp = client.patch(
            f"/api/users/{root_id}",
            headers=admin_headers,
            json={"role": "user"},
        )
        assert resp.status_code == 409


class TestMcpInstallAuthz:
    def test_non_owner_user_cannot_install_mcp_server(
        self, client: TestClient, alice_headers, bob_headers
    ):
        agent_id = client.post("/api/agents", headers=alice_headers, json={"name": "a"}).json()[
            "id"
        ]
        resp = client.post(
            f"/api/agents/{agent_id}/mcp-servers/install",
            headers=bob_headers,
            json={
                "server_id": "fake",
                "server_name": "fake",
                "command": "true",
                "args": [],
            },
        )
        assert resp.status_code == 403

    def test_viewer_cannot_install_mcp_server(self, client: TestClient, alice_headers, bob_headers):
        agent_id = client.post("/api/agents", headers=alice_headers, json={"name": "a"}).json()[
            "id"
        ]
        bob_id = _user_id(client, bob_headers)
        client.put(
            f"/api/agents/{agent_id}/shares/{bob_id}",
            headers=alice_headers,
            json={"permission": "viewer"},
        ).raise_for_status()
        resp = client.post(
            f"/api/agents/{agent_id}/mcp-servers/install",
            headers=bob_headers,
            json={
                "server_id": "fake",
                "server_name": "fake",
                "command": "true",
                "args": [],
            },
        )
        assert resp.status_code == 403
