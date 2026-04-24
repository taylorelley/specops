# CLAUDE.md

Guidance for Claude Code when working in this repository. Keep it current when structure or workflow changes.

## Project overview

SpecOps is a multi-agent orchestration platform. A FastAPI **control plane** manages users, plans (Kanban), and agent lifecycles, and spawns **agent workers** that run in isolation (Docker/Podman container or local subprocess) and connect back over a per-agent WebSocket. Agents use LLMs via LiteLLM, call tools (filesystem, shell, web, MCP servers, agent-to-agent messaging) and integrate with chat platforms (Telegram, Slack, Discord, Feishu, WhatsApp, Zalo, Email). Marketplace roles let users deploy pre-built agent templates with one click.

Apache 2.0, currently beta. See `README.md` for product features and `docs/` for the full VitePress site.

## Repository layout

This is a `uv` workspace (root `pyproject.toml:1-2`) with three Python packages, plus a React UI, Node bridges, and assets.

- `specops_lib/` — shared library: `storage/` (local + S3), `config/schema.py` (all Pydantic config models), `channels/` (plugin channel adapters), `registry/` (skills, MCP, software, plan templates), `activity.py`, `bus.py`. Imported by both `specops` and `specialagent`.
- `specialagent/` — agent worker framework. `agent/loop/core.py` is the main loop; tools in `agent/tools/`; LLM providers in `providers/`; WebSocket client to the admin in `worker/`. CLI: `specialagent`.
- `specops/` — admin control plane. FastAPI app (`app.py`), REST routers (`apis/`), repositories (`core/store/`, SQLite), runtime backends (`core/runtimes/`), auth (JWT + bcrypt), Fernet-encrypted secrets. CLI: `specops`.
- `specops-ui/` — React 19 + Vite + Tailwind SPA. Builds into `specops/static/`, which the backend serves.
- `bridges/whatsapp/`, `bridges/zalo/` — standalone TypeScript/Node bridges to third-party messaging.
- `marketplace/roles/`, `marketplace/plan-templates/`, `marketplace/softwares/` — YAML templates shipped with the app.
- `deploy/` — multi-stage `Dockerfile` (Node 20 builder → Ubuntu 24.04 + Python 3.12) and `entrypoint.sh`.
- `docs/` — VitePress site (`guide/`, `reference/`, `.vitepress/`).
- `scripts/` — `install.sh`, `install.ps1`, `dev.sh` (container dev loop).
- `tests/` — pytest suite (asyncio auto mode).

## Architecture at a glance

Three tiers, single dependency direction:

```
specops-ui (React)  ──HTTP/WS──▶  specops (control plane)  ──per-agent WS──▶  specialagent (worker)
                                            │                                          │
                                            └──────────── specops_lib ─────────────────┘
```

- Build / import order: `specops_lib` → `specialagent` → `specops`. Anything shared between control plane and worker belongs in `specops_lib/`.
- Agent data rooted at `$ADMIN_STORAGE_ROOT` (default `$HOME/.specops-data`; Makefile targets override to `./data`). Layout: `specops.db`, `admin/`, `agents/<id>/{profiles,workspace,.config,.sessions,.logs}`.
- Storage is abstracted (`specops_lib/storage/`) — local FS or S3-compatible via `boto3`. Don't read/write the data root directly; go through the backend.
- Version is not hardcoded — `hatch-vcs` derives it from git tags (`CONTRIBUTING.md:51`). Local builds without a tag become `0.0.0.dev0`.

## Tech stack

- **Python** 3.11+ (ruff `target-version = "py311"`). Key libs: FastAPI, Uvicorn, Pydantic v2, LiteLLM, MCP, PyJWT, bcrypt, boto3 (optional S3), croniter, loguru, typer, slowapi.
- **Frontend**: React 19, React Router 7, Vite 6, Tailwind 3, TanStack Query, xterm.js, Monaco.
- **Node bridges**: TypeScript, compiled to `dist/`.
- **Container**: Docker or Podman (auto-detected by `Makefile:10`).

## Common commands

Use these instead of improvising — env vars and paths are baked into the Makefile.

