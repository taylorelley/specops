"""Workspace service: agent directory provisioning from templates.

Layout::

    {storage_root}/agents/{agent_id}/
    ├── .config/agent.json   <- config (secrets served via vault API at runtime)
    ├── profiles/            <- character setup (agent read-only)
    ├── workspace/           <- agent sandbox (read/write)
    ├── .sessions/           <- internal
    └── .logs/               <- audit logs

All runtime reads/writes to agent data go through the WebSocket runtime.
This service only handles initial provisioning (copying templates to storage).
"""

import json
import re
import shutil
from pathlib import Path

import yaml

from specops.core.domain.agent import AgentDef
from specops.core.storage import StorageBackend, get_storage_root

AGENTS_DIR = "agents"

_ROOT = Path(__file__).resolve().parents[3]
_ROLES_TEMPLATES_DIR = _ROOT / "marketplace" / "roles"
_BUILTIN_WORKSPACE_TEMPLATE = _ROLES_TEMPLATES_DIR / "default" / "workspace"
_BUILTIN_PROFILE_TEMPLATE = _ROLES_TEMPLATES_DIR / "default" / "profile"
_CUSTOM_TEMPLATES_SUBDIR = "admin/agent_templates"
# Reject ids with path separators, leading dots, etc. before joining to disk.
_SAFE_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class WorkspaceService:
    """Agent directory provisioning from templates."""

    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    # -- Provisioning --

    def _resolve_template_root(self, template: str) -> Path | None:
        """Locate a template directory by id, checking built-in roles first then custom.

        Validates the template id as a single safe path component to prevent
        directory traversal (e.g. "../../etc") from escaping the template roots.
        """
        if not template or not _SAFE_TEMPLATE_NAME_RE.fullmatch(template):
            return None
        builtin = _ROLES_TEMPLATES_DIR / template
        if builtin.is_dir():
            return builtin
        custom = get_storage_root(self._storage) / _CUSTOM_TEMPLATES_SUBDIR / template
        if custom.is_dir():
            return custom
        return None

    def _get_profile_template_dir(self, template: str | None = None) -> Path | None:
        # When a specific template is requested, resolve it strictly: if it
        # cannot be located (deleted, stale, malformed slug) return None instead
        # of silently provisioning from the built-in default — that would leave
        # the caller with a generic agent and no signal that the requested
        # template went missing.
        if template:
            root = self._resolve_template_root(template)
            if root is None:
                return None
            role_profile = root / "profile"
            return role_profile if role_profile.is_dir() else None
        if _BUILTIN_PROFILE_TEMPLATE.is_dir():
            return _BUILTIN_PROFILE_TEMPLATE
        return None

    def _get_workspace_template_dir(self, template: str | None = None) -> Path | None:
        if template:
            root = self._resolve_template_root(template)
            if root is None:
                return None
            role_workspace = root / "workspace"
            return role_workspace if role_workspace.is_dir() else None
        if _BUILTIN_WORKSPACE_TEMPLATE.is_dir():
            return _BUILTIN_WORKSPACE_TEMPLATE
        return None

    def provision(self, base_path: str, *, agent_id: str = "", template: str | None = None) -> None:
        """Populate agent directory from profile and workspace templates.

        Creates agents/{base_path}/.config/, profiles/, workspace/, .sessions/, .logs/
        and copies template files. Config from profile template goes to .config/agent.json.
        If template is set (e.g. "sre"), uses templates/roles/{template}/profile and workspace.

        Raises ``ValueError`` when ``template`` is explicitly provided but cannot
        be resolved (deleted or stale custom id, malformed slug). We refuse to
        silently fall back to the built-in default in that case — the caller
        asked for a specific role and should know if it's gone missing.
        """
        if template and self._resolve_template_root(template) is None:
            raise ValueError(f"Unknown agent template: {template!r}")

        root = get_storage_root(self._storage)
        agent_prefix = f"{AGENTS_DIR}/{base_path}"
        _ = root / agent_prefix  # agent_root, used implicitly via storage paths

        profile_tpl = self._get_profile_template_dir(template)
        if profile_tpl:
            for path in profile_tpl.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(profile_tpl)
                    key = str(rel).replace("\\", "/")
                    if key.startswith("config/"):
                        if agent_id:
                            dest = f"{agent_prefix}/.config/{key.removeprefix('config/')}"
                            if dest.endswith(".yaml"):
                                dest = dest.replace(".yaml", ".json")
                            try:
                                if path.suffix in (".yaml", ".yml"):
                                    data = yaml.safe_load(path.read_text()) or {}
                                    self._storage.write_sync(
                                        dest, json.dumps(data, indent=2).encode("utf-8")
                                    )
                                else:
                                    self._storage.write_sync(dest, path.read_bytes())
                            except Exception:
                                pass
                    else:
                        dest = f"{agent_prefix}/profiles/{key}"
                        try:
                            self._storage.write_sync(dest, path.read_bytes())
                        except Exception:
                            pass

        workspace_tpl = self._get_workspace_template_dir(template)
        if workspace_tpl:
            for path in workspace_tpl.rglob("*"):
                if path.is_file():
                    rel = path.relative_to(workspace_tpl)
                    key = str(rel).replace("\\", "/")
                    # Skills: workspace/skills/<name>/ -> workspace/.agents/skills/<name>/
                    if key.startswith("skills/") and "/" in key:
                        skill_name = key.split("/")[1]
                        rest = "/".join(key.split("/")[2:])
                        dest = f"{agent_prefix}/workspace/.agents/skills/{skill_name}/{rest}"
                    # Memory: workspace/memory/ -> workspace/.agents/memory/
                    elif key.startswith("memory/"):
                        rest = key.removeprefix("memory/")
                        dest = f"{agent_prefix}/workspace/.agents/memory/{rest}"
                    # HEARTBEAT: workspace/HEARTBEAT.md -> workspace/.agents/HEARTBEAT.md
                    elif key == "HEARTBEAT.md":
                        dest = f"{agent_prefix}/workspace/.agents/HEARTBEAT.md"
                    else:
                        dest = f"{agent_prefix}/workspace/{key}"
                    try:
                        self._storage.write_sync(dest, path.read_bytes())
                    except Exception:
                        pass

        for sub in (".sessions", ".logs"):
            try:
                self._storage.write_sync(f"{agent_prefix}/{sub}/.gitkeep", b"")
            except Exception:
                pass

    def reset_agent(self, agent: AgentDef, template: str | None = None) -> None:
        """Delete agent directory and re-provision from templates."""
        root = get_storage_root(self._storage)
        bp = agent.base_path or agent.id
        agent_root = root / AGENTS_DIR / bp
        if agent_root.exists():
            shutil.rmtree(agent_root, ignore_errors=True)
        self.provision(bp, agent_id=agent.id, template=template)
