"""Configuration schema using Pydantic (shared between admin and specialagent)."""

from typing import ClassVar, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings


class Base(BaseModel):
    """Base model using snake_case keys (standard Python convention).

    Subclasses that contain secret values (tokens, keys, passwords) declare them
    via the class attribute secret_fields so redaction and merge-preserve logic
    can be schema-driven instead of hardcoded key names.
    """

    model_config = ConfigDict(populate_by_name=True)
    secret_fields: ClassVar[frozenset[str]] = frozenset()


class GuardrailRef(Base):
    """One guardrail attachment.

    Resolution at agent start (in ``GuardrailRunner.resolve_refs``):
      * If ``name`` matches a registered guardrail, that wins.
      * Else, ``pattern`` defines an inline ``RegexGuardrail``.
      * Else, ``prompt`` defines an inline ``LLMGuardrail``.

    ``on_fail`` controls what happens when the guardrail fails;
    ``max_retries`` bounds the ``retry`` mode per (step, guardrail).
    """

    name: str = ""
    on_fail: str = "retry"
    max_retries: int = Field(default=3, alias="maxRetries")
    pattern: str | None = None
    prompt: str | None = None
    regex_mode: str = Field(default="block", alias="regexMode")


class WhatsAppConfig(Base):
    secret_fields: ClassVar[frozenset[str]] = frozenset()
    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")


class TelegramConfig(Base):
    secret_fields: ClassVar[frozenset[str]] = frozenset({"token"})
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")
    proxy: str | None = None
    group_policy: str = "mention"


class FeishuConfig(Base):
    secret_fields: ClassVar[frozenset[str]] = frozenset(
        {"app_id", "app_secret", "encrypt_key", "verification_token"}
    )
    enabled: bool = False
    app_id: str = Field(default="", alias="appId")
    app_secret: str = Field(default="", alias="appSecret")
    encrypt_key: str = ""
    verification_token: str = ""
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")


class DiscordConfig(Base):
    secret_fields: ClassVar[frozenset[str]] = frozenset({"token"})
    enabled: bool = False
    token: str = ""
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377


class EmailConfig(Base):
    secret_fields: ClassVar[frozenset[str]] = frozenset({"imap_password", "smtp_password"})
    enabled: bool = False
    consent_granted: bool = False
    imap_host: str = Field(default="", alias="imapHost")
    imap_port: int = Field(default=993, alias="imapPort")
    imap_username: str = Field(default="", alias="imapUsername")
    imap_password: str = Field(default="", alias="imapPassword")
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    smtp_host: str = Field(default="", alias="smtpHost")
    smtp_port: int = Field(default=587, alias="smtpPort")
    smtp_username: str = Field(default="", alias="smtpUsername")
    smtp_password: str = Field(default="", alias="smtpPassword")
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = Field(default="", alias="fromAddress")
    auto_reply_enabled: bool = True
    poll_interval_seconds: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")


class SlackDMConfig(Base):
    enabled: bool = True
    policy: str = "open"
    allow_from: list[str] = Field(default_factory=list)


class ZaloUserConfig(Base):
    """Zalo Personal (zalouser) channel config — uses Node.js bridge with zca-js."""

    secret_fields: ClassVar[frozenset[str]] = frozenset()
    enabled: bool = False
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")
    group_policy: str = "mention"  # mention | open | disabled


class ZaloConfig(Base):
    """Zalo Official Account (Bot API) channel config."""

    secret_fields: ClassVar[frozenset[str]] = frozenset({"bot_token"})
    enabled: bool = False
    bot_token: str = Field(default="", alias="botToken")
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")
    group_policy: str = "allowlist"  # open | allowlist | disabled
    group_allow_from: list[str] = Field(default_factory=list, alias="groupAllowFrom")
    media_max_mb: int = Field(default=5, alias="mediaMaxMb")


