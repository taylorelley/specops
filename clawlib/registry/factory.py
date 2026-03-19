"""Factory for registry implementations. Returns configured SkillRegistry, MCPRegistry, and SoftwareRegistry."""

from clawlib.mcpregistry.official_mcp import OfficialMCPRegistry
from clawlib.registry.protocols import MCPRegistry, SkillRegistry, SoftwareRegistry
from clawlib.skillregistry import SkillsShRegistry
from clawlib.softwareregistry import YamlSoftwareRegistry
from clawlib.storage import get_storage_backend, get_storage_root

_skill_registry: SkillsShRegistry | None = None
_mcp_registry: OfficialMCPRegistry | None = None
_software_registry: YamlSoftwareRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """Return the SkillRegistry implementation (agentskill.sh)."""
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillsShRegistry()
    return _skill_registry


def get_mcp_registry() -> MCPRegistry:
    """Return the MCPRegistry implementation (official registry)."""
    global _mcp_registry
    if _mcp_registry is None:
        _mcp_registry = OfficialMCPRegistry()
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
