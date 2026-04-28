"""Pydantic request/response schemas for agent endpoints."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from specops_lib.config.schema import (
    AgentDefaults,
    ChannelsConfig,
    MCPServerConfig,
    ToolsConfig,
)

# Slug rule for custom agent templates: must be prefixed with `custom-` so
# they cannot collide with built-in marketplace roles or smuggle path segments.
_CUSTOM_TEMPLATE_ID_RE = re.compile(r"^custom-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class AgentCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str = ""
    template: str | None = None
    mode: str | None = None
    color: str = ""


class AgentUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    description: str | None = None
    color: str | None = None
    mode: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    max_tool_iterations: int | None = None
    memory_window: int | None = None
    fault_tolerance: dict | None = None
    enabled: bool | None = None
    onboarding_completed: bool | None = None
    tools: dict | None = None
    skills: dict | None = None
    channels: ChannelsConfig | None = None
    providers: dict | None = None
    heartbeat: dict | None = None
    security: dict | None = None


class CustomAgentTemplateRequest(BaseModel):
    """Request body for creating or updating a custom agent template."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Slug; must start with 'custom-'")
    name: str = Field(..., min_length=1)
    description: str = ""
    categories: list[str] = Field(default_factory=list)
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)
    tools: ToolsConfig | None = None
    channels: ChannelsConfig | None = None
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict, alias="mcpServers")
    skill_ids: list[str] = Field(default_factory=list, alias="skillIds")
    agents_md: str = Field(..., min_length=1, alias="agentsMd")
    soul_md: str | None = Field(default=None, alias="soulMd")

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if not v:
            raise ValueError("id must not be empty")
        if not _CUSTOM_TEMPLATE_ID_RE.match(v):
            raise ValueError("id must match 'custom-<slug>' (lowercase letters, digits, dashes)")
        return v


class A2AMessageBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str


# Kept separate from A2AMessageBody: user chat and A2A share a shape today but
# are expected to diverge (session/stream/attachments on chat; peer context on A2A).
class ChatMessageBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
