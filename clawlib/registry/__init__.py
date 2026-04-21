"""Registry abstraction for Skill, MCP, Software, and PlanTemplate marketplaces."""

from clawlib.registry.factory import (
    get_mcp_registry,
    get_plan_template_registry,
    get_skill_registry,
    get_software_registry,
)
from clawlib.registry.protocols import (
    MCPRegistry,
    PlanTemplateRegistry,
    SkillRegistry,
    SoftwareRegistry,
)

__all__ = [
    "MCPRegistry",
    "PlanTemplateRegistry",
    "SkillRegistry",
    "SoftwareRegistry",
    "get_mcp_registry",
    "get_plan_template_registry",
    "get_skill_registry",
    "get_software_registry",
]
