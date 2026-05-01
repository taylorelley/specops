"""Custom agent template service: filesystem CRUD for user-authored role templates.

Custom templates live alongside the built-in marketplace roles but in the admin
storage area so they survive package upgrades. Layout::

    {storage_root}/admin/agent_templates/{template_id}/
    ├── profile/
    │   ├── AGENTS.md          # required: system prompt
    │   ├── SOUL.md            # optional: personality
    │   ├── TOOLS.md           # copied from default role
    │   ├── USER.md            # copied from default role
    │   └── config/agent.yaml  # AgentDefaults + ToolsConfig + ChannelsConfig + mcp_servers
    └── workspace/
        ├── README.md
        ├── HEARTBEAT.md
        ├── memory/{MEMORY,HISTORY}.md
        └── skills/<slug>/SKILL.md   # one per default skill

The shape mirrors ``marketplace/roles/<role>/`` exactly so the existing
``WorkspaceService.provision()`` (only patched to look up this directory as a
fallback) handles agent creation with no further changes.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from specops.core.storage import StorageBackend, get_storage_root
from specops_lib.config.schema import Config

logger = logging.getLogger(__name__)

CUSTOM_TEMPLATES_SUBDIR = "admin/agent_templates"

_ROOT = Path(__file__).resolve().parents[3]
_BUILTIN_ROLES_DIR = _ROOT / "marketplace" / "roles"
_DEFAULT_ROLE_DIR = _BUILTIN_ROLES_DIR / "default"

# Defense-in-depth slug regex (router validates first). Must match the regex
# used in specops/apis/agents/_schemas.py:_CUSTOM_TEMPLATE_ID_RE.
_SAFE_TEMPLATE_ID_RE = re.compile(r"^custom-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

# Default workspace seeds — short and meaningful so a fresh agent isn't blank.
_DEFAULT_README = """# Workspace

This is your agent's read/write workspace. Files here persist across sessions.
"""

_DEFAULT_HEARTBEAT = """# Heartbeat Tasks

This file is checked periodically by your agent. Add tasks below that you want
the agent to work on at each heartbeat.

If this file has no tasks (only headers and comments), the agent will skip the
heartbeat.

## Active Tasks

<!-- Add your periodic tasks below this line -->


## Completed

<!-- Move completed tasks here or delete them -->
"""

_DEFAULT_MEMORY = """# Long-term Memory

This file stores important information that should persist across sessions.

## User Information

(Important facts about the user)

## Preferences

(User preferences learned over time)

## Project Context

(Information about ongoing projects)

## Important Notes

(Things to remember)
"""

_DEFAULT_HISTORY = """# Event History

This file logs significant events.
"""


class CustomAgentTemplateError(Exception):
    """Raised for validation / lookup errors that should map to HTTP 4xx."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def builtin_role_ids() -> set[str]:
    """Yield ids of built-in marketplace roles. Used to reject custom-id collisions."""
    if not _BUILTIN_ROLES_DIR.is_dir():
        return set()
    return {
        p.name
        for p in _BUILTIN_ROLES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    }


