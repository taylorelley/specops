"""Tests for the custom agent templates feature.

Covers:
- Filesystem CRUD via :class:`CustomAgentTemplateService`.
- /api/templates GET (merged), /api/templates/custom, /api/templates/{id},
  POST/PUT/DELETE /api/templates.
- WorkspaceService provisioning resolves a custom template by id.
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
    registry_factory._skill_registry = None  # type: ignore[attr-defined]
    yield data_dir
    db_module.get_database.cache_clear()
    registry_factory._plan_template_registry = None  # type: ignore[attr-defined]
    registry_factory._skill_registry = None  # type: ignore[attr-defined]


@pytest.fixture
def client(isolated_data_dir: Path):
    from specops.app import create_app

    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def admin_user(client: TestClient):
    from specops.auth import hash_password
    from specops.core.database import get_database
    from specops.core.store.users import UserStore

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


def _basic_payload(template_id: str = "custom-data-scientist", **overrides) -> dict:
    payload = {
        "id": template_id,
        "name": "Data Scientist",
        "description": "Analyses data sets",
        "categories": ["analytics"],
        "defaults": {
            "model": "anthropic/claude-opus-4-5",
            "temperature": 0.4,
            "maxTokens": 8192,
            "maxToolIterations": 25,
            "memoryWindow": 50,
        },
        "agents_md": "# Agent Instructions\n\nYou are a data scientist.\n",
    }
    payload.update(overrides)
    return payload


class TestCustomAgentTemplateService:
    def test_create_writes_expected_files(self, isolated_data_dir: Path):
        from specops.core.services.agent_template_service import CustomAgentTemplateService
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)

        result = svc.create(_basic_payload(), skill_resolver=lambda _slug: None)
        assert result["id"] == "custom-data-scientist"

        tdir = isolated_data_dir / "admin" / "agent_templates" / "custom-data-scientist"
        assert (tdir / "profile" / "AGENTS.md").is_file()
        assert (tdir / "profile" / "config" / "agent.yaml").is_file()
        assert (tdir / "workspace" / "README.md").is_file()
        assert (tdir / "workspace" / "HEARTBEAT.md").is_file()
        assert (tdir / "workspace" / "memory" / "MEMORY.md").is_file()
        assert (tdir / "template.yaml").is_file()

    def test_collision_with_builtin_rejected(self, isolated_data_dir: Path):
        from specops.core.services.agent_template_service import (
            CustomAgentTemplateError,
            CustomAgentTemplateService,
        )
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)
        # `default` is a built-in role; the regex requires `custom-` prefix anyway,
        # but the service also checks against built-in ids defensively.
        with pytest.raises(CustomAgentTemplateError) as exc:
            svc.create(_basic_payload(template_id="default"), skill_resolver=lambda _: None)
        assert exc.value.status_code in (409, 400)

    def test_invalid_temperature_raises_422(self, isolated_data_dir: Path):
        from specops.core.services.agent_template_service import (
            CustomAgentTemplateError,
            CustomAgentTemplateService,
        )
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)
        bad = _basic_payload()
        bad["defaults"]["temperature"] = "not-a-number"  # type: ignore[index]
        with pytest.raises(CustomAgentTemplateError) as exc:
            svc.create(bad, skill_resolver=lambda _: None)
        assert exc.value.status_code == 422

    def test_skill_resolver_writes_skill_md(self, isolated_data_dir: Path):
        from specops.core.services.agent_template_service import CustomAgentTemplateService
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)

        def resolver(slug: str) -> str | None:
            if slug == "data-cleaning":
                return "---\nname: data-cleaning\n---\nDo data cleaning."
            return None

        payload = _basic_payload()
        payload["skill_ids"] = ["data-cleaning"]
        svc.create(payload, skill_resolver=resolver)
        skill_md = (
            isolated_data_dir
            / "admin"
            / "agent_templates"
            / "custom-data-scientist"
            / "workspace"
            / "skills"
            / "data-cleaning"
            / "SKILL.md"
        )
        assert skill_md.is_file()
        assert "Do data cleaning" in skill_md.read_text()

    def test_missing_skill_rejected(self, isolated_data_dir: Path):
        from specops.core.services.agent_template_service import (
            CustomAgentTemplateError,
            CustomAgentTemplateService,
        )
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)
        payload = _basic_payload()
        payload["skill_ids"] = ["does-not-exist"]
        with pytest.raises(CustomAgentTemplateError) as exc:
            svc.create(payload, skill_resolver=lambda _slug: None)
        assert exc.value.status_code == 422

    def test_update_overwrites(self, isolated_data_dir: Path):
        from specops.core.services.agent_template_service import CustomAgentTemplateService
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)
        svc.create(_basic_payload(), skill_resolver=lambda _: None)
        updated = _basic_payload(name="Renamed")
        updated["agents_md"] = "# Renamed\n"
        svc.update("custom-data-scientist", updated, skill_resolver=lambda _: None)
        tdir = isolated_data_dir / "admin" / "agent_templates" / "custom-data-scientist"
        assert "# Renamed" in (tdir / "profile" / "AGENTS.md").read_text()

    def test_delete_removes_directory(self, isolated_data_dir: Path):
        from specops.core.services.agent_template_service import CustomAgentTemplateService
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)
        svc.create(_basic_payload(), skill_resolver=lambda _: None)
        assert svc.delete("custom-data-scientist") is True
        assert svc.template_dir("custom-data-scientist") is None
        assert svc.delete("custom-does-not-exist") is False


class TestCustomAgentTemplateEndpoints:
    def test_create_appears_in_merged_list(self, client: TestClient, auth_headers):
        resp = client.post("/api/templates", headers=auth_headers, json=_basic_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["custom"] is True

        resp = client.get("/api/templates", headers=auth_headers)
        assert resp.status_code == 200
        merged = resp.json()
        ids = {t["value"] for t in merged}
        assert "default" in ids  # built-in still listed
        assert "custom-data-scientist" in ids
        custom_entry = next(t for t in merged if t["value"] == "custom-data-scientist")
        assert custom_entry["custom"] is True
        assert custom_entry["editable"] is True

    def test_custom_only_endpoint(self, client: TestClient, auth_headers):
        client.post("/api/templates", headers=auth_headers, json=_basic_payload())
        resp = client.get("/api/templates/custom", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == "custom-data-scientist"
        assert body[0]["agents_md"].startswith("# Agent Instructions")

    def test_get_detail_returns_files_and_payload(self, client: TestClient, auth_headers):
        client.post("/api/templates", headers=auth_headers, json=_basic_payload())
        resp = client.get("/api/templates/custom-data-scientist", headers=auth_headers)
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["custom"] is True
        profile_paths = {f["path"] for f in detail["profileFiles"]}
        assert "AGENTS.md" in profile_paths
        assert "config/agent.yaml" in profile_paths
        assert detail.get("payload", {}).get("id") == "custom-data-scientist"

    def test_invalid_id_rejected(self, client: TestClient, auth_headers):
        # Missing required `custom-` prefix
        bad = _basic_payload(template_id="data-scientist")
        resp = client.post("/api/templates", headers=auth_headers, json=bad)
        assert resp.status_code == 422

    def test_duplicate_id_returns_409(self, client: TestClient, auth_headers):
        client.post("/api/templates", headers=auth_headers, json=_basic_payload())
        resp = client.post("/api/templates", headers=auth_headers, json=_basic_payload())
        assert resp.status_code == 409

    def test_update_and_delete(self, client: TestClient, auth_headers):
        client.post("/api/templates", headers=auth_headers, json=_basic_payload())

        renamed = _basic_payload(name="Renamed Scientist")
        resp = client.put(
            "/api/templates/custom-data-scientist",
            headers=auth_headers,
            json=renamed,
        )
        assert resp.status_code == 200

        resp = client.delete("/api/templates/custom-data-scientist", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        resp = client.get("/api/templates/custom-data-scientist", headers=auth_headers)
        assert resp.status_code == 404

    def test_cannot_delete_builtin(self, client: TestClient, auth_headers):
        resp = client.delete("/api/templates/default", headers=auth_headers)
        assert resp.status_code == 400

    def test_update_url_body_mismatch_400(self, client: TestClient, auth_headers):
        client.post("/api/templates", headers=auth_headers, json=_basic_payload())
        body = _basic_payload(template_id="custom-other")
        resp = client.put("/api/templates/custom-data-scientist", headers=auth_headers, json=body)
        assert resp.status_code == 400

    def test_requires_auth(self, client: TestClient):
        assert client.get("/api/templates").status_code == 401
        assert client.post("/api/templates", json=_basic_payload()).status_code == 401

    def test_writes_require_admin(self, client: TestClient, admin_user):
        """Non-admin users get 403 on POST/PUT/DELETE; reads stay accessible."""
        from specops.auth import hash_password
        from specops.core.database import get_database
        from specops.core.store.users import UserStore

        UserStore(get_database()).create_user(
            username="someuser", password_hash=hash_password("pw"), role="user"
        )
        login = client.post("/api/auth/login", data={"username": "someuser", "password": "pw"})
        user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        # Reads stay accessible to any authed user.
        assert client.get("/api/templates", headers=user_headers).status_code == 200
        # Writes are admin-only.
        assert (
            client.post("/api/templates", headers=user_headers, json=_basic_payload()).status_code
            == 403
        )
        assert (
            client.put(
                "/api/templates/custom-data-scientist",
                headers=user_headers,
                json=_basic_payload(),
            ).status_code
            == 403
        )
        assert (
            client.delete("/api/templates/custom-data-scientist", headers=user_headers).status_code
            == 403
        )

    def test_secrets_redacted_in_read_endpoints(
        self, client: TestClient, auth_headers, isolated_data_dir: Path
    ):
        """MCP env values, channel tokens, and raw agent.yaml never leak via reads."""
        from specops.core.services.agent_template_service import CustomAgentTemplateService
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)
        payload = _basic_payload()
        payload["mcp_servers"] = {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "ghp_supersecret_xxx"},
                "url": "",
                "headers": {"Authorization": "Bearer abc.def.ghi"},
            }
        }
        payload["channels"] = {"telegram": {"enabled": True, "bot_token": "bot:secret"}}
        svc.create(payload, skill_resolver=lambda _: None)

        # /api/templates/custom — full payload
        resp = client.get("/api/templates/custom", headers=auth_headers)
        assert resp.status_code == 200
        entry = resp.json()[0]
        mcp_env = entry["mcp_servers"]["github"]["env"]
        assert mcp_env["GITHUB_TOKEN"] == "***", "MCP env value not redacted"
        mcp_headers = entry["mcp_servers"]["github"]["headers"]
        assert mcp_headers["Authorization"] == "***", "MCP header value not redacted"
        # Channel bot_token is a known secret_field and should be redacted.
        tg_token = entry["channels"]["telegram"]["bot_token"]
        assert tg_token != "bot:secret"
        assert "***" in tg_token

        # /api/templates/{id} — config file content must not leak raw YAML
        resp = client.get("/api/templates/custom-data-scientist", headers=auth_headers)
        assert resp.status_code == 200
        detail = resp.json()
        config_files = [f for f in detail["profileFiles"] if f["path"] == "config/agent.yaml"]
        assert len(config_files) == 1
        assert "ghp_supersecret_xxx" not in config_files[0]["content"]
        assert "bot:secret" not in config_files[0]["content"]
        # Structured payload also redacted.
        assert detail["payload"]["mcp_servers"]["github"]["env"]["GITHUB_TOKEN"] == "***"

    def test_put_roundtrip_preserves_redacted_secrets(
        self, client: TestClient, auth_headers, isolated_data_dir: Path
    ):
        """Saving an edit after fetching a redacted GET must NOT wipe stored secrets.

        Reproduces the round-trip:
          1. Create a template with real secrets.
          2. GET it (returns redacted ``***``).
          3. PUT the redacted body verbatim back.
          4. Real secrets are still on disk.
        """
        from specops.core.services.agent_template_service import CustomAgentTemplateService
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)
        payload = _basic_payload()
        payload["mcp_servers"] = {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "ghp_real_secret"},
                "url": "",
                "headers": {"Authorization": "Bearer real.jwt.value"},
            }
        }
        payload["channels"] = {"telegram": {"enabled": True, "bot_token": "bot:realsecret"}}
        svc.create(payload, skill_resolver=lambda _: None)

        # Round-trip via the API: GET → PUT
        get_resp = client.get("/api/templates/custom-data-scientist", headers=auth_headers)
        assert get_resp.status_code == 200
        redacted_body = get_resp.json()["payload"]
        # Sanity: GET payload is redacted.
        assert redacted_body["mcp_servers"]["github"]["env"]["GITHUB_TOKEN"] == "***"
        # The PUT body needs the same shape as POST.
        redacted_body.pop("id", None)
        put_body = {**_basic_payload(), **redacted_body, "id": "custom-data-scientist"}
        put_body["name"] = "Renamed Scientist"

        put_resp = client.put(
            "/api/templates/custom-data-scientist",
            headers=auth_headers,
            json=put_body,
        )
        assert put_resp.status_code == 200, put_resp.text

        # On-disk secrets must still be the real values.
        on_disk = svc.get("custom-data-scientist")
        assert on_disk is not None
        assert on_disk["mcp_servers"]["github"]["env"]["GITHUB_TOKEN"] == "ghp_real_secret"
        assert (
            on_disk["mcp_servers"]["github"]["headers"]["Authorization"] == "Bearer real.jwt.value"
        )
        assert on_disk["channels"]["telegram"]["bot_token"] == "bot:realsecret"
        # And the unrelated change actually applied.
        assert on_disk["name"] == "Renamed Scientist"

    def test_put_drops_redacted_keys_with_no_existing_value(self, client: TestClient, auth_headers):
        """If the PUT body contains a redacted key the service has never seen,
        we drop the placeholder rather than persisting ``***``."""
        client.post("/api/templates", headers=auth_headers, json=_basic_payload())
        body = _basic_payload()
        body["mcp_servers"] = {
            "fresh": {
                "command": "x",
                "args": [],
                "env": {"NEW_KEY": "***"},
                "url": "",
                "headers": {},
            }
        }
        resp = client.put("/api/templates/custom-data-scientist", headers=auth_headers, json=body)
        assert resp.status_code == 200
        # Round-trip GET to confirm placeholder did not get persisted.
        detail = client.get("/api/templates/custom-data-scientist", headers=auth_headers).json()[
            "payload"
        ]
        assert "NEW_KEY" not in detail["mcp_servers"]["fresh"].get("env", {})

    def test_path_traversal_rejected_via_service(self, isolated_data_dir: Path):
        """Crafted ids with separators are rejected before any filesystem write."""
        from specops.core.services.agent_template_service import (
            CustomAgentTemplateError,
            CustomAgentTemplateService,
        )
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        svc = CustomAgentTemplateService(storage)
        for bad_id in ("../escape", "custom-../etc", "custom-a/b", "custom-..", ""):
            with pytest.raises(CustomAgentTemplateError):
                payload = _basic_payload(template_id=bad_id)
                svc.create(payload, skill_resolver=lambda _: None)


class TestProvisioningWithCustomTemplate:
    def test_provision_uses_custom_template(self, isolated_data_dir: Path):
        from specops.core.services.agent_template_service import CustomAgentTemplateService
        from specops.core.services.workspace_service import WorkspaceService
        from specops.core.storage import LocalStorage

        storage = LocalStorage(str(isolated_data_dir))
        CustomAgentTemplateService(storage).create(_basic_payload(), skill_resolver=lambda _: None)

        ws = WorkspaceService(storage)
        ws.provision("agent-1", agent_id="agent-1", template="custom-data-scientist")

        agent_root = isolated_data_dir / "agents" / "agent-1"
        assert (agent_root / "profiles" / "AGENTS.md").is_file()
        assert "data scientist" in (agent_root / "profiles" / "AGENTS.md").read_text().lower()
        assert (agent_root / ".config" / "agent.json").is_file()
        # Workspace seeds were copied.
        assert (agent_root / "workspace" / "README.md").is_file()

    def test_resolve_template_root_rejects_traversal(self, isolated_data_dir: Path):
        """Bogus template ids never escape the marketplace/admin roots."""
        from specops.core.services.workspace_service import WorkspaceService
        from specops.core.storage import LocalStorage

        ws = WorkspaceService(LocalStorage(str(isolated_data_dir)))
        for bad in ("../etc", "..", "a/b", "default/../etc"):
            assert ws._resolve_template_root(bad) is None

    def test_provision_raises_on_unknown_template(self, isolated_data_dir: Path):
        """A specific template id that can't be resolved fails loudly instead of
        silently provisioning the default seeds."""
        from specops.core.services.workspace_service import WorkspaceService
        from specops.core.storage import LocalStorage

        ws = WorkspaceService(LocalStorage(str(isolated_data_dir)))
        with pytest.raises(ValueError, match="Unknown agent template"):
            ws.provision("agent-x", agent_id="agent-x", template="custom-does-not-exist")
        # Agent dir was not created with default seeds.
        assert not (isolated_data_dir / "agents" / "agent-x" / "profiles" / "AGENTS.md").is_file()

    def test_create_agent_endpoint_returns_400_for_unknown_template(
        self, client: TestClient, auth_headers
    ):
        """``POST /api/agents`` surfaces unknown-template as 400, not a 500
        traceback or a half-provisioned agent."""
        resp = client.post(
            "/api/agents",
            headers=auth_headers,
            json={"name": "x", "template": "custom-does-not-exist"},
        )
        assert resp.status_code == 400
        assert "Unknown agent template" in resp.json()["detail"]
        # No agent was persisted.
        listing = client.get("/api/agents", headers=auth_headers).json()
        assert all(a.get("name") != "x" for a in listing)
