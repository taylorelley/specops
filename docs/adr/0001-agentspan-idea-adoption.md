# ADR 0001 — Adopt Agentspan ideas natively, do not depend on Agentspan

- Status: Proposed (Phase 0)
- Date: 2026-04-24
- Related design: [`docs/design/durability-and-tooling.md`](../design/durability-and-tooling.md)

## Context

SpecOps agents today lose in-flight state when their worker container
restarts. A turn (one inbound message → LLM → tool calls → assistant
reply) lives entirely in `SessionProcessor` memory; only the *finished*
turn is persisted (JSONL session plus activity events). Approval gates
hold `asyncio.Future`s in `specialagent/agent/approval.py`, so a
worker dying mid-approval loses the pause.

We want three things:

1. **Durable turns** — `docker kill` mid-tool-call should not silently
   re-run side-effecting tools or drop the user's request on the
   floor.
2. **Durable HITL** — humans should be able to approve or reject a
   paused agent action minutes, hours, or days later, from any
   console, even after the original worker has been recycled.
3. **OpenAPI tool ingestion** — give agents access to whole APIs in
   one click rather than wrapping every endpoint by hand or via an
   MCP server.

[Agentspan](https://github.com/agentspan-ai/agentspan) (MIT, © 2025
Agentspan) demonstrates a clean shape for all three plus a four-mode
guardrail framework that ties them together. We could either
**adopt Agentspan as a dependency** (server side and SDK) or
**port the ideas natively** into our existing Python stack.

The deciding factors:

- Agentspan's runtime is a Java / Spring Boot service backed by
  Netflix Conductor.
