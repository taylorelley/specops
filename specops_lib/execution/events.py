"""Journal-event types and pure helpers.

Kept dependency-free (no I/O, no SQL) so both the worker and the
control plane can import these. Persistence lives in
``specops_lib.execution.journal`` (worker buffer) and
``specops.core.store.execution_events`` (control plane).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Literal, Mapping

from specops_lib.activity import ActivityEvent

EventKind = Literal[
    "execution_started",
    "step_started",
    "step_completed",
    "llm_request",
    "llm_response",
    "tool_call",
    "tool_result",
    "guardrail_result",
    "hitl_waiting",
    "hitl_resolved",
    "error",
]

ReplaySafety = Literal["safe", "checkpoint", "skip"]

ExecutionStatus = Literal["running", "paused", "failed", "completed"]

EVENT_KINDS: tuple[EventKind, ...] = (
    "execution_started",
    "step_started",
    "step_completed",
    "llm_request",
    "llm_response",
    "tool_call",
    "tool_result",
    "guardrail_result",
    "hitl_waiting",
    "hitl_resolved",
    "error",
)

REPLAY_SAFETIES: tuple[ReplaySafety, ...] = ("safe", "checkpoint", "skip")

EXECUTION_STATUSES: tuple[ExecutionStatus, ...] = (
    "running",
    "paused",
    "failed",
    "completed",
)


def derive_idempotency_key(
    execution_id: str,
    step_id: str,
    tool_name: str,
    args: Mapping[str, Any],
) -> str:
    """Default idempotency key for a tool call inside one execution step.

    The key is stable across worker restarts as long as the four inputs
    are stable, which means a re-run of the same tool with the same
    args at the same step collapses onto the same journal row.
    """
    canonical = json.dumps(
        dict(args),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    payload = f"{execution_id}|{step_id}|{tool_name}|{canonical}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_event(
    *,
    agent_id: str,
    event_type: str,
    execution_id: str,
    step_id: str,
    event_kind: EventKind,
    channel: str = "",
    content: str = "",
    plan_id: str = "",
    tool_name: str | None = None,
    tool_args_redacted: dict[str, Any] | None = None,
    result_status: str | None = None,
    duration_ms: int | None = None,
    replay_safety: ReplaySafety | None = None,
    idempotency_key: str | None = None,
    payload_json: str | None = None,
) -> ActivityEvent:
    """Construct an ``ActivityEvent`` carrying journal fields."""
    return ActivityEvent(
        agent_id=agent_id,
        event_type=event_type,
        channel=channel,
        content=content,
        plan_id=plan_id,
        tool_name=tool_name,
        tool_args_redacted=tool_args_redacted,
        result_status=result_status,
        duration_ms=duration_ms,
        event_id=uuid.uuid4().hex,
        execution_id=execution_id,
        step_id=step_id,
        event_kind=event_kind,
        replay_safety=replay_safety,
        idempotency_key=idempotency_key,
        payload_json=payload_json,
    )


def journal_fields(event: ActivityEvent) -> dict[str, Any]:
    """Return the journal-only fields for serialisation, omitting Nones."""
    out: dict[str, Any] = {}
    if getattr(event, "execution_id", None):
        out["execution_id"] = event.execution_id
    if getattr(event, "step_id", None):
        out["step_id"] = event.step_id
    if getattr(event, "event_kind", None):
        out["event_kind"] = event.event_kind
    if getattr(event, "replay_safety", None):
        out["replay_safety"] = event.replay_safety
    if getattr(event, "idempotency_key", None):
        out["idempotency_key"] = event.idempotency_key
    if getattr(event, "payload_json", None) is not None:
        out["payload_json"] = event.payload_json
    return out