class CustomAgentTemplateService:
    """Filesystem CRUD for user-authored agent templates."""

    def __init__(self, storage: StorageBackend) -> None:
        self._storage = storage

    # -- Path helpers ---------------------------------------------------------

    def _root(self) -> Path:
        return get_storage_root(self._storage) / CUSTOM_TEMPLATES_SUBDIR

    def template_dir(self, template_id: str) -> Path | None:
        """Return the directory for a custom template if it exists, else None."""
        if not _SAFE_TEMPLATE_ID_RE.match(template_id):
            return None
        path = self._root() / template_id
        return path if path.is_dir() else None

    def list_ids(self) -> list[str]:
        """List all custom template ids on disk (sorted)."""
        root = self._root()
        if not root.is_dir():
            return []
        ids: list[str] = []
        builtin = builtin_role_ids()
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            if not _SAFE_TEMPLATE_ID_RE.match(entry.name):
                continue
            if entry.name in builtin:
                # Defensive: never let a custom id shadow a built-in
                continue
            ids.append(entry.name)
        return ids

    # -- Read -----------------------------------------------------------------

    def get(self, template_id: str) -> dict[str, Any] | None:
        """Read a custom template back into a payload dict for the API."""
        tdir = self.template_dir(template_id)
        if not tdir:
            return None
        config_path = tdir / "profile" / "config" / "agent.yaml"
        config_data: dict[str, Any] = {}
        if config_path.is_file():
            try:
                config_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                config_data = {}
        meta_path = tdir / "template.yaml"
        meta: dict[str, Any] = {}
        if meta_path.is_file():
            try:
                meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError:
                meta = {}

        agents_md = (
            (tdir / "profile" / "AGENTS.md").read_text(encoding="utf-8")
            if (tdir / "profile" / "AGENTS.md").is_file()
            else ""
        )
        soul_path = tdir / "profile" / "SOUL.md"
        soul_md = soul_path.read_text(encoding="utf-8") if soul_path.is_file() else None

        skills_dir = tdir / "workspace" / "skills"
        skill_ids: list[str] = []
        if skills_dir.is_dir():
            skill_ids = sorted(p.name for p in skills_dir.iterdir() if p.is_dir())

        agents_section = (config_data.get("agents") or {}).get("defaults") or {}
        return {
            "id": template_id,
            "name": meta.get("name")
            or template_id.removeprefix("custom-").replace("-", " ").title(),
            "description": meta.get("description", ""),
            "categories": meta.get("categories") or [],
            "defaults": agents_section,
            "tools": config_data.get("tools") or None,
            "channels": config_data.get("channels") or None,
            "mcp_servers": (config_data.get("tools") or {}).get("mcpServers")
            or (config_data.get("tools") or {}).get("mcp_servers")
            or {},
            "skill_ids": skill_ids,
            "agents_md": agents_md,
            "soul_md": soul_md,
        }

    # -- Write ----------------------------------------------------------------

    def create(self, payload: dict[str, Any], skill_resolver) -> dict[str, Any]:
        """Create a new custom template. Raises on collision/validation errors."""
        template_id = payload["id"]
        if not _SAFE_TEMPLATE_ID_RE.fullmatch(template_id):
            raise CustomAgentTemplateError(
                "Invalid custom template id; expected 'custom-<slug>'",
                status_code=400,
            )
        if template_id in builtin_role_ids():
            raise CustomAgentTemplateError(
                f"Template id '{template_id}' collides with a built-in role",
                status_code=409,
            )
        if self.template_dir(template_id) is not None:
            raise CustomAgentTemplateError(
                f"Template '{template_id}' already exists",
                status_code=409,
            )
        self._write(template_id, payload, skill_resolver)
        return self._summary(template_id)

    def update(self, template_id: str, payload: dict[str, Any], skill_resolver) -> dict[str, Any]:
        """Overwrite an existing custom template in place."""
        if not _SAFE_TEMPLATE_ID_RE.fullmatch(template_id):
            raise CustomAgentTemplateError(
                "Invalid custom template id; expected 'custom-<slug>'",
                status_code=400,
            )
        if self.template_dir(template_id) is None:
            raise CustomAgentTemplateError(
                f"Custom template '{template_id}' not found", status_code=404
            )
        self._write(template_id, payload, skill_resolver)
        return self._summary(template_id)

    def delete(self, template_id: str) -> bool:
        if not _SAFE_TEMPLATE_ID_RE.fullmatch(template_id):
            return False
        tdir = self.template_dir(template_id)
        if not tdir:
            return False
        shutil.rmtree(tdir, ignore_errors=True)
        return True

    # -- Internals ------------------------------------------------------------

    def _summary(self, template_id: str) -> dict[str, Any]:
        return {
            "id": template_id,
            "value": template_id,
            "label": template_id.removeprefix("custom-").replace("-", " ").title(),
            "custom": True,
            "editable": True,
        }

    def _write(
        self,
        template_id: str,
        payload: dict[str, Any],
        skill_resolver,
    ) -> None:
        # Build the agent.yaml dict once and round-trip it through the Config
        # schema to catch invalid values (e.g. temperature out of range).
        config_dict = self._build_config_dict(payload)
        try:
            Config.model_validate(config_dict)
        except Exception as exc:
            raise CustomAgentTemplateError(
                f"Invalid template configuration: {exc}", status_code=422
            ) from exc

        # Resolve skill bundles up front so we fail before touching disk.
        skill_ids: list[str] = list(payload.get("skill_ids") or [])
        skill_bundles: dict[str, str] = {}
        missing: list[str] = []
        for slug in skill_ids:
            content = skill_resolver(slug)
            if content is None:
                missing.append(slug)
            else:
                skill_bundles[slug] = content
        if missing:
            raise CustomAgentTemplateError(
                f"Unknown or non-installable skills: {', '.join(missing)}",
                status_code=422,
            )

        root = self._root()
        root.mkdir(parents=True, exist_ok=True)
        target = root / template_id
        # Atomic-ish: write to a sibling tmp dir then swap. If a previous tmp
        # was left behind, clear it first.
        tmp = root / f".{template_id}.tmp"
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        try:
            self._materialize(tmp, payload, config_dict, skill_bundles)
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            tmp.rename(target)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

    def _build_config_dict(self, payload: dict[str, Any]) -> dict[str, Any]:
        defaults = payload.get("defaults") or {}
        tools = dict(payload.get("tools") or {})
        if payload.get("mcp_servers"):
            # Surface MCP servers under tools.mcpServers (alias used by the schema).
            tools["mcpServers"] = payload["mcp_servers"]
        config: dict[str, Any] = {
            "agents": {"defaults": defaults},
            "providers": {},
        }
        if tools:
            config["tools"] = tools
        channels = payload.get("channels")
        if channels:
            config["channels"] = channels
        return config

    def _materialize(
        self,
        target: Path,
        payload: dict[str, Any],
        config_dict: dict[str, Any],
        skill_bundles: dict[str, str],
    ) -> None:
        profile = target / "profile"
        workspace = target / "workspace"
        (profile / "config").mkdir(parents=True, exist_ok=True)
        workspace.mkdir(parents=True, exist_ok=True)

        # profile/AGENTS.md (required)
        (profile / "AGENTS.md").write_text(payload["agents_md"], encoding="utf-8")

        # profile/SOUL.md (optional; only write if non-empty)
        soul = (payload.get("soul_md") or "").strip()
        if soul:
            (profile / "SOUL.md").write_text(payload["soul_md"], encoding="utf-8")

        # profile/TOOLS.md and USER.md — copy from the default role so the
        # agent has the standard reference docs without the user retyping them.
        for shared in ("TOOLS.md", "USER.md"):
            src = _DEFAULT_ROLE_DIR / "profile" / shared
            if src.is_file():
                (profile / shared).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        # profile/config/agent.yaml
        (profile / "config" / "agent.yaml").write_text(
            yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8"
        )

        # template.yaml — sidecar metadata used by GET endpoints
        meta = {
            "id": payload["id"],
            "name": payload.get("name") or payload["id"],
            "description": payload.get("description", ""),
            "categories": payload.get("categories") or [],
        }
        (target / "template.yaml").write_text(
            yaml.safe_dump(meta, sort_keys=False), encoding="utf-8"
        )

        # workspace seeds
        (workspace / "README.md").write_text(_DEFAULT_README, encoding="utf-8")
        (workspace / "HEARTBEAT.md").write_text(_DEFAULT_HEARTBEAT, encoding="utf-8")
        memory = workspace / "memory"
        memory.mkdir(parents=True, exist_ok=True)
        (memory / "MEMORY.md").write_text(_DEFAULT_MEMORY, encoding="utf-8")
        (memory / "HISTORY.md").write_text(_DEFAULT_HISTORY, encoding="utf-8")

        # workspace/skills/<slug>/SKILL.md — provisioning remaps these to
        # workspace/.agents/skills/<slug>/SKILL.md at agent creation time.
        if skill_bundles:
            skills_root = workspace / "skills"
            skills_root.mkdir(parents=True, exist_ok=True)
            for slug, content in skill_bundles.items():
                skill_dir = skills_root / slug
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
