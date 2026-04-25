# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed (BREAKING)
- **Rebrand: Clawforce → SpecOps, Clawbot/Claws → SpecialAgents.** Deep rename across the full stack.
  - Python distributions and imports: `clawforce` → `specops`, `clawbot` → `specialagent`, `clawlib` → `specops_lib`. Update any `from clawforce…/clawbot…/clawlib…` imports.
  - CLI commands: `clawforce` → `specops`, `clawbot` → `specialagent`.
  - Environment-variable prefixes: `CLAWFORCE_*` → `SPECOPS_*`, `CLAWBOT_*` → `SPECIALAGENT_*`. Update `.env` files and deployment configs.
  - Docker images and container names: `ghcr.io/saolalab/clawforce` → `ghcr.io/taylorelley/specops`; agent container prefix `clawbot-agent-` → `specialagent-`.
  - UI routes, components, hooks: `/claws` → `/specialagents`; `ClawIcon`/`CreateClawModal`/`ClawsList` → `SpecialAgentIcon`/`CreateSpecialAgentModal`/`SpecialAgentsList`; `useClaws`/`useCreateClaw` → `useSpecialAgents`/`useCreateSpecialAgent`.
  - Skill frontmatter metadata key: primary key is now `"specialagent"`; the parser keeps `"clawbot"` and `"openclaw"` as legacy fallbacks so previously-published skill packs still load.
  - npm bridge package: `@clawbot/whatsapp-bridge` → `@specialagent/whatsapp-bridge` (binary `specialagent-whatsapp-bridge`).

### Added
- **Plan Templates** marketplace category. Bundled starter templates (product-launch, sprint-planning, bug-triage, research-project) plus full CRUD for user-managed custom templates. New `/api/plan-templates` endpoints and an optional `template_id` on `POST /api/plans` that seeds the new plan with the template's columns and tasks. When creating a plan in the UI, choose **Blank Plan** or **From Template**.
- Plan templates can **preassign agents** at the plan level (`agent_ids`) and at the task level (`agent_id`). Missing agent ids are silently skipped at plan-creation time. The Add Plan Template modal lets you pick agents as chips (plan-level) and dropdowns (per task), and the detail modal shows preassigned agents with a stale/missing indicator.
- **Durable execution journal for SpecialAgent (Phase 1 of Agentspan
  idea adoption).** Each inbound message starts an `Execution` (UUID);
  the agent loop emits structured journal events
  (`execution_started`, `step_started`, `step_completed`, `tool_call`,
  `tool_result`) through the existing activity stream. The control
  plane routes events with an `execution_id` into two new tables —
  `executions` and `execution_events` — alongside the existing
  `activity_events` audit log. New REST endpoints:
  `GET /api/agents/{id}/executions`, `GET /api/executions/{id}`,
  `GET /api/executions/{id}/events`, and a Phase-1 admin hand-crank
  `POST /api/executions/{id}/resume` that re-delivers the original
  message to the worker via a new `{type: "resume", …}` WebSocket
  message. The worker's `LocalJournalLookup` reads
  `.logs/activity.jsonl` (and rotated siblings) so a fresh worker on
  the same data root short-circuits previously-completed tool calls.
  No user action required at upgrade: tables are created with
  `CREATE TABLE IF NOT EXISTS`, no data backfill, no config change.
  Pre-existing turns in flight at upgrade time are not retroactively
  journaled. Design: `docs/design/durability-and-tooling.md`. ADR:
  `docs/adr/0001-agentspan-idea-adoption.md`.
- **Replay-safety attribute on `Tool`.** A new
  `Tool.replay_safety: ClassVar[Literal["safe","checkpoint","skip"]]`
  defaults to `"checkpoint"` (the conservative choice). Built-in
  read-only tools (`read_file`, `list_dir`, `workspace_tree`,
  `web_search`, `web_fetch`, the read-only plan tools, and
  `a2a_discover`) are annotated `"safe"`; side-effecting tools
  (writes, `exec`, `message`, `spawn`, `cron`, plan mutations,
  `a2a_call`, MCP wrappers) keep the conservative default. Tool
  authors may override `Tool.compute_idempotency_key(args)` to supply
  a custom dedup key (Stripe-style). On resume: completed
  `checkpoint`-safety calls short-circuit to the cached result; a
  half-completed `checkpoint` call (tool_call written, no
  tool_result) surfaces as `[INTERRUPTED]` to the LLM rather than
  re-executing the side effect; `skip`-safety surfaces
  `[RESUME UNSAFE]` and aborts the step.
- **API Tools marketplace category (Phase 2 of Agentspan idea
  adoption).** A new `marketplace/api-tools/catalog.yaml` ships with
  bundled entries (Stripe, GitHub, OpenAI). On install, the agent
  worker fetches the spec at startup (cached under
  `.config/api-tools/`), filters to up to `max_tools` operations
  using a token-set overlap with the agent's role hint, and
  registers one `GeneratedHttpTool` per operation. Header templates
  carry `${VAR}` placeholders resolved from the encrypted variable
  vault at request time — credentials never live on disk in
  plaintext. Specs may opt operations into `replay_safety="safe"`
  via the `x-replay-safety` extension. New REST endpoints under
  `/api/api-tools/*` and `/api/agents/{id}/api-tools/*`. New
  Marketplace tab **API Tools** (sits between MCP Servers and
  Software). New `OpenAPIToolConfig` schema (declares
  `secret_fields = {"headers"}`) plumbed under
  `tools.openapi_tools`. Hand-rolled parser covers OpenAPI 3 /
  Swagger 2 / Postman v2.1 — the optional `prance` extra is detected
  lazily and used when present.

### Fixed
- **`MCPServerConfig` now redacts `headers` and `env` in API
  responses.** Previously these credential-bearing fields were
  exposed in plaintext through the config-fetch endpoint because
  the model didn't declare them as secrets. Both are now in
  `MCPServerConfig.secret_fields` and the path-aware redactor walks
  through `dict[str, MCPServerConfig]` correctly. Existing stored
  configs are unchanged on disk; redaction happens at API response
  time.

### Notes
- The new `executions` and `execution_events` tables are additive.
  `_migrate()` (`specops/core/database.py`) creates them with
  `CREATE TABLE IF NOT EXISTS` on first start, so existing databases
  upgrade transparently with no manual migration step.
- The WebSocket protocol additions (the new `resume` message type and
  the new optional fields on activity events) are also additive.
  Workers built before this release ignore the `resume` message
  through the dispatcher's default fall-through and the activity
  push path simply omits the new optional fields.

