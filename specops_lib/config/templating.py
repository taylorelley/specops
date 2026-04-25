"""Template-variable substitution.

Tiny pure helper used by the OpenAPI api_tool runtime (Phase 2) and the
guardrail framework (Phase 3) to interpolate ``${VAR}`` placeholders
against a mapping. Strict by default: missing keys raise so tools fail
fast at install rather than silently sending an unauthenticated request.
"""

from __future__ import annotations

import re
from typing import Mapping

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.\-]*)\}")


class MissingVariableError(KeyError):
    """Raised when a ``${VAR}`` placeholder has no corresponding entry."""


def substitute_vars(
    template: str,
    variables: Mapping[str, str],
    *,
    strict: bool = True,
) -> str:
    """Replace ``${VAR}`` occurrences in ``template`` from ``variables``.

    Args:
        template: String containing zero or more ``${name}`` placeholders.
        variables: Lookup table for placeholder values.
        strict: If True (default), raise :class:`MissingVariableError`
            when a placeholder has no matching key. When False, the
            placeholder is left in place so callers can inspect.

    Returns:
        The interpolated string. If ``template`` is not a string,
        returns it unchanged.
    """
    if not isinstance(template, str):
        return template

    def _resolve(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in variables:
            return str(variables[name])
        if strict:
            raise MissingVariableError(name)
        return match.group(0)

    return _VAR_RE.sub(_resolve, template)


def substitute_vars_in_mapping(
    template: Mapping[str, str],
    variables: Mapping[str, str],
    *,
    strict: bool = True,
) -> dict[str, str]:
    """Apply :func:`substitute_vars` to every value in ``template``."""
    return {k: substitute_vars(v, variables, strict=strict) for k, v in template.items()}


__all__ = [
    "MissingVariableError",
    "substitute_vars",
    "substitute_vars_in_mapping",
]
