"""ToolsManager: tool registration, execution, and approval."""

import json
import time
from pathlib import Path

from loguru import logger

from specialagent.agent.agent_fs import AgentFS
from specialagent.agent.approval import ToolApprovalManager
from specialagent.agent.subagent import SubagentManager
from specialagent.agent.tools.a2a import get_a2a_tools
from specialagent.agent.tools.cron import CronTool
from specialagent.agent.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WorkspaceTreeTool,
    WriteFileTool,
)
from specialagent.agent.tools.message import MessageTool
from specialagent.agent.tools.plan import get_plan_tools
from specialagent.agent.tools.policy import ShellCommandPolicy
from specialagent.agent.tools.registry import ToolRegistry
from specialagent.agent.tools.shell import ExecTool
from specialagent.agent.tools.spawn import SpawnTool
from specialagent.agent.tools.utils import redact_tool_args, truncate_output
from specialagent.agent.tools.web import WebFetchTool, WebSearchTool
from specialagent.providers.base import ToolCallRequest
from specops_lib.bus import InboundMessage, MessageBus
from specops_lib.config.schema import ExecToolConfig, WebSearchConfig
from specops_lib.execution import (
    JournalLookup,
    NullJournal,
    derive_idempotency_key,
)


class ToolsManager:
    """Manages tool registration, context setting, approval, and execution."""

    def __init__(
        self,
        tools: ToolRegistry,
        mcp: ToolRegistry,
        approval: ToolApprovalManager,
        bus: MessageBus,
        subagents: SubagentManager,
        file_service: AgentFS,
        workspace: Path | str,
        exec_config: ExecToolConfig,
        web_search_config: WebSearchConfig,
        restrict_to_workspace: bool,
        ssrf_protection: bool,
        max_tool_output_chars: int,
        admin_api_url: str = "",
        agent_token: str = "",
        agent_id: str = "",
        cron_service=None,
        on_event=None,
        journal_lookup: JournalLookup | None = None,
    ) -> None:
        self.tools = tools
        self.mcp = mcp
        self._approval = approval
        self._bus = bus
        self._subagents = subagents
        self._file_service = file_service
        self._workspace = Path(workspace) if isinstance(workspace, str) else workspace
        self._exec_config = exec_config
        self._web_search_config = web_search_config
        self._restrict_to_workspace = restrict_to_workspace
        self._ssrf_protection = ssrf_protection
        self._max_tool_output_chars = max_tool_output_chars
        self._admin_api_url = admin_api_url
        self._agent_token = agent_token
        self._agent_id = agent_id
        self._cron_service = cron_service
        self._on_event = on_event
        self._journal: JournalLookup = journal_lookup or NullJournal()

    def register_default_tools(self) -> None:
        """Register the default set of tools."""
        self.tools.register(ReadFileTool(file_service=self._file_service))
        self.tools.register(WriteFileTool(file_service=self._file_service))
        self.tools.register(EditFileTool(file_service=self._file_service))
        self.tools.register(ListDirTool(file_service=self._file_service))
        self.tools.register(WorkspaceTreeTool(file_service=self._file_service))

        shell_policy = ShellCommandPolicy.from_dict(self._exec_config.policy.model_dump())
        self.tools.register(
            ExecTool(
                working_dir=str(self._workspace),
                timeout=self._exec_config.timeout,
                restrict_to_workspace=self._restrict_to_workspace,
                policy=shell_policy,
            )
        )

        self.tools.register(WebSearchTool(config=self._web_search_config))
        self.tools.register(WebFetchTool(ssrf_protection=self._ssrf_protection))

        message_tool = MessageTool(send_callback=self._bus.publish_outbound)
        self.tools.register(message_tool)

        spawn_tool = SpawnTool(manager=self._subagents)
        self.tools.register(spawn_tool)

        if self._cron_service:
            self.tools.register(CronTool(self._cron_service))

        if self._admin_api_url and self._agent_token:
            for tool in get_plan_tools(self._admin_api_url, self._agent_token, self._agent_id):
                self.tools.register(tool)
            logger.info("Registered plan tools (admin_url={})", self._admin_api_url)

            for tool in get_a2a_tools(self._admin_api_url, self._agent_token, self._agent_id):
                self.tools.register(tool)
            logger.info("Registered A2A tools")

        self.tools.register_plugins()

    def set_tool_context(self, channel: str, chat_id: str) -> None:
        """Update context for tools that need routing info (message, spawn, cron).

        Call before each agent run; tools use this to route replies to the correct channel/chat.
        """
        if message_tool := self.tools.get("message"):
            message_tool.set_context(channel, chat_id)
        if spawn_tool := self.tools.get("spawn"):
            spawn_tool.set_context(channel, chat_id)
        if cron_tool := self.tools.get("cron"):
            cron_tool.set_context(channel, chat_id)

    @property
    def approval_config(self):
        """Tool approval config (for context builder)."""
        return self._approval.config

    def try_resolve_approval(self, msg: InboundMessage) -> bool:
        """If this message is a yes/no reply for a pending tool approval, resolve the future and return True."""
        return self._approval.try_resolve(msg)

    async def execute_tool(
        self,
        tool_call: ToolCallRequest,
        channel: str,
        chat_id: str,
        plan_id: str = "",
        execution_id: str = "",
        step_id: str = "",
    ) -> tuple[str, str]:
        """Execute a single tool call with logging, journal, and truncation.

        Approval gate: if approval is ``ask_before_run``, prompts the user
        in-channel and waits for approval.

        Journal: when ``execution_id`` is provided and the tool is
        ``checkpoint`` or ``skip`` replay-safety, the prior journal is
        consulted before executing. A previously completed call short-
        circuits to the cached result; an interrupted call (tool_call
        with no tool_result) returns a synthetic message rather than
        re-executing a side-effecting tool.
        """
        mode = self._approval.get_mode(tool_call.name)
        if mode == "ask_before_run":
            logger.info(
                "[tool_approval] Requesting approval for tool={}, channel={}, chat_id={}",
                tool_call.name,
                channel,
                chat_id,
            )
            approved = await self._approval.request_approval(tool_call, channel, chat_id)
            logger.info(
                "[tool_approval] Approval result for tool={}: approved={}",
                tool_call.name,
                approved,
            )
            if not approved:
                return (
                    tool_call.id,
                    f"[APPROVAL REQUIRED] The user did not approve running '{tool_call.name}' "
                    f"(either replied 'no' or didn't respond within the timeout). "
                    "This is not a system error - you can still use this tool if the user agrees. "
                    "Ask the user if they want you to try again.",
                )

        tool_obj = self.tools.get(tool_call.name) or self.mcp.get(tool_call.name)
        replay_safety = (
            getattr(tool_obj, "replay_safety", "checkpoint") if tool_obj else "checkpoint"
        )
        idem_key: str | None = None
        if execution_id:
            override = tool_obj.compute_idempotency_key(tool_call.arguments) if tool_obj else None
            idem_key = override or derive_idempotency_key(
                execution_id, step_id or "step:0", tool_call.name, tool_call.arguments
            )

        args_str = json.dumps(tool_call.arguments, ensure_ascii=False)

        if execution_id and idem_key and replay_safety in ("checkpoint", "skip"):
            prior_result = await self._journal.find_tool_result(execution_id, idem_key)
            if prior_result and (prior_result.get("result_status") == "ok"):
                cached = prior_result.get("payload_json") or prior_result.get("content") or ""
                logger.info(
                    "[journal] Reusing prior tool_result for tool={}, exec={}, idem={}",
                    tool_call.name,
                    execution_id,
                    idem_key[:12],
                )
                return tool_call.id, cached
            prior_call = await self._journal.find_tool_call(execution_id, idem_key)
            if prior_call and not prior_result:
                if replay_safety == "skip":
                    msg = (
                        f"[RESUME UNSAFE] '{tool_call.name}' was started in a prior execution "
                        "but did not complete. Resume cannot continue safely; aborting this step."
                    )
                    return tool_call.id, msg
                msg = (
                    f"[INTERRUPTED] A prior call to '{tool_call.name}' with the same arguments "
                    "was started but never confirmed complete. Treat the side effects as "
                    "unknown and decide whether to ask the user before retrying."
                )
                return tool_call.id, msg

        logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
        start = time.perf_counter()
        result_status = "ok"
        if self._on_event:
            hint = args_str[:80]
            await self._on_event(
                "tool_call",
                "",
                hint,
                tool_name=tool_call.name,
                tool_args_redacted=redact_tool_args(tool_call.arguments),
                plan_id=plan_id,
                execution_id=execution_id or None,
                step_id=step_id or None,
                event_kind="tool_call" if execution_id else None,
                replay_safety=replay_safety if execution_id else None,
                idempotency_key=idem_key,
            )

        try:
            if tool_call.name in self.mcp:
                result = await self.mcp.execute(tool_call.name, tool_call.arguments)
            else:
                result = await self.tools.execute(tool_call.name, tool_call.arguments)
        except Exception as e:
            result_status = "error"
            result = f"Error executing {tool_call.name}: {e}"
        result = truncate_output(result, self._max_tool_output_chars)
        duration_ms = round((time.perf_counter() - start) * 1000)

        if self._on_event:
            await self._on_event(
                "tool_result",
                "",
                str(result)[:120],
                tool_name=tool_call.name,
                tool_args_redacted=redact_tool_args(tool_call.arguments),
                result_status=result_status,
                duration_ms=duration_ms,
                plan_id=plan_id,
                execution_id=execution_id or None,
                step_id=step_id or None,
                event_kind="tool_result" if execution_id else None,
                replay_safety=replay_safety if execution_id else None,
                idempotency_key=idem_key,
                payload_json=result if execution_id else None,
            )
        return tool_call.id, result