| Task | Command |
|---|---|
| Install everything | `make install` (`uv sync --group dev` + `npm install` in `specops-ui/`) |
| Create default admin user | `make setup` (admin/admin, data in `./data`) |
| Backend dev server (hot-reload, :8080) | `make backend` |
| Frontend dev server (:5173) | `make frontend` |
| Production SPA build → `specops/static/` | `make build` |
| Run tests | `make test` (≡ `uv run python -m pytest tests/ -v`) |
| Lint check | `make lint` (ruff check + format check) |
| Auto-fix / format | `make lint-fix`, `make format` |
| Container dev loop | `make container` (override engine: `ENGINE=podman make container`) |
| Stop all containers | `make container-stop` |
| Docs dev server | `make docs-dev`; build+preview: `make docs` |
| Clean caches | `make clean` |

Pre-commit hooks: `pre-commit install` once after `make install`.

## Code style & conventions

- **Ruff** (line length 100, `py311`), rule set `E, F, I, N, W, PLC0415, S`. Global ignores at `pyproject.toml:27-40`.
- **Lazy imports are deliberate.** `PLC0415` is enforced repo-wide but a long list of per-file exemptions at `pyproject.toml:42-101` covers CLIs, channel plugins, factories, optional SDKs, and tests that must import after monkeypatching env. When adding a new module that fits one of these patterns (optional dep, faster CLI `--help`, factory), add a targeted per-file exemption instead of disabling the rule.
- **mypy** runs in CI with `continue-on-error`; config at `pyproject.toml:116-126`. Treat output as informational, not blocking.
- **Pre-commit** hooks: `ruff`, `ruff-format`, `detect-secrets` (baseline `.secrets.baseline`).
- **Pydantic models** use `populate_by_name=True` so APIs accept camelCase while Python stays `snake_case`. Config models with secrets declare `secret_fields: ClassVar[frozenset[str]]` for redaction — preserve this when editing `specops_lib/config/schema.py`.
- **Plugin patterns** — follow the existing base/registry when extending:
  - Stores: inherit `BaseRepository[T]` in `specops/core/store/base.py`.
  - Channels: inherit `BaseChannel` in `specops_lib/channels/base.py`; SDK imports wrapped in `try/except ImportError` with a `PLC0415` exemption.
  - Tools: inherit `BaseTool` in `specialagent/agent/tools/base.py`; third-party tools may also register via setuptools entry points (`specialagent/agent/tools/registry.py`).
  - LLM providers: register through `specialagent/providers/registry.py`.
- **Comments**: match the existing minimal-comment style; prefer self-describing names.

## Testing notes

- `asyncio_mode = "auto"` (`pyproject.toml:103-105`) — don't add `@pytest.mark.asyncio`.
- Coverage gate `fail_under = 25` across `specops_lib`, `specialagent`, `specops` (`pyproject.toml:107-114`). CI invokes `uv run pytest tests/ -v --cov --cov-report=term-missing --cov-report=xml`.
- Tests that monkeypatch env vars (`ADMIN_STORAGE_ROOT`, etc.) intentionally import inside the test function so the patched value is honored — see `pyproject.toml:96-101` per-file exemptions. Follow that pattern for new env-sensitive tests.

## CLI entry points

- `specops` → `specops/cli.py:app`. Subcommands: `setup`, `serve`, `agent {list,create,start,stop,token}`, `user {create,list,update,set-password}`.
- `specialagent` → `specialagent/cli.py:main`. Subcommands: `run --agent-root ... --admin-url ... --token ...`, `init <path>`, `config`, `version`.

## Files to know

- Shared config schema (channels, tools, providers): `specops_lib/config/schema.py`.
- Agent main loop: `specialagent/agent/loop/core.py` (see also `loop/session.py`, `loop/tools.py`, `loop/mcp.py`).
- Tool implementations: `specialagent/agent/tools/{filesystem,shell,web,mcp,plan,message,a2a,cron,spawn,software_exec}.py`.
- REST routers: `specops/apis/*.py`.
- Persistence (SQLite, Fernet for secrets): `specops/core/store/*.py`.
- Runtime backends (selected via `factory.py`): `specops/core/runtimes/{docker,local}.py`.
- Frontend API layer: `specops-ui/src/lib/api.ts`.

## Things to avoid

- Don't hardcode a version — `hatch-vcs` reads the git tag.
- Don't make a channel SDK a hard dependency; keep the `try/except ImportError` + `PLC0415` lazy-import pattern so installs without that extra still work.
- Don't bypass `specops_lib/storage` for file I/O against the data root — going direct breaks the S3 backend.
- Don't commit files under `specops/static/` by hand; they're produced by `make build` (or by stage 1 of `deploy/Dockerfile`).
- Don't add `CLAUDE.md` to subpackages without a reason — keep guidance centralized here.