class TeamsConfig(Base):
    """Microsoft Teams channel (Bot Framework)."""

    secret_fields: ClassVar[frozenset[str]] = frozenset({"app_id", "app_password"})
    enabled: bool = False
    app_id: str = Field(default="", alias="appId")
    app_password: str = Field(default="", alias="appPassword")
    allow_from: list[str] = Field(default_factory=list, alias="allowFrom")


class SlackConfig(Base):
    secret_fields: ClassVar[frozenset[str]] = frozenset({"bot_token", "app_token"})
    enabled: bool = False
    mode: str = "socket"
    webhook_path: str = "/slack/events"
    bot_token: str = Field(default="", alias="botToken")
    app_token: str = Field(default="", alias="appToken")
    user_token_read_only: bool = True
    reply_in_thread: bool = Field(default=True, alias="replyInThread")
    react_emoji: str = "eyes"
    group_policy: str = "mention"
    group_allow_from: list[str] = Field(default_factory=list)
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)

    @field_validator("user_token_read_only", "reply_in_thread", mode="before")
    @classmethod
    def _coerce_slack_bool(cls, v: object) -> object:
        """Accept string/int so API payloads from UI or stored config parse correctly."""
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        if isinstance(v, int):
            return bool(v)
        return v


class FaultToleranceConfig(Base):
    max_attempts: int = 3
    backoff_factor: float = 1.0


class ChannelsConfig(Base):
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    zalo: ZaloConfig = Field(default_factory=ZaloConfig)
    zalouser: ZaloUserConfig = Field(default_factory=ZaloUserConfig)
    teams: TeamsConfig = Field(default_factory=TeamsConfig)


class AgentDefaults(Base):
    model: str = "anthropic/claude-opus-4-5"
    max_tokens: int = Field(default=8192, alias="maxTokens")
    temperature: float = 0.7
    max_tool_iterations: int = Field(default=20, alias="maxToolIterations")
    memory_window: int = Field(default=50, alias="memoryWindow")
    max_tool_output_chars: int = Field(default=16000, alias="maxToolOutputChars")
    fault_tolerance: FaultToleranceConfig = Field(
        default_factory=FaultToleranceConfig, alias="faultTolerance"
    )
    # Guardrails applied to the final assistant message (Position.AGENT_OUTPUT).
    guardrails: list[GuardrailRef] = Field(default_factory=list)


class AgentsConfig(Base):
    defaults: AgentDefaults = Field(default_factory=AgentDefaults)


class ProviderConfig(Base):
    secret_fields: ClassVar[frozenset[str]] = frozenset({"api_key", "api_base", "extra_headers"})
    api_key: str = Field(default="", alias="apiKey")
    api_base: str | None = Field(default=None, alias="apiBase")
    extra_headers: dict[str, str] | None = Field(default=None, alias="extraHeaders")


class ProvidersConfig(Base):
    # Reference to an admin-managed LLM provider row (LLMProviderStore). When set
    # the control plane resolves credentials at runtime and fills in the per-type
    # slot below before the config reaches the worker.
    provider_ref: str | None = Field(default=None, alias="providerRef")
    custom: ProviderConfig = Field(default_factory=ProviderConfig)
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)
    siliconflow: ProviderConfig = Field(default_factory=ProviderConfig)
    openai_codex: ProviderConfig = Field(default_factory=ProviderConfig)
    github_copilot: ProviderConfig = Field(default_factory=ProviderConfig)
    chatgpt: ProviderConfig = Field(default_factory=ProviderConfig)


class GatewayConfig(Base):
    host: str = "0.0.0.0"
    port: int = 18790


class WebSearchConfig(Base):
    provider: str = "duckduckgo"
    brave_api_key: str = ""
    serpapi_api_key: str = ""
    max_results: int = 5


class WebToolsConfig(Base):
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ShellPolicyConfig(Base):
    mode: str = "allow_all"
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    relaxed: bool = False


