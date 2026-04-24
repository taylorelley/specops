# Execution events

The durable execution journal records what an agent did during one
inbound message. The events power crash recovery: if a worker is
killed mid-tool-call, a fresh worker mounting the same data root reads
the journal and short-circuits any side-effecting tool whose call
already completed. Half-completed calls surface as `[INTERRUPTED]`
rather than re-running the side effect.

## Schema

Events extend the same `ActivityEvent` envelope used by the audit log.
Journal-mode events additionally carry:

| Field | Type | Notes |
| --- | --- | --- |
| `execution_id` | string (UUID) | One per inbound message. |
| `step_id` | string (e.g. `"step:0"`) | One per LLM iteration inside an execution. |
| `event_kind` | string | Closed enum, see below. |
| `replay_safety` | string \| null | Tool events only: `"safe"`, `"checkpoint"`, or `"skip"`. |
| `idempotency_key` | string \| null | sha256 by default; tools may override via `Tool.compute_idempotency_key(args)`. |
| `payload_json` | string \| null | JSON-encoded payload (tool args, tool result, LLM message). |

`event_id` (UUID) and `INSERT OR IGNORE` keep the journal idempotent
under WS reconnects, mirroring the activity log.

## Event kinds

| `event_kind` | Emitted when |
| --- | --- |
| `execution_started` | First event of a turn. Payload carries channel/chat_id/session_key — the control plane uses these to seed the `executions` row. |
| `step_started` | LLM iteration starts. |
| `step_completed` | LLM iteration finishes (tool round complete, or final assistant message). |
| `llm_request` | Reserved for future phases. |
| `llm_response` | Reserved for future phases. |
| `tool_call` | About to dispatch a tool. Carries `replay_safety` and `idempotency_key`. |
| `tool_result` | Tool returned. Carries `result_status`, `duration_ms`, and (for journal use) `payload_json` with the tool output. |
| `guardrail_result` | Reserved for Phase 3. |
| `hitl_waiting` | Reserved for Phase 4. |
| `hitl_resolved` | Reserved for Phase 4. |
| `error` | Reserved. |

## Replay-safety values

- **`safe`** — Tool is pure-read or otherwise idempotent; resume always
  re-executes. Examples: `read_file`, `list_dir`, `workspace_tree`,
  `web_search`, `web_fetch`, read-only plan tools.
- **`checkpoint`** — Tool has external side effects. On resume:
  - If a journaled `tool_result` exists for the same
    `(execution_id, idempotency_key)`, the dispatcher reuses its
    output without re-executing.
  - If only `tool_call` exists, the dispatcher returns
    `[INTERRUPTED] …` so the LLM can decide whether to ask the user
    rather than re-running a side-effecting tool.
  - This is the default for any tool that doesn't explicitly opt
    into another value.
- **`skip`** — Strongest setting. A `tool_call` with no matching
  `tool_result` aborts the step with `[RESUME UNSAFE]` and the
  execution is treated as failed. Reserved for tools where re-running
  AND quietly skipping would both be wrong (e.g. payments).

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/agents/{id}/executions` | List executions for an agent (optional `?status=` filter). |
| `GET` | `/api/executions/{id}` | One execution row (status, last step, channel/chat_id). |
| `GET` | `/api/executions/{id}/events` | Journal stream, paginated via `?after_id=`. |
| `POST` | `/api/executions/{id}/resume` | Phase-1 admin hand-crank: re-deliver the original message to the worker over WebSocket so the journal can short-circuit completed tools. Phase 4 supersedes this with `/resolve` for HITL flows. |

See [`docs/design/durability-and-tooling.md`](../design/durability-and-tooling.md)
for the full design.