- SpecOps' value proposition includes a single-container
  `docker run` install — see `README.md` ("Run with Docker or
  Podman"). Adding a JVM service breaks that.
- Agentspan is MIT-licensed; SpecOps is Apache-2.0. License
  compatibility is fine in either direction at the dependency level,
  but pulling in the Java runtime would make the project's
  deployment story far more complicated than the value justifies for
  the four targeted features.
- The ideas we want (journal events, replay-safe tool model,
  guardrail enforcement points, durable HITL) map cleanly onto
  primitives we already have: `ActivityEvent` / `ActivityEventsStore`
  for an event-stream backbone, the Fernet vault for credentials,
  the existing per-agent WS channel for resume RPCs.

## Decision

Port four Agentspan ideas natively in Python, additive on top of the
existing SpecOps primitives. Do not take a runtime dependency on
Agentspan.

The four ports:

1. Durable execution journal (new `executions` and
   `execution_events` tables in the existing control-plane SQLite;
   worker buffers to `.logs/journal.jsonl`).
2. OpenAPI `api_tool` marketplace category (new `OpenAPIToolConfig`
   schema; runtime `GeneratedHttpTool` produced by an in-process
   spec parser; credentials resolve from the existing Fernet vault
   via `${VAR}` substitution).
3. Four-mode guardrail framework (`retry` / `raise` / `fix` /
   `escalate`) with three guardrail types (callable, regex,
   LLM-judge) attachable at tool input, tool output, or final agent
   output.
4. Durable HITL (a `hitl_waiting` row in the journal plus
   `executions.status="paused"`; resolve via a new
   `POST /api/executions/{id}/resolve`; resume a fresh worker via
   the existing WS channel).

Names and shapes — `GuardrailResult`, `OnFail`, `Position`,
`@guardrail`, `api_tool` — are derived from Agentspan's API. No
source code is copied. The Agentspan term `OnFail.HUMAN` is renamed
`OnFail.escalate` in SpecOps to avoid confusion with the existing
"human approval" terminology that already pervades the codebase.
The full design and migration plan live in
[`docs/design/durability-and-tooling.md`](../design/durability-and-tooling.md).

## Consequences

### Positive

- **Single-container install preserved.** No JVM, no Spring Boot, no
  Netflix Conductor, no new database engine, no new required
  service. `docker run -p 8080:8080 ghcr.io/taylorelley/specops:latest`
  remains the install story.
- **License hygiene stays clean.** SpecOps is Apache-2.0; we use
  Agentspan's API as design reference and document the derivation in
  `NOTICE`. No mixed-license code in the repository.
- **Reuse of existing primitives.** The journal extends
  `ActivityEvent`; the durable-HITL store reuses `BaseRepository[T]`;
  credential resolution reuses the Fernet-encrypted
  `AgentVariablesStore`; the resume RPC reuses the existing per-agent
  WebSocket channel. The diff stays additive across the board.
- **Schema and config additivity.** Every change is `CREATE TABLE IF
  NOT EXISTS` / `ALTER TABLE … ADD COLUMN` / a new optional config
  key. Existing roles, plan templates, marketplace items, and YAML
  files load unchanged.
- **Backwards-compatible HITL.** The current `ToolApprovalConfig`
  YAML keeps loading; the in-channel approval prompt UX stays the
  same. Only the persistence backend and the binding mechanism
  change.

### Negative

- **We re-implement what we could otherwise inherit.** The journal,
  guardrail runner, OpenAPI parser, and HITL resolve API are all
  net-new code that Agentspan would give us "for free" if we shipped
  it as a service. Mitigation: aggressive reuse of existing SpecOps
  primitives (`ActivityEvent` / `ActivityEventsStore`,
  `BaseRepository`, `AgentVariablesStore`, the WS dispatcher) keeps
  the diff smaller than a clean-room port. The ports are also
  individually small enough to land in four independent phases.
- **No automatic upstream tracking.** Agentspan can change its
  APIs and we won't get the changes for free. Mitigation: we keep
  the API surface minimal and document Agentspan-derived names in
  `NOTICE` so a future contributor can audit the lineage.
- **We carry the burden of OpenAPI parser correctness.** Spec
  edge cases (refs, oneOf, callbacks, x-extensions) are notoriously
  fiddly. Mitigation: ship hand-rolled OpenAPI 3 coverage as a
  baseline, optional `prance` upgrade for richer dialect support;
  cap risk via `max_tools` and an explicit `enabled_operations`
  override.
- **Replay-safety annotations are a new mental model.** Tool
  authors must think about whether their tool is `safe`,
  `checkpoint`, or `skip`. Mitigation: default is `checkpoint`
  (the safest choice — store the result, reuse on resume); built-in
  tools are annotated as part of Phase 1; documentation explains
  the model with concrete examples.

## Alternatives considered

### A. Take Agentspan as a runtime dependency

Run Agentspan's Java server alongside SpecOps; have SpecialAgent
workers call it for journal/guardrail/HITL services. *Rejected*
because it breaks the single-container install, adds a JVM
operational footprint (memory, ports, healthchecks), and couples
SpecOps' release cadence to Agentspan's. The license is fine; the
deployment cost is not.

### B. Embed Conductor in-container

Ship a Conductor binary inside the SpecOps Docker image. *Rejected*
because Conductor expects its own datastore (Postgres / Cassandra /
Redis) and a JVM runtime; even an embedded mode would balloon image
size by hundreds of MB and add runtime memory pressure.

### C. Build durability ourselves with no Agentspan reference

Same outcome as the chosen path but with zero design borrowing —
invent our own guardrail and journal API. *Rejected*: Agentspan's
API shape is good and well-thought-through; reimplementing the same
shape under different names adds NIH cost without benefit. We
derive the shape, attribute it, and move on.

### D. Defer the work indefinitely

Keep ephemeral turns and in-memory approvals. *Rejected* because
mid-turn restarts are a real user-visible failure mode (any agent
that runs `exec` or writes files can trip it), and durable HITL is
a recurrent product ask.

## References

- Agentspan project: https://github.com/agentspan-ai/agentspan (MIT)
- Agentspan README, accessed Phase 0
- SpecOps `README.md` — install story
- `specops_lib/activity.py` — `ActivityEvent` envelope reused
- `specops/core/store/activity_events.py` — `INSERT OR IGNORE`
  pattern reused
- `specops/core/store/agent_variables.py` — Fernet vault reused
- `specialagent/core/admin.py` — WebSocket dispatcher reused
- Phase 0 design: `docs/design/durability-and-tooling.md`