class ExecToolConfig(Base):
    timeout: int = 60
    policy: ShellPolicyConfig = Field(default_factory=ShellPolicyConfig)


class MCPConfigField(Base):
    """A single field in an MCP server's config schema (JSON Schema subset).

    name:        env var (stdio) or header name (HTTP) the server expects
    title:       human-readable label (maps to JSON Schema "title")
    description: hint text shown below the input
    type:        JSON Schema type — "string" | "number" | "boolean"
    format:      JSON Schema format — "password" | "uri" | "date" | ...
    x_widget:    extension for non-standard widgets — "file"
    default:     default value (any)
    enum:        allowed values → renders as <select>
    required:    whether the field must be filled before connecting
    """

    name: str
    title: str = ""
    description: str = ""
    type: str = "string"
    format: str = ""
    x_widget: str = Field(default="", alias="x-widget")
    default: str | int | float | bool | None = None
    enum: list[str] = Field(default_factory=list)
    required: bool = True


class MCPServerConfig(Base):
    secret_fields: ClassVar[frozenset[str]] = frozenset({"headers", "env"})

    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    enabled_tools: list[str] | None = Field(default=None, alias="enabledTools")
    # Config schema for the server (populated at install time from the registry).
    # Standard JSON Schema fields drive the UI: type, format, enum, x-widget, etc.
    config_schema: list[MCPConfigField] = Field(default_factory=list, alias="configSchema")
    # Guardrails applied to every tool exposed by this server.
    guardrails: list[GuardrailRef] = Field(default_factory=list)


class OpenAPIToolConfig(Base):
    """Installed OpenAPI/Swagger spec generating one tool per operation.

    Headers carry ``${VAR}`` placeholders resolved at runtime against the
    agent's encrypted variable vault, so credentials never live on disk
    in plaintext. The tool dispatcher treats individual operations as
    side-effecting (replay-safety ``checkpoint``) by default; specs may
    annotate read-only operations with ``x-replay-safety: safe``.
    """

    secret_fields: ClassVar[frozenset[str]] = frozenset({"headers"})

    spec_id: str = Field(default="", alias="specId")
    spec_url: str = Field(default="", alias="specUrl")
    headers: dict[str, str] = Field(default_factory=dict)
    enabled_operations: list[str] | None = Field(default=None, alias="enabledOperations")
    max_tools: int = Field(default=64, alias="maxTools")
    base_url_override: str | None = Field(default=None, alias="baseUrlOverride")
    role_hint: str = Field(default="", alias="roleHint")
    # Guardrails applied to every operation generated from this spec.
    guardrails: list[GuardrailRef] = Field(default_factory=list)


class SoftwareEntry(Base):
    """Installed software entry (catalog; used by subagents via software_exec)."""

    name: str = ""
    description: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    installed_via: str = ""
    package: str = ""
    stdin: bool = False


class ToolApprovalConfig(Base):
    """Per-tool execution mode: always_run (default) or ask_before_run (user approves in-channel)."""

    default_mode: str = "always_run"
    per_tool: dict[str, str] = Field(default_factory=dict, alias="perTool")
    timeout_seconds: int = 120


class ToolsConfig(Base):
    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = True
    ssrf_protection: bool = True
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)
    software: dict[str, SoftwareEntry] = Field(default_factory=dict)
    approval: ToolApprovalConfig = Field(default_factory=ToolApprovalConfig)
    openapi_tools: dict[str, OpenAPIToolConfig] = Field(default_factory=dict, alias="openapiTools")
    # Default guardrails applied to every tool's input/output. Per-tool
    # overrides come via Tool.guardrails (class-level) plus
    # OpenAPIToolConfig.guardrails / MCPServerConfig.guardrails.
    guardrails: list[GuardrailRef] = Field(default_factory=list)


class HeartbeatConfig(Base):
    enabled: bool = True
    interval_s: int = 30 * 60
    cron_expr: str = ""
    timezone: str = ""


