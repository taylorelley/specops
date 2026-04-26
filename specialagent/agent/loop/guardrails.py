"""GuardrailRunner: enforce guardrails at tool input / output and agent output.

This module is the worker-side integration of the
``specops_lib.guardrails`` API. It:

* Resolves :class:`GuardrailRef` configs into concrete
  :class:`Guardrail` instances at startup (named via a
  :class:`GuardrailRegistry` or built inline from regex/prompt fields).
* Applies them at each :class:`Position` call site, observing per-step
  ``max_retries`` budgets so a runaway ``retry`` mode can't loop
  forever.
* Emits ``guardrail_result`` and ``hitl_waiting`` events into the
  durable execution journal so the Phase 4 HITL resume path has the
  context it needs.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Mapping

from specops_lib.execution import JournalLookup
from specops_lib.guardrails import (
    CallableGuardrail,
    Guardrail,
    GuardrailContext,
    GuardrailRegistry,
    GuardrailResult,
    LLMGuardrail,
    OnFail,
    Position,
    RegexGuardrail,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Outcome the runner returns to the caller
# ---------------------------------------------------------------------------


@dataclass
class EnforcementOutcome:
    """What the agent loop should do after enforcement.

    Exactly one of ``content`` / ``retry_message`` / ``error_message`` /
    ``pause_payload`` will be non-None depending on ``decision``.
    """

    decision: str  # "pass" | "replace" | "retry" | "raise" | "pause"
    content: str = ""
    retry_message: str = ""
    error_message: str = ""
    pause_payload: dict[str, Any] = field(default_factory=dict)
    guardrail_name: str = ""

    @property
    def passed(self) -> bool:
        return self.decision == "pass"


# ---------------------------------------------------------------------------
# GuardrailRef resolution
# ---------------------------------------------------------------------------


def resolve_refs(
    refs: list[Any],
    *,
    registry: GuardrailRegistry,
    judge: Callable[[str, str], Awaitable[str]] | None = None,
) -> list[Guardrail]:
    """Turn a list of :class:`GuardrailRef`-shaped dicts/objects into
    runnable guardrails.

    Resolution order:
      1. If ``ref.name`` matches a registered guardrail, use it (with
         the ref's ``on_fail``/``max_retries`` overrides applied).
      2. Else, if ``ref.pattern`` is set, build a :class:`RegexGuardrail`.
      3. Else, if ``ref.prompt`` is set and ``judge`` is provided, build
         an :class:`LLMGuardrail`.
      4. Else, log and skip.
    """
    out: list[Guardrail] = []
    for raw in refs or []:
        ref = _ref_to_dict(raw)
        name = str(ref.get("name") or "")
        raw_on_fail = ref.get("on_fail") or "retry"
        on_fail: OnFail = (
            raw_on_fail if raw_on_fail in ("retry", "raise", "fix", "escalate") else "retry"
        )
        max_retries = int(ref.get("max_retries") or 3)
        registered = registry.get(name) if name else None
        if registered is not None:
            # Shallow-copy so per-call overrides don't mutate the
            # registry's shared instance (would otherwise cross-pollute
            # different tools / agents that reference the same name).
            override = copy.copy(registered)
            override.on_fail = on_fail
            override.max_retries = max_retries
            out.append(override)
            continue
        pattern = ref.get("pattern")
        prompt = ref.get("prompt")
        raw_mode = ref.get("regex_mode") or "block"
        regex_mode: Literal["block", "allow"] = (
            raw_mode if raw_mode in ("block", "allow") else "block"
        )
        if isinstance(pattern, str) and pattern:
            out.append(
                RegexGuardrail(
                    pattern,
                    mode=regex_mode,
                    name=name or f"inline_regex_{len(out)}",
                    on_fail=on_fail,
                    max_retries=max_retries,
                )
            )
            continue
        if isinstance(prompt, str) and prompt:
            if judge is None:
                logger.warning(
                    "[guardrail] LLM ref '%s' has prompt but no judge; skipping",
                    name or "inline",
                )
                continue
            out.append(
                LLMGuardrail(
                    prompt,
                    judge=judge,
                    name=name or f"inline_llm_{len(out)}",
                    on_fail=on_fail,
                    max_retries=max_retries,
                )
            )
            continue
        logger.warning(
            "[guardrail] ref '%s' has no registered name and no inline pattern/prompt; skipping",
            name or "?",
        )
    return out


def _ref_to_dict(raw: Any) -> Mapping[str, Any]:
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    if isinstance(raw, dict):
        return raw
    return {}


# ---------------------------------------------------------------------------
# Synthesise escalate guardrails from ToolApprovalConfig (backwards-compat).
# ---------------------------------------------------------------------------


def synthesize_approval_guardrails(approval_cfg: Any) -> dict[str, list[Any]]:
    """Map ``ToolApprovalConfig`` → per-tool inline guardrail refs.

    Tools listed with mode ``"ask_before_run"`` (or every tool when the
    default mode is ``"ask_before_run"``) get a single
    ``on_fail="escalate"`` callable guardrail synthesised. The YAML
    schema is unchanged — this runs in-memory at agent start.

    Returns a ``{tool_name: [GuardrailRef-shaped dict, ...]}`` map; the
    caller merges it into the per-tool ``guardrails`` field before
    resolving refs.
    """
    if approval_cfg is None:
        return {}
    default_mode = getattr(approval_cfg, "default_mode", "always_run")
    per_tool = dict(getattr(approval_cfg, "per_tool", {}) or {})
    out: dict[str, list[Any]] = {}
    for tool_name, mode in per_tool.items():
        if mode == "ask_before_run":
            out[tool_name] = [{"name": "legacy_approval", "on_fail": "escalate", "max_retries": 1}]
    if default_mode == "ask_before_run":
        # Mark all-tools default; the runner reads this special key.
        out.setdefault(
            "__default__", [{"name": "legacy_approval", "on_fail": "escalate", "max_retries": 1}]
        )
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def legacy_approval_guardrail() -> Guardrail:
    """Always-fail callable that triggers ``escalate``; used to bridge
    the legacy approval queue onto the journal-backed pause."""

    def _check(_content: str) -> GuardrailResult:
        return GuardrailResult(
            passed=False,
            message="Tool requires human approval (legacy ToolApprovalConfig).",
        )

    return CallableGuardrail(_check, name="legacy_approval", on_fail="escalate", max_retries=1)


class GuardrailRunner:
    """Applies a configured set of guardrails at a given Position.

    The runner is per-execution; the caller (``ToolsManager`` /
    ``SessionProcessor``) constructs one with the agent-level guardrails
    plus per-tool overrides resolved upfront. Per-step retry budgets are
    tracked in :meth:`enforce` itself — the caller decides how many
    times to re-invoke the guardrail.
    """

    def __init__(
        self,
        *,
        on_event: Callable[..., Awaitable[None]] | None = None,
        journal_lookup: JournalLookup | None = None,
    ) -> None:
        self._on_event = on_event
        self._journal = journal_lookup
        # Per-(step, guardrail) retry counters; reset by caller between turns.
        self._retries: dict[tuple[str, str], int] = {}

    def reset_step(self, step_id: str) -> None:
        """Drop retry counters for the given step (called between steps)."""
        self._retries = {k: v for k, v in self._retries.items() if k[0] != step_id}

    async def enforce(
        self,
        *,
        content: str,
        guardrails: list[Guardrail],
        position: Position,
        tool_name: str | None = None,
        args: Mapping[str, Any] | None = None,
        execution_id: str | None = None,
        step_id: str | None = None,
        plan_id: str = "",
    ) -> EnforcementOutcome:
        """Run all configured guardrails against ``content``.

        Behaviour:
          * The first failing guardrail dictates the outcome.
          * ``retry`` outcomes increment the per-(step, guardrail)
            counter; once it hits ``max_retries`` the runner upgrades
            to ``raise`` so the agent loop doesn't spin forever.
          * ``fix`` requires :attr:`GuardrailResult.fixed_output`; missing
            it falls through to ``raise`` with a clear error message.
          * ``escalate`` emits a ``hitl_waiting`` event and returns a
            pause outcome carrying the original content + the
            guardrail's reason in ``pause_payload``.
        """
        for g in guardrails:
            # Resume short-circuit: if a human has already approved this
            # (execution_id, guardrail, tool) triple via /resolve, skip
            # the check. If they rejected it, propagate as a hard raise
            # regardless of the configured on_fail.
            prior = await self._lookup_prior_resolution(execution_id, g.name, tool_name)
            if prior is not None:
                decision = str(prior.get("decision") or "")
                if decision == "approve":
                    await self._emit_result_event(
                        gname=g.name,
                        position=position,
                        tool_name=tool_name,
                        result=GuardrailResult(passed=True, message="resumed: approved"),
                        execution_id=execution_id,
                        step_id=step_id,
                        plan_id=plan_id,
                    )
                    continue
                if decision == "reject":
                    note = str(prior.get("note") or "")
                    msg = f"Approval rejected by human{f': {note}' if note else ''}."
                    await self._emit_result_event(
                        gname=g.name,
                        position=position,
                        tool_name=tool_name,
                        result=GuardrailResult(passed=False, message=msg),
                        execution_id=execution_id,
                        step_id=step_id,
                        plan_id=plan_id,
                    )
                    return EnforcementOutcome(
                        decision="raise", error_message=msg, guardrail_name=g.name
                    )
            result = await self._check_one(g, content, position, tool_name, args)
            await self._emit_result_event(
                gname=g.name,
                position=position,
                tool_name=tool_name,
                result=result,
                execution_id=execution_id,
                step_id=step_id,
                plan_id=plan_id,
            )
            if result.passed:
                continue
            return await self._dispatch_outcome(
                guardrail=g,
                content=content,
                position=position,
                tool_name=tool_name,
                result=result,
                execution_id=execution_id,
                step_id=step_id,
                plan_id=plan_id,
            )
        return EnforcementOutcome(decision="pass", content=content)

    async def _lookup_prior_resolution(
        self,
        execution_id: str | None,
        guardrail_name: str,
        tool_name: str | None,
    ) -> dict[str, Any] | None:
        if not self._journal or not execution_id:
            return None
        try:
            return await self._journal.find_hitl_resolved(execution_id, guardrail_name, tool_name)
        except Exception:
            logger.exception(
                "[guardrail] journal lookup failed for %s/%s/%s",
                execution_id,
                guardrail_name,
                tool_name,
            )
            return None

    async def _check_one(
        self,
        g: Guardrail,
        content: str,
        position: Position,
        tool_name: str | None,
        args: Mapping[str, Any] | None,
    ) -> GuardrailResult:
        ctx = GuardrailContext(position=position, tool_name=tool_name, args=args)
        try:
            # LLMGuardrail prefers async; use it where present, else sync check().
            if hasattr(g, "check_async"):
                return await getattr(g, "check_async")(content, ctx)
            return g.check(content, ctx)
        except Exception as exc:  # defensive — never let a bad guardrail kill the loop
            logger.exception("[guardrail] %s raised; treating as fail", g.name)
            return GuardrailResult(passed=False, message=f"Guardrail '{g.name}' errored: {exc}")

    async def _dispatch_outcome(
        self,
        *,
        guardrail: Guardrail,
        content: str,
        position: Position,
        tool_name: str | None,
        result: GuardrailResult,
        execution_id: str | None,
        step_id: str | None,
        plan_id: str,
    ) -> EnforcementOutcome:
        mode = guardrail.on_fail
        gname = guardrail.name
        msg = result.message or f"Guardrail '{gname}' failed."

        if mode == "raise":
            return EnforcementOutcome(decision="raise", error_message=msg, guardrail_name=gname)

        if mode == "fix":
            if result.fixed_output is None:
                # Misconfigured — degrade to raise with a clear message.
                return EnforcementOutcome(
                    decision="raise",
                    error_message=(
                        f"Guardrail '{gname}' is on_fail=fix but produced no fixed_output."
                    ),
                    guardrail_name=gname,
                )
            return EnforcementOutcome(
                decision="replace", content=result.fixed_output, guardrail_name=gname
            )

        if mode == "escalate":
            payload = {
                "guardrail": gname,
                "position": position,
                "tool_name": tool_name,
                "reason": msg,
                "original_content": content,
            }
            await self._emit_hitl_waiting(
                payload, execution_id=execution_id, step_id=step_id, plan_id=plan_id
            )
            return EnforcementOutcome(decision="pause", pause_payload=payload, guardrail_name=gname)

        # default: retry
        key = ((step_id or ""), gname)
        used = self._retries.get(key, 0)
        if used >= guardrail.max_retries:
            return EnforcementOutcome(
                decision="raise",
                error_message=(
                    f"Guardrail '{gname}' exceeded max_retries={guardrail.max_retries}: {msg}"
                ),
                guardrail_name=gname,
            )
        self._retries[key] = used + 1
        return EnforcementOutcome(decision="retry", retry_message=msg, guardrail_name=gname)

    async def _emit_result_event(
        self,
        *,
        gname: str,
        position: Position,
        tool_name: str | None,
        result: GuardrailResult,
        execution_id: str | None,
        step_id: str | None,
        plan_id: str,
    ) -> None:
        if not self._on_event or not execution_id:
            return
        await self._on_event(
            "guardrail_result",
            "",
            f"{gname}@{position}: {'pass' if result.passed else 'fail'}",
            tool_name=tool_name,
            plan_id=plan_id,
            execution_id=execution_id,
            step_id=step_id,
            event_kind="guardrail_result",
            result_status="ok" if result.passed else "error",
            payload_json=json.dumps(
                {
                    "guardrail": gname,
                    "position": position,
                    "passed": result.passed,
                    "message": result.message,
                    "fixed": result.fixed_output is not None,
                }
            ),
        )

    async def _emit_hitl_waiting(
        self,
        payload: dict[str, Any],
        *,
        execution_id: str | None,
        step_id: str | None,
        plan_id: str,
    ) -> None:
        if not self._on_event or not execution_id:
            return
        await self._on_event(
            "hitl_waiting",
            "",
            f"awaiting approval: {payload.get('guardrail', '')}",
            plan_id=plan_id,
            execution_id=execution_id,
            step_id=step_id,
            event_kind="hitl_waiting",
            payload_json=json.dumps(payload),
        )


__all__ = [
    "EnforcementOutcome",
    "GuardrailRunner",
    "legacy_approval_guardrail",
    "resolve_refs",
    "synthesize_approval_guardrails",
]
