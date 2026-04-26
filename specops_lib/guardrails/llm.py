"""LLM-judge guardrails — defer the decision to a temperature-0 LLM call.

The judge prompt is concatenated with the content and sent to the
agent's main provider (or a separately injected one). The model is
asked to return a JSON object ``{"passed": bool, "reason": str,
"fixed_output": str?}``; malformed output falls back to
``passed=False`` with the parser error so the loop reacts safely.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from specops_lib.guardrails.base import (
    Guardrail,
    GuardrailContext,
    GuardrailResult,
    OnFail,
)

logger = logging.getLogger(__name__)

# A judge-callable returns the LLM's raw text response for a given
# (system, user) prompt pair. Decoupled from any specific provider so
# tests can pass a stub. The runner adapts the worker's existing
# LLMProvider.chat() into this shape.
JudgeFn = Callable[[str, str], Awaitable[str]]


_JUDGE_SYSTEM_PROMPT = (
    "You are a strict, terse safety/quality judge. The user will give you a "
    "policy and a candidate output. Respond with ONE JSON object exactly:\n"
    '  {"passed": <bool>, "reason": "<short reason>", "fixed_output": "<optional>"}\n'
    "Only include fixed_output when you can produce a corrected version. "
    "Do not include any prose outside the JSON object."
)


@dataclass
class _JudgeInvocation:
    judge: JudgeFn
    policy: str


class LLMGuardrail(Guardrail):
    """LLM-as-judge guardrail.

    ``policy`` is a short natural-language description of what passes
    and what fails. ``judge`` is an injectable async callable; in
    production the runner adapts the agent's main provider, in tests a
    stub is passed.
    """

    def __init__(
        self,
        policy: str,
        *,
        judge: JudgeFn,
        name: str | None = None,
        on_fail: OnFail = "retry",
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            name=name or "llm_guardrail",
            on_fail=on_fail,
            max_retries=max_retries,
        )
        self._inv = _JudgeInvocation(judge=judge, policy=policy)

    def check(self, content: str, context: GuardrailContext) -> GuardrailResult:
        # Placeholder for sync API; the runner calls ``check_async`` for the real path.
        raise NotImplementedError(
            "LLMGuardrail.check() is async; call check_async() via GuardrailRunner."
        )

    async def check_async(self, content: str, context: GuardrailContext) -> GuardrailResult:
        user = (
            f"Policy: {self._inv.policy}\n\n"
            f"Candidate output:\n---\n{content}\n---\n\n"
            "Respond with the JSON object only."
        )
        try:
            raw = await self._inv.judge(_JUDGE_SYSTEM_PROMPT, user)
        except Exception as exc:
            logger.warning("[guardrail.llm] judge call failed: %s", exc)
            return GuardrailResult(
                passed=False, message=f"LLM guardrail '{self.name}' errored: {exc}"
            )
        return _parse_judge_response(raw, self.name)


def _parse_judge_response(raw: str, gname: str) -> GuardrailResult:
    text = (raw or "").strip()
    # Tolerate a model that wraps the JSON in ```json fences.
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline >= 0 else text
        if text.endswith("```"):
            text = text[:-3]
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        return GuardrailResult(
            passed=False,
            message=f"LLM guardrail '{gname}' produced unparseable output: {exc}",
        )
    if not isinstance(data, dict):
        return GuardrailResult(
            passed=False,
            message=f"LLM guardrail '{gname}' returned non-object JSON.",
        )
    passed = bool(data.get("passed", False))
    reason = str(data.get("reason", ""))
    fixed = data.get("fixed_output")
    if fixed is not None and not isinstance(fixed, str):
        fixed = str(fixed)
    return GuardrailResult(passed=passed, message=reason, fixed_output=fixed)


__all__ = ["LLMGuardrail", "JudgeFn"]