class SkillsConfig(Base):
    disabled: list[str] = Field(default_factory=list)


class ControlPlaneConfig(Base):
    admin_url: str = ""
    agent_id: str = ""
    agent_token: str = ""
    heartbeat_interval: int = 30


class DockerSecurityConfig(Base):
    """Docker container security. level: permissive | sandboxed | privileged."""

    level: str = "permissive"
    read_only: bool | None = None
    network_mode: str | None = None
    pids_limit: int | None = None
    mem_limit: str | None = None
    cpu_quota: int | None = None
    cpu_period: int | None = None
    log_level: str = "INFO"


class SecurityConfig(Base):
    docker: DockerSecurityConfig = Field(default_factory=DockerSecurityConfig)


class SecretsConfig(Base):
    """Agent-level secrets injected as environment variables."""

    env: dict[str, str] = Field(default_factory=dict)


class SecretsPayload(Base):
    """In-memory format for agent secrets (providers, channels)."""

    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)


# Top-level section names that hold credentials (for slice and merge).
SECRET_SECTIONS = frozenset(SecretsPayload.model_fields)

# All secret field names from models that declare secret_fields (for unknown-path fallback).
_ALL_SECRET_MODELS = (
    WhatsAppConfig,
    TelegramConfig,
    FeishuConfig,
    DiscordConfig,
    EmailConfig,
    SlackConfig,
    ZaloConfig,
    ZaloUserConfig,
    TeamsConfig,
    ProviderConfig,
)
ALL_SECRET_FIELD_NAMES = frozenset().union(
    *(getattr(m, "secret_fields", frozenset()) for m in _ALL_SECRET_MODELS)
)


def get_model_for_path(root: type[BaseModel], path: tuple[str, ...]) -> type[BaseModel] | None:
    """Resolve a config path to the leaf Pydantic model class.

    Used so redaction and restore_secrets can use model.secret_fields instead of
    hardcoded key names. E.g. get_model_for_path(Config, ("channels", "slack")) -> SlackConfig.

    For ``dict[str, SomeModel]`` fields (like ``tools.mcp_servers`` or
    ``tools.openapi_tools``) the function descends into ``SomeModel`` and
    treats the next path segment as the dict key, skipping it.
    """
    if not path:
        return root
    current: type[BaseModel] | None = root
    skip_next = False
    for segment in path:
        if skip_next:
            skip_next = False
            continue
        if current is None or not hasattr(current, "model_fields"):
            return None
        if segment not in current.model_fields:
            return None
        ann = current.model_fields[segment].annotation
        origin = get_origin(ann)
        args = get_args(ann)
        if origin is Union and args:
            ann = next((a for a in args if a is not type(None)), ann)
            origin = get_origin(ann)
            args = get_args(ann)
        if origin is dict and len(args) >= 2:
            value_type = args[1]
            if isinstance(value_type, type) and issubclass(value_type, BaseModel):
                current = value_type
                skip_next = True
                continue
            return None
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            current = ann
        else:
            return None
    return current


class Config(BaseSettings):
    """Root configuration (shared schema). Provider matching is in specialagent.config.schema."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    control_plane: ControlPlaneConfig = Field(default_factory=ControlPlaneConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)

    model_config = ConfigDict(env_prefix="SPECIALAGENT_", env_nested_delimiter="__")


class ConfigUpdate(Base):
    """Partial config for updates (all sections optional). Validated and (de)serialized like Config."""

    agents: AgentsConfig | None = None
    channels: ChannelsConfig | None = None
    providers: ProvidersConfig | None = None
    gateway: GatewayConfig | None = None
    tools: ToolsConfig | None = None
    skills: SkillsConfig | None = None
    heartbeat: HeartbeatConfig | None = None
    control_plane: ControlPlaneConfig | None = None
    security: SecurityConfig | None = None
    secrets: SecretsConfig | None = None
