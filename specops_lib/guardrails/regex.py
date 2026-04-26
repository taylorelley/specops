"""Regex guardrails — pattern match in block / allow modes."""

from __future__ import annotations

import re
from typing import Literal

from specops_lib.guardrails.base import (
    Guardrail,
    GuardrailContext,
    GuardrailResult,
    OnFail,
)

RegexMode = Literal["block", "allow"]


class RegexGuardrail(Guardrail):
    """Pattern-based guardrail.

    ``mode="block"`` fails when the pattern matches anywhere in the
    content; ``mode="allow"`` fails when it does NOT match. The
    pattern is compiled once at construction with optional ``flags``.
    """

    def __init__(
        self,
        pattern: str,
        *,
        mode: RegexMode = "block",
        name: str | None = None,
        on_fail: OnFail = "retry",
        max_retries: int = 3,
        flags: int = 0,
    ) -> None:
        super().__init__(
            name=name or f"regex_{mode}",
            on_fail=on_fail,
            max_retries=max_retries,
        )
        self._regex = re.compile(pattern, flags)
        self._mode: RegexMode = mode
        self._raw_pattern = pattern

    def check(self, content: str, context: GuardrailContext) -> GuardrailResult:
        matched = bool(self._regex.search(content or ""))
        if self._mode == "block":
            if matched:
                return GuardrailResult(
                    passed=False,
                    message=f"Output blocked by guardrail '{self.name}': matched /{self._raw_pattern}/.",
                )
            return GuardrailResult(passed=True)
        # allow mode
        if matched:
            return GuardrailResult(passed=True)
        return GuardrailResult(
            passed=False,
            message=f"Output rejected by guardrail '{self.name}': did not match /{self._raw_pattern}/.",
        )


__all__ = ["RegexGuardrail", "RegexMode"]
