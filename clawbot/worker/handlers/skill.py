"""Skill handlers for installing and uninstalling skills from the registry."""

import logging
import re
import shutil
from pathlib import Path

from clawbot.agent.agent_fs import AgentFS
from clawbot.worker.handlers.schema import (
    InstallSkillRequest,
    SkillResultData,
    UninstallSkillRequest,
)
from clawlib.registry import get_skill_registry

logger = logging.getLogger(__name__)

# Allow letters, digits, dash, dot, underscore. Every other character (including
# path separators and whitespace) is replaced with "_".
_UNSAFE_CHAR_RE = re.compile(r"[^A-Za-z0-9._-]")


def _slug_to_skill_name(slug: str) -> str:
    """Extract skill directory name from slug (owner/repo@skill-name -> skill-name)."""
    if "@" in slug:
        return slug.rsplit("@", 1)[1]
    return slug.replace("/", "_").replace(".", "_") or "skill"


def _safe_skill_name(raw: str) -> str:
    """Produce a filesystem-safe skill directory name.

    Strips path separators, drops leading dots so names like ``..`` can't climb,
    replaces any remaining unsafe chars with ``_``, and falls back to ``skill``
    when nothing is left.
    """
    name = (raw or "").replace("/", "_").replace("\\", "_").strip()
    name = name.lstrip(".")  # no leading dots — blocks "..", "."
    name = _UNSAFE_CHAR_RE.sub("_", name)
    return name or "skill"


def _resolve_under(base: Path, name: str) -> Path:
    """Resolve ``base/name`` and assert the result lives under ``base``.

    Raises ``ValueError`` if ``name`` escapes ``base`` via symlinks or ``..``.
    """
    base_resolved = base.resolve()
    candidate = (base_resolved / name).resolve()
    candidate.relative_to(base_resolved)  # raises ValueError on escape
    return candidate


async def handle_install_skill(file_service: AgentFS, req: InstallSkillRequest) -> dict:
    workspace_dir = file_service.workspace_path
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Self-hosted path: write the provided SKILL.md content directly.
    if req.skill_content:
        skill_name = _safe_skill_name(_slug_to_skill_name(req.slug))
        skill_base = workspace_dir / ".agents" / "skills"
        skill_base.mkdir(parents=True, exist_ok=True)
        try:
            skill_dir = _resolve_under(skill_base, skill_name)
        except ValueError:
            logger.warning("Rejected self-hosted skill with unsafe name: slug=%s", req.slug)
            raise RuntimeError(
                f"Install failed: slug {req.slug!r} resolves outside the skills directory"
            )
        try:
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(req.skill_content, encoding="utf-8")
        except OSError as e:
            logger.warning("Self-hosted skill write failed: slug=%s err=%s", req.slug, e)
            raise RuntimeError(f"Install failed: {e}")
        return {
            "data": SkillResultData(
                slug=skill_name, message=f"Installed self-hosted skill '{skill_name}'"
            ).model_dump()
        }

    registry = get_skill_registry()
    rc, stdout, stderr = await registry.install_skill(req.slug, workspace_dir, req.env or None)
    if rc != 0:
        err_msg = (stderr or stdout or "npx skills exited with non-zero code").strip()[:500]
        logger.warning("Skill install failed: slug=%s rc=%s stderr=%s", req.slug, rc, stderr[:300])
        raise RuntimeError(f"Install failed: {err_msg}")
    installed_slug = _safe_skill_name(_slug_to_skill_name(req.slug))
    return {"data": SkillResultData(slug=installed_slug, message=stdout.strip()[:200]).model_dump()}


async def handle_uninstall_skill(file_service: AgentFS, req: UninstallSkillRequest) -> dict:
    workspace = file_service.workspace_path
    skill_name = _safe_skill_name(_slug_to_skill_name(req.slug))
    skill_base = workspace / ".agents" / "skills"
    try:
        skill_dir = _resolve_under(skill_base, skill_name)
    except (FileNotFoundError, ValueError):
        raise FileNotFoundError(f"Skill '{req.slug}' not found")
    if not skill_dir.exists():
        raise FileNotFoundError(f"Skill '{req.slug}' not found")
    shutil.rmtree(skill_dir, ignore_errors=True)
    return {"data": SkillResultData(slug=req.slug).model_dump()}
