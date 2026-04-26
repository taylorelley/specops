"""String-keyed registry so YAML config can reference shared guardrails."""

from __future__ import annotations

from threading import Lock

from specops_lib.guardrails.base import Guardrail


class GuardrailRegistry:
    """Holds named :class:`Guardrail` instances for config lookup."""

    def __init__(self) -> None:
        self._items: dict[str, Guardrail] = {}
        self._lock = Lock()

    def register(self, guardrail: Guardrail, *, name: str | None = None) -> None:
        key = name or guardrail.name
        with self._lock:
            self._items[key] = guardrail

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._items.pop(name, None) is not None

    def get(self, name: str) -> Guardrail | None:
        return self._items.get(name)

    def names(self) -> list[str]:
        return list(self._items.keys())


# Singleton used by config-driven attachment in the worker.
_default = GuardrailRegistry()


def default_registry() -> GuardrailRegistry:
    return _default


__all__ = ["GuardrailRegistry", "default_registry"]
