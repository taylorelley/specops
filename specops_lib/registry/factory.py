"""Factory for registry implementations. Returns configured SkillRegistry, MCPRegistry, SoftwareRegistry, PlanTemplateRegistry, and ApiToolRegistry."""

from specops_lib.apitoolregistry import YamlApiToolRegistry
from specops_lib.mcpregistry.official_mcp import OfficialMCPRegistry
from specops_lib.mcpregistry.yaml_catalog import YamlMCPRegistry
from specops_lib.plantemplateregistry import YamlPlanTemplateRegistry
from specops_lib.registry.protocols import (
    ApiToolRegistry,
    MCPRegistry,
    PlanTemplateRegistry,
    SkillRegistry,
    SoftwareRegistry,
)
from specops_lib.skillregistry import SkillsShRegistry, YamlSkillRegistry
from specops_lib.softwareregistry import YamlSoftwareRegistry
from specops_lib.storage import get_storage_backend, get_storage_root

_skill_registry: YamlSkillRegistry | None = None
_mcp_registry: YamlMCPRegistry | None = None
_software_registry: YamlSoftwareRegistry | None = None
_plan_template_registry: YamlPlanTemplateRegistry | None = None
_api_tool_registry: YamlApiToolRegistry | None = None


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


def get_api_tool_registry() -> ApiToolRegistry:
    """Return the ApiToolRegistry implementation (marketplace YAML catalog + custom entries)."""
    global _api_tool_registry
    if _api_tool_registry is None:
        storage = get_storage_backend()
        root = get_storage_root(storage)
        custom_path = root / "admin" / "custom_api_tools.yaml"
        _api_tool_registry = YamlApiToolRegistry(custom_catalog_path=custom_path)
    return _api_tool_registry
