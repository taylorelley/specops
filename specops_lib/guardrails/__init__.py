"""Public guardrail API.

API shape (``GuardrailResult``, ``OnFail``, ``Position``,
``@guardrail``, ``RegexGuardrail``, ``LLMGuardrail``) is derived from
Agentspan (MIT, © 2025 Agentspan) and re-implemented natively in
Apache-2.0 Python. See NOTICE for attribution.
"""

from specops_lib.guardrails.base import (
    ON_FAIL_MODES,
    POSITIONS,
    Guardrail,
    GuardrailContext,
    GuardrailResult,
    OnFail,
    Position,
)
from specops_lib.guardrails.callable import CallableGuardrail, guardrail
from specops_lib.guardrails.llm import JudgeFn, LLMGuardrail
from specops_lib.guardrails.regex import RegexGuardrail, RegexMode
from specops_lib.guardrails.registry import GuardrailRegistry, default_registry

__all__ = [
    "CallableGuardrail",
    "Guardrail",
    "GuardrailContext",
    "GuardrailRegistry",
    "GuardrailResult",
    "JudgeFn",
    "LLMGuardrail",
    "ON_FAIL_MODES",
    "OnFail",
    "POSITIONS",
    "Position",
    "RegexGuardrail",
    "RegexMode",
    "default_registry",
    "guardrail",
]
