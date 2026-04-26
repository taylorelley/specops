"""Agent loop: the core processing engine."""

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger

from specialagent.agent.agent_fs import AgentFS
from specialagent.agent.approval import ToolApprovalManager
from specialagent.agent.consolidator import MemoryConsolidator
from specialagent.agent.context import ContextBuilder
from specialagent.agent.loop.guardrails import (
    GuardrailRunner,
    legacy_approval_guardrail,
    resolve_refs,
    synthesize_approval_guardrails,
)
from specialagent.agent.loop.mcp import McpManager
from specialagent.agent.loop.session import SessionProcessor
from specialagent.agent.loop.tools import ToolsManager
from specialagent.agent.subagent import SubagentManager
from specialagent.agent.tools.mcp import MCPServerStatus
from specialagent.agent.tools.registry import ToolRegistry
from specialagent.core.cron import CronService
from specialagent.core.session import SessionManager
from specialagent.core.software import SoftwareManagement
from specialagent.providers.base import LLMProvider
from specialagent.providers.litellm_provider import LiteLLMProvider
from specialagent.providers.registry import find_by_model
from specops_lib.bus import MessageBus, OutboundMessage
from specops_lib.config.schema import (
    AgentDefaults,
    ControlPlaneConfig,
    ProviderConfig,
    SecretsConfig,
    SkillsConfig,
    ToolApprovalConfig,
    ToolsConfig,
)
from specops_lib.execution import JournalLookup, LocalJournalLookup
from specops_lib.guardrails import Guardrail, default_registry


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back

    Behaviour is composed from:
    - McpManager:       MCP server connection and lifecycle
    - ToolsManager:     tool registration, execution, and approval
    - SessionProcessor: message processing and the LLM iteration loop
    """

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        file_service: AgentFS,
        agent_defaults: AgentDefaults | None = None,
        tools_config: ToolsConfig | None = None,
        control_plane: ControlPlaneConfig | None = None,
        skills_config: SkillsConfig | None = None,
        cron_service: CronService | None = None,
        session_manager: SessionManager | None = None,
        software_management: SoftwareManagement | None = None,
        on_event: Callable[..., Awaitable[None]] | None = None,
        journal_lookup: JournalLookup | None = None,
        secrets_config: SecretsConfig | None = None,
    ):
        self._file_service = file_service
        self.workspace = file_service.workspace_path
        self.bus = bus
        self.provider = provider

        defaults = agent_defaults or AgentDefaults()
        self.model = defaults.model or provider.get_default_model()
        self.max_iterations = defaults.max_tool_iterations
        self.temperature = defaults.temperature
        self.max_tokens = defaults.max_tokens
        self.memory_window = defaults.memory_window
        self.max_tool_output_chars = defaults.max_tool_output_chars

        tools = tools_config or ToolsConfig()
        self.web_search_config = tools.web.search
        self.exec_config = tools.exec
        self.cron_service = cron_service
        self.restrict_to_workspace = tools.restrict_to_workspace
        self.ssrf_protection = tools.ssrf_protection

        skills = skills_config or SkillsConfig()
        self.context = ContextBuilder(
            self.workspace,
            profile_path=self._file_service.profile_path,
            disabled_skills=skills.disabled,
        )
        self.sessions = session_manager or SessionManager(
            sessions_dir=self._file_service.sessions_path
        )
        self.tools = ToolRegistry()
        self.mcp = ToolRegistry()
        self.subagents = SubagentManager(
            provider=provider,
            file_service=self._file_service,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            web_search_config=self.web_search_config,
            exec_config=self.exec_config,
            restrict_to_workspace=self.restrict_to_workspace,
            software_management=software_management,
            on_event=on_event,
        )

        self._running = False
        self.software_management = software_management
        self._on_event = on_event

        cp = control_plane or ControlPlaneConfig()
        self._admin_api_url = cp.admin_url or ""
        self._agent_token = cp.agent_token or ""
        self._agent_id = cp.agent_id or ""
        self._approval = ToolApprovalManager(bus=bus, config=tools.approval)
        self._consolidator = MemoryConsolidator(
            workspace=self.workspace, provider=provider, model=self.model
        )

        self._mcp_manager = McpManager(
            mcp_registry=self.mcp,
            initial_servers=dict(tools.mcp_servers) if tools.mcp_servers else None,
        )

        self._journal_lookup: JournalLookup = journal_lookup or LocalJournalLookup(
            self._file_service.logs_path
        )

        secrets = secrets_config or SecretsConfig()
        var_lookup = dict(secrets.env or {})
        api_tool_cache_dir = self._file_service.config_path.parent / "api-tools"

        guardrail_runner = GuardrailRunner(on_event=on_event, journal_lookup=self._journal_lookup)
        # Bridge ToolApprovalConfig → escalate guardrails so legacy YAML
        # keeps working without schema change.
        registry = default_registry()
        registry.register(legacy_approval_guardrail())
        approval_synth = synthesize_approval_guardrails(tools.approval)
        # Per-tool resolved guardrails: agent-default + per-tool config overrides
        # + synthesised approval refs + (later, at registration time) class-level Tool.guardrails.
        default_refs = list(tools.guardrails or [])
        default_tool_guardrails: list[Guardrail] = resolve_refs(default_refs, registry=registry)
        per_tool_refs: dict[str, list[Any]] = {}
        for tool_name, refs in approval_synth.items():
            if tool_name == "__default__":
                # Approval default-mode means every tool gets the synth.
                default_tool_guardrails.extend(resolve_refs(refs, registry=registry))
            else:
                per_tool_refs.setdefault(tool_name, []).extend(refs)
        # MCP server guardrails: each server's refs apply to every tool the
        # server exposes (named ``mcp_<server>_<tool>`` at runtime).
        for server_key, server_cfg in (tools.mcp_servers or {}).items():
            server_refs = getattr(server_cfg, "guardrails", None) or []
            if not server_refs:
                continue
            prefix = f"mcp_{server_key}_"
            per_tool_refs.setdefault(prefix, []).extend(
                ref.model_dump() if hasattr(ref, "model_dump") else dict(ref) for ref in server_refs
            )
        # OpenAPI tool guardrails: same shape — one prefix per spec.
        for spec_id, ot_cfg in (tools.openapi_tools or {}).items():
            ot_refs = getattr(ot_cfg, "guardrails", None) or []
            if not ot_refs:
                continue
            prefix = f"api_{spec_id}_"
            per_tool_refs.setdefault(prefix, []).extend(
                ref.model_dump() if hasattr(ref, "model_dump") else dict(ref) for ref in ot_refs
            )
        tool_guardrails: dict[str, list[Guardrail]] = {
            name: resolve_refs(refs, registry=registry) for name, refs in per_tool_refs.items()
        }
        # Agent-output guardrails come from agent.defaults.guardrails.
        agent_output_refs = list(getattr(defaults, "guardrails", None) or [])
        agent_output_guardrails: list[Guardrail] = resolve_refs(
            agent_output_refs, registry=registry
        )
        self._guardrail_runner = guardrail_runner
        self._tool_guardrails = tool_guardrails
        self._default_tool_guardrails = default_tool_guardrails
        self._agent_output_guardrails = agent_output_guardrails

        self._tools_manager = ToolsManager(
            tools=self.tools,
            mcp=self.mcp,
            approval=self._approval,
            bus=bus,
            subagents=self.subagents,
            file_service=file_service,
            workspace=self.workspace,
            exec_config=self.exec_config,
            web_search_config=self.web_search_config,
            restrict_to_workspace=self.restrict_to_workspace,
            ssrf_protection=self.ssrf_protection,
            max_tool_output_chars=self.max_tool_output_chars,
            admin_api_url=self._admin_api_url,
            agent_token=self._agent_token,
            agent_id=self._agent_id,
            cron_service=cron_service,
            on_event=on_event,
            journal_lookup=self._journal_lookup,
            var_lookup=var_lookup,
            openapi_tools_config=dict(tools.openapi_tools or {}),
            api_tool_cache_dir=api_tool_cache_dir,
            guardrail_runner=guardrail_runner,
            # ToolsManager.guardrails_for_tool does exact-name then
            # startswith() fallback over the registered keys, so the
            # prefix wiring here is a plain pass-through.
            tool_guardrails=tool_guardrails,
            default_tool_guardrails=default_tool_guardrails,
        )
        self._tools_manager.register_default_tools()

        self._session_processor = SessionProcessor(
            tools_manager=self._tools_manager,
            mcp_manager=self._mcp_manager,
            provider=provider,
            context=self.context,
            sessions=self.sessions,
            consolidator=self._consolidator,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            max_iterations=self.max_iterations,
            memory_window=self.memory_window,
            on_event=on_event,
            software_management=software_management,
            guardrail_runner=guardrail_runner,
            agent_output_guardrails=agent_output_guardrails,
        )

    # ── Hot-reload ────────────────────────────────────────────────────────────

    def update_tool_approval(self, cfg: ToolApprovalConfig) -> None:
        """Hot-reload tool approval config (called when admin updates config)."""
        self._approval.update_config(cfg)

    def update_provider_secrets(self, providers: dict) -> None:
        """Hot-reload provider API credentials.

        Prefer using ConfigEngine.hot_reload_providers() so the
        engine owns the flow; this method is the implementation that applies
        the given providers dict to the running LiteLLM provider and subagents.

        Args:
            providers: Dict of provider configs, e.g. {"gemini": {"api_key": "..."}}
        """
        if not isinstance(self.provider, LiteLLMProvider):
            logger.debug("[provider_secrets] Provider is not LiteLLM, skipping update")
            return

        spec = find_by_model(self.model)
        if not spec:
            logger.debug("[provider_secrets] No provider spec found for model: {}", self.model)
            return

        raw = providers.get(spec.name)
        if not isinstance(raw, dict):
            logger.debug("[provider_secrets] No config for provider: {}", spec.name)
            return
        pc = ProviderConfig.model_validate(raw)
        if not pc.api_key:
            logger.debug("[provider_secrets] No api_key for provider: {}", spec.name)
            return
        logger.info("[provider_secrets] Updating API key for provider: {}", spec.name)
        self.provider.update_credentials(
            api_key=pc.api_key,
            api_base=pc.api_base,
            extra_headers=pc.extra_headers,
        )

    def register_software(self, key: str, entry: dict) -> None:
        """Register software in the catalog at runtime (hot reload). Subagents use it via software_exec."""
        if self.software_management:
            self.software_management.register(key, entry)
        else:
            logger.warning("No software_management: cannot register software")

    def unregister_software(self, key: str) -> None:
        """Unregister software from the catalog at runtime (hot reload)."""
        if self.software_management:
            self.software_management.unregister(key)
        else:
            logger.warning("No software_management: cannot unregister software")

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def mcp_status(self) -> dict[str, MCPServerStatus]:
        """Per-server MCP connection status (populated after first connect)."""
        return self._mcp_manager.status

    @property
    def mcp_servers(self) -> dict:
        """All registered MCP server configs (including those not yet connected)."""
        return self._mcp_manager.servers

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        await self._mcp_manager.close()

    async def register_mcp_server(self, key: str, config: dict) -> MCPServerStatus:
        """Register a new MCP server at runtime (delegates to McpManager)."""
        return await self._mcp_manager.register_server(key, config)

    def unregister_mcp_server(self, key: str) -> None:
        """Unregister an MCP server at runtime (delegates to McpManager)."""
        self._mcp_manager.unregister_server(key)

    async def reconnect_skipped_mcp_servers(self) -> dict[str, MCPServerStatus]:
        """Retry failed/skipped MCP server connections (e.g. after post-install daemons start)."""
        return await self._mcp_manager.reconnect_skipped_or_failed()

    def try_resolve_approval(self, msg) -> bool:
        """If this message is a yes/no reply for a pending tool approval, resolve and return True."""
        return self._tools_manager.try_resolve_approval(msg)

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress=None,
        execution_id: str | None = None,
    ) -> str:
        """Process a message directly (delegates to SessionProcessor)."""
        return await self._session_processor.process_direct(
            content,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            on_progress=on_progress,
            execution_id=execution_id,
        )

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        self._mcp_manager.connect()
        await self._mcp_manager.await_connected()
        try:
            await self._tools_manager.register_openapi_tools()
        except Exception as exc:
            logger.warning("OpenAPI tool registration failed (non-fatal): {}", exc)
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
                if self.try_resolve_approval(msg):
                    continue
                try:
                    response = await self._session_processor.process_message(msg)
                    if response:
                        await self.bus.publish_outbound(response)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=f"Sorry, I encountered an error: {str(e)}",
                        )
                    )
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Agent loop consume_inbound error: {}", e)
                if not self._running:
                    break
                continue

    def stop(self) -> None:
        """Stop the agent loop (idempotent)."""
        if not self._running:
            return
        self._running = False
        logger.info("Agent loop stopping")
