"""Guardrail public types: GuardrailResult, OnFail, Position, Guardrail base.

API shape derived from Agentspan (MIT, © 2025 Agentspan); independently
implemented in Apache-2.0 Python. Agentspan's ``OnFail.HUMAN`` is
renamed ``OnFail.escalate`` in SpecOps to avoid clashing with the
existing in-channel "human approval" terminology used by
``ToolApprovalConfig``. See NOTICE for the attribution statement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal, Mapping

# Order matters: tool_input before dispatch, tool_output after, agent_output after the LLM produces a final reply.
Position = Literal["tool_input", "tool_output", "agent_output"]
POSITIONS: tuple[Position, ...] = ("tool_input", "tool_output", "agent_output")

OnFail = Literal["retry", "raise", "fix", "escalate"]
ON_FAIL_MODES: tuple[OnFail, ...] = ("retry", "raise", "fix", "escalate")


@dataclass
class GuardrailResult:
    """One guardrail decision.

    ``passed=True`` short-circuits enforcement; ``passed=False`` invokes
    the configured ``on_fail`` mode. ``message`` is fed to the LLM on
    ``retry`` and surfaced to the user on ``raise``. ``fixed_output``
    is required for the ``fix`` mode and ignored otherwise.
    """

    passed: bool
    message: str = ""
    fixed_output: str | None = None


@dataclass
class GuardrailContext:
    """Optional context passed to ``Guardrail.check`` (callsite metadata)."""

    position: Position
    tool_name: str | None = None
    args: Mapping[str, Any] | None = None
    execution_id: str | None = None
    step_id: str | None = None


class Guardrail(ABC):
    """Abstract base for all guardrail kinds.

    Concrete guardrails inherit from this and implement ``check``.
    The ``GuardrailRunner`` (in ``specialagent/agent/loop/guardrails.py``)
    consults ``on_fail`` and ``max_retries`` to decide what the agent
    loop should do when ``passed=False``.
    """

    name: str
    on_fail: OnFail
    max_retries: int

    def __init__(
        self,
        *,
        name: str,
        on_fail: OnFail = "retry",
        max_retries: int = 3,
    ) -> None:
        self.name = name
        self.on_fail = on_fail
        self.max_retries = max_retries

    @abstractmethod
    def check(self, content: str, context: GuardrailContext) -> GuardrailResult:
        """Decide whether ``content`` passes. Must be cheap (no I/O) for
        callable / regex guardrails; LLM judges may block but should
        respect timeouts in their implementation.
        """


__all__ = [
    "OnFail",
    "ON_FAIL_MODES",
    "Position",
    "POSITIONS",
    "GuardrailResult",
    "GuardrailContext",
    "Guardrail",
]
