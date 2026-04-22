"""Factory for registry implementations. Returns configured SkillRegistry, MCPRegistry, SoftwareRegistry, and PlanTemplateRegistry."""

from clawlib.mcpregistry.official_mcp import OfficialMCPRegistry
from clawlib.mcpregistry.yaml_catalog import YamlMCPRegistry
from clawlib.plantemplateregistry import YamlPlanTemplateRegistry
from clawlib.registry.protocols import (
    MCPRegistry,
    PlanTemplateRegistry,
    SkillRegistry,
    SoftwareRegistry,
)
from clawlib.skillregistry import SkillsShRegistry, YamlSkillRegistry
from clawlib.softwareregistry import YamlSoftwareRegistry
from clawlib.storage import get_storage_backend, get_storage_root

_skill_registry: YamlSkillRegistry | None = None
_mcp_registry: YamlMCPRegistry | None = None
_software_registry: YamlSoftwareRegistry | None = None
_plan_template_registry: YamlPlanTemplateRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Return the SkillRegistry implementation (agentskill.sh + self-hosted YAML catalog)."""
    global _skill_registry
    if _skill_registry is None:
        storage = get_storage_backend()
        root = get_storage_root(storage)
        custom_path = root / "admin" / "custom_skills_catalog.yaml"
        _skill_registry = YamlSkillRegistry(
            custom_catalog_path=custom_path,
            inner=SkillsShRegistry(),
        )
    return _skill_registry


def get_mcp_registry() -> MCPRegistry:
    """Return the MCPRegistry implementation (official registry + self-hosted YAML catalog)."""
    global _mcp_registry
    if _mcp_registry is None:
        storage = get_storage_backend()
        root = get_storage_root(storage)
        custom_path = root / "admin" / "custom_mcp_servers_catalog.yaml"
        _mcp_registry = YamlMCPRegistry(
            custom_catalog_path=custom_path,
            inner=OfficialMCPRegistry(),
        )
    return _mcp_registry


def get_software_registry() -> SoftwareRegistry:
    """Return the SoftwareRegistry implementation (marketplace YAML catalog + custom entries)."""
    global _software_registry
    if _software_registry is None:
        storage = get_storage_backend()
        root = get_storage_root(storage)
        custom_path = root / "admin" / "custom_software_catalog.yaml"
        _software_registry = YamlSoftwareRegistry(custom_catalog_path=custom_path)
    return _software_registry


def get_plan_template_registry() -> PlanTemplateRegistry:
    """Return the PlanTemplateRegistry implementation (marketplace YAML catalog + custom entries)."""
    global _plan_template_registry
    if _plan_template_registry is None:
        storage = get_storage_backend()
        root = get_storage_root(storage)
        custom_path = root / "admin" / "custom_plan_templates.yaml"
        _plan_template_registry = YamlPlanTemplateRegistry(custom_catalog_path=custom_path)
    return _plan_template_registry
