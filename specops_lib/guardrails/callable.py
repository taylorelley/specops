"""Callable guardrails — wrap a Python function in the Guardrail interface."""

from __future__ import annotations

from typing import Any, Callable

from specops_lib.guardrails.base import (
    Guardrail,
    GuardrailContext,
    GuardrailResult,
    OnFail,
)

_GuardrailFn = Callable[[str], GuardrailResult]


class CallableGuardrail(Guardrail):
    """Wrap any ``(content: str) -> GuardrailResult`` function."""

    def __init__(
        self,
        func: _GuardrailFn,
        *,
        name: str | None = None,
        on_fail: OnFail = "retry",
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            name=name or getattr(func, "__name__", "callable_guardrail"),
            on_fail=on_fail,
            max_retries=max_retries,
        )
        self._func = func

    def check(self, content: str, context: GuardrailContext) -> GuardrailResult:
        return self._func(content)


def guardrail(
    _func: _GuardrailFn | None = None,
    *,
    name: str | None = None,
    on_fail: OnFail = "retry",
    max_retries: int = 3,
) -> Any:
    """Decorator turning a function into a :class:`CallableGuardrail`.

    Mirrors Agentspan's ``@guardrail`` declarative form. Supports both
    bare and parameterised use::

        @guardrail
        def word_limit(content: str) -> GuardrailResult: ...

        @guardrail(name="pii_block", on_fail="raise")
        def pii_block(content: str) -> GuardrailResult: ...
    """

    def _wrap(fn: _GuardrailFn) -> CallableGuardrail:
        return CallableGuardrail(fn, name=name, on_fail=on_fail, max_retries=max_retries)

    if _func is not None:
        return _wrap(_func)
    return _wrap


__all__ = ["CallableGuardrail", "guardrail"]
