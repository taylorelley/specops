"""Worker-side journal interface and helpers.

The worker writes journal events through the existing
:class:`specops_lib.activity.ActivityLog` (so they ride the same JSONL
buffer + WS push path as audit events). What this module adds is a
read-side ``Journal`` lookup the agent loop and tool dispatcher use to
decide whether to skip a tool call on resume, plus a ``NullJournal``
for tests and disabled-feature paths.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping


def canonical_args(args: Mapping[str, Any]) -> str:
    """Stable JSON encoding for tool arguments."""
    return json.dumps(
        dict(args),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


class JournalLookup(ABC):
    """Resume-side reader: does a prior ``tool_result`` exist for this key?"""

    @abstractmethod
    async def find_tool_result(
        self,
        execution_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        """Return the journaled tool_result row (with ``content`` and
        ``result_status`` fields) or ``None`` if no completed call exists.
        """

    @abstractmethod
    async def find_tool_call(
        self,
        execution_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        """Return the journaled tool_call row or ``None``.

        Used to detect "tool started but never finished" (kill between
        ``tool_call`` and ``tool_result``); for ``checkpoint``-safety
        tools this is treated as an interrupted call rather than a
        re-run.
        """

    async def find_hitl_resolved(
        self,
        execution_id: str,
        guardrail_name: str,
        tool_name: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the most recent ``hitl_resolved`` event matching the
        guardrail (and optional tool name) for the given execution, or
        ``None``.

        ``tool_name`` is the disambiguator for the synthesised
        ``legacy_approval`` guardrail — every tool with an
        ``ask_before_run`` mode shares that name, so resolving for
        tool A must not silently unblock tool B. Pass ``None`` to
        match any tool.

        Phase 4 uses this on the resume path so an already-resolved
        guardrail doesn't re-pause when the LLM re-emits the same tool
        call. The default is ``None`` — concrete lookups override.
        """
        return None


class Journal(JournalLookup):
    """Full journal interface, write + read.

    The worker's default implementation routes writes through the
    existing ``ActivityLog.emit`` (which persists to ``activity.jsonl``
    and pushes to the control plane); reads go to whatever reader the
    worker is configured with — typically a small wrapper that hits
    the control plane via the existing request/response WebSocket
    pattern.
    """

    @abstractmethod
    def emit(self, event: Any) -> None:
        """Append an :class:`ActivityEvent` to the journal."""


class NullJournal(Journal):
    """No-op journal — the safe default when journaling is disabled.

    Tests and one-shot CLI invocations use this to bypass the journal
    entirely. ``find_*`` always returns ``None`` so the dispatcher
    behaves as if there is no prior event.
    """

    def emit(self, event: Any) -> None:  # noqa: D401
        return None

    async def find_tool_result(
        self,
        execution_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        return None

    async def find_tool_call(
        self,
        execution_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        return None


class LocalJournalLookup(JournalLookup):
    """Reads journal events from the worker's ``.logs/activity.jsonl``.

    The same JSONL files the worker streams to the control plane are
    also the worker's local journal — events carry the new optional
    ``execution_id`` / ``idempotency_key`` / ``event_kind`` fields, and
    a fresh worker mounting the same data root can index them on
    startup to short-circuit completed tool calls during a resume.

    The index is built lazily on first read and reloaded if the
    underlying file mtime advances (``refresh_if_changed`` keeps the
    in-memory map in sync without re-reading on every query).
    """

    _FILES = ("activity.2.jsonl", "activity.1.jsonl", "activity.jsonl")

    def __init__(self, logs_path: Path | None) -> None:
        self._logs_path = Path(logs_path) if logs_path else None
        # (execution_id, idempotency_key, event_kind) -> last matching event payload
        self._index: dict[tuple[str, str, str], dict[str, Any]] = {}
        # (execution_id, guardrail_name, tool_name_or_empty) -> last hitl_resolved row
        # (parsed payload merged in). Empty tool_name slot acts as a wildcard.
        self._hitl_index: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._mtimes: dict[str, float] = {}
        self._loaded = False

    def _files(self) -> list[Path]:
        if not self._logs_path:
            return []
        return [self._logs_path / name for name in self._FILES]

    def _load(self) -> None:
        self._index.clear()
        self._hitl_index.clear()
        self._mtimes.clear()
        for path in self._files():
            if not path.exists():
                continue
            try:
                self._mtimes[path.name] = path.stat().st_mtime
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    exec_id = data.get("execution_id")
                    kind = data.get("event_kind")
                    if not exec_id or not kind:
                        continue
                    if kind == "hitl_resolved":
                        payload = self._parse_payload(data.get("payload_json"))
                        gname = str(payload.get("guardrail") or "")
                        tname = str(payload.get("tool_name") or "")
                        if gname:
                            merged = {**data, **payload}
                            # Pop-then-set so a later-emit duplicate key
                            # moves to the end of the dict, keeping the
                            # tool_name=None wildcard's reverse-iteration
                            # in true insertion (time) order.
                            key = (exec_id, gname, tname)
                            self._hitl_index.pop(key, None)
                            self._hitl_index[key] = merged
                        continue
                    idem = data.get("idempotency_key")
                    if not idem:
                        continue
                    key2 = (exec_id, idem, kind)
                    self._index.pop(key2, None)
                    self._index[key2] = data
            except OSError:
                continue
        self._loaded = True

    @staticmethod
    def _parse_payload(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _refresh_if_changed(self) -> None:
        if not self._logs_path:
            return
        for path in self._files():
            try:
                mtime = path.stat().st_mtime if path.exists() else 0.0
            except OSError:
                continue
            # Use 0.0 (not -1.0) as the missing-key default so files that
            # were absent at last load and remain absent compare equal —
            # otherwise every find_* would trigger a full reload while
            # rotated activity.{1,2}.jsonl don't exist (the common case
            # on a fresh worker).
            if self._mtimes.get(path.name, 0.0) != mtime:
                self._load()
                return

    async def find_tool_result(
        self,
        execution_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        if not self._loaded:
            self._load()
        else:
            self._refresh_if_changed()
        return self._index.get((execution_id, idempotency_key, "tool_result"))

    async def find_tool_call(
        self,
        execution_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        if not self._loaded:
            self._load()
        else:
            self._refresh_if_changed()
        return self._index.get((execution_id, idempotency_key, "tool_call"))

    async def find_hitl_resolved(
        self,
        execution_id: str,
        guardrail_name: str,
        tool_name: str | None = None,
    ) -> dict[str, Any] | None:
        if not self._loaded:
            self._load()
        else:
            self._refresh_if_changed()
        if tool_name is None:
            # True wildcard — used at agent_output where there is no
            # tool. Any indexed resolution for the guardrail counts.
            # Index insertion order matches JSONL append order; iterate
            # in reverse so the most recent match wins.
            for (exec_id, gname, _row_tool), row in reversed(self._hitl_index.items()):
                if exec_id == execution_id and gname == guardrail_name:
                    return row
            return None
        hit = self._hitl_index.get((execution_id, guardrail_name, tool_name))
        if hit is not None:
            return hit
        # Tool-agnostic fallback: an event written without a tool_name
        # applies to any tool with the same guardrail.
        return self._hitl_index.get((execution_id, guardrail_name, ""))
