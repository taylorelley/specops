# Security

## Reporting a Vulnerability

**Do not open a public GitHub issue.** Create a [private security advisory](https://github.com/saolalab/clawforce/security/advisories/new) on GitHub or email the maintainers.
## Disclaimer

AI agents are inherently susceptible to prompt injection, indirect prompt injection, social engineering, and jailbreaking. No security control fully prevents a sufficiently sophisticated attack. By using Clawforce you accept full responsibility for any actions the agent takes on your behalf.

---

## Agent Isolation (Docker Pool)

The default pool backend runs each agent in its own Docker container. This is the recommended mode for any non-development deployment.

**What the container enforces by default (`permissive` level):**
- `cap_drop=ALL` — all Linux capabilities dropped
- `no-new-privileges` — prevents privilege escalation
- Memory and CPU limits (`AGENT_DOCKER_MEM_LIMIT`, `AGENT_DOCKER_CPU_QUOTA`)
- No port mapping — workers connect out to the control plane via WebSocket only

**Stricter isolation (`sandboxed` level, UI: Safe):**

Set `security.docker.level = sandboxed` in the agent config to enable:
- Read-only root filesystem
- `tmpfs` for `/tmp`
- `network_mode=none` (no outbound network)
- `pids_limit=256`

**Full system access (`privileged` level, UI: Power):**

Set `security.docker.level = privileged` to remove capability restrictions. The agent can run `sudo` and `apt-get install` for system packages. **Use only in trusted environments** — this preset has no `cap_drop` or `no-new-privileges`.

Configure per agent via the dashboard (Settings → Security) or the API.

### Volume Isolation

Each worker container is bind-mounted with only its own data directory:

```
{ADMIN_STORAGE_ROOT}/agents/{agent_id}/   → /agent  (inside container)
```

The worker never sees `admin/`, other agents' directories, or any host path outside its own directory.

### Process Pool (Development Only)

When `ADMIN_RUNTIME_BACKEND=process`, agents run as host subprocesses. There is no OS-level isolation — only app-level guards (see Tool Security below). Use this for local development only.

---

## Secret Management

### How secrets are stored

Agent API keys and tokens live in `.config/agent.json` inside the agent's directory. This file is:
- **Hidden from the agent itself** — `AgentFS` blocks read/write access to `.config/`, `.sessions/`, and `.logs/`
- **Never returned by the config API** — `clawlib.config.helpers.redact()` masks `api_key`, `agent_token`, `password`, and other secret fields before any GET response
- **Not overwritten by config PUT** — redacted placeholders are stripped server-side so round-trips never erase real secrets

### Production recommendations

- Set `chmod 600` on `{ADMIN_STORAGE_ROOT}/agents/*/\.config/agent.json`
- Set `chmod 700` on the storage root directory
- Set `ADMIN_JWT_SECRET` to a strong random value (required when `CLAWFORCE_ENV=production`)
- Rotate agent tokens with `clawforce agent token <id> --regenerate` if compromise is suspected
- Restrict `CORS_ORIGINS` to the exact admin UI origin in production

---

## Authentication & Authorization

- **Admin users** — passwords are bcrypt-hashed; never returned by any API
- **JWT tokens** — used for dashboard/API auth; `ADMIN_JWT_SECRET` is required in production
- **Login rate limiting** — 5 requests/minute per IP
- **RBAC** — agents have an optional `owner_user_id`; only the owner or a `superadmin` can access settings, start/stop, or delete an agent
- **User management** — no HTTP API exposes user listing or creation; CLI-only (`clawforce user create`, `clawforce user update`, `clawforce user list`, `clawforce user reset`)

---

## Tool Security (App-Level)

These controls apply in both Docker and process modes. In Docker mode they are a second layer; in process mode they are the primary defense.

### Shell (`exec`)

Three layers of protection run in order:

| Layer | What it blocks |
|-------|----------------|
| `ShellCommandPolicy` | Shell injection: `$()`, backticks, `\|`, `&&`, `\|\|`, `;`, redirects |
| Deny patterns | Destructive commands: `rm -rf`, `dd`, `mkfs`, `shutdown`, `env`, `printenv` |
| Workspace restriction | Absolute paths outside the workspace, system directories (`/etc`, `/var`) |

### Filesystem (`read_file`, `write_file`, `edit_file`, `list_dir`)

`AgentFS` validates every path before any file operation:
- Blocks `..` traversal and absolute paths
- Resolves symlinks and validates the target
- `workspace/` — read/write; `profiles/` — read-only
- `.config/`, `.sessions/`, `.logs/` — inaccessible to the agent

### Network (`web_fetch`)

`NetworkSecurityPolicy` provides SSRF protection:
- Blocks all RFC 1918 ranges, localhost, and link-local addresses
- Resolves the hostname and re-checks the IP after DNS (DNS rebinding protection)
- HTTP(S) only — `file://`, `ftp://` are rejected
- Optional domain allowlist per agent

### MCP Servers

- **stdio-based** (`command:`) — run as child processes; isolated by the container in Docker mode
- **HTTP-based** (`url:`) — connect from the worker process; can make unrestricted outbound connections — use only with trusted servers

### TLS Certificate Verification

By default, every outbound HTTPS call (LLM providers, channel APIs, MCP HTTP servers, admin API, registries) and every SMTP/IMAP TLS connection verifies the remote certificate against the system trust store. `httpx` already honors `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE`, so the correct way to trust a private/internal CA in production is to install that bundle and point these variables at it.

As a last-resort escape hatch for lab, air-gapped, or MITM-proxy environments, set `CLAWFORCE_DISABLE_SSL_VERIFY=1` (or `true`/`yes`/`on`) to turn verification off globally — in clawforce, clawbot, clawlib, and every agent container spawned by the Docker runtime (the variable is passed through automatically). A one-time warning is logged the first time any component reads the flag.

**Never set this in production.** Disabling verification exposes the deployment to man-in-the-middle attacks on every outbound connection.

---

## Channel Access Control

Each channel supports an `allowFrom` list. An empty list allows all users (suitable for personal use). Set explicit IDs for production:

```yaml
channels:
  telegram:
    allowFrom: ["123456789"]
  slack:
    allowFrom: ["U012AB3CD"]
```

---

## Audit Logging

Security events are emitted to the `clawforce.audit` logger:

| Event | Fields |
|-------|--------|
| `auth_event` | `event`, `user_id`, `ip`, `success`, `detail`, `timestamp` |
| `vault_access` | `agent_id`, `ip`, `success`, `detail`, `timestamp` |

Configure your log aggregator to capture this logger for security monitoring.

---

## Known Limitations

- API keys in config are stored in plain text (no keyring by default)
- No automatic JWT session expiry
- Shell filtering blocks common patterns but is not exhaustive
- Agent tokens are stored in the database; rotate if compromised

---

## Production Checklist

- [ ] `CLAWFORCE_ENV=production` and `ADMIN_JWT_SECRET` set
- [ ] Storage root and config files have restricted permissions (`700`/`600`)
- [ ] `CORS_ORIGINS` locked to the admin UI origin
- [ ] `allowFrom` configured for all active channels
- [ ] Running as a non-root user or inside a container
- [ ] Dependencies up to date (`pip-audit`, `npm audit`)
- [ ] `clawforce.audit` logger captured and monitored
- [ ] Agent tokens rotated after any suspected exposure

---

For the latest security advisories: [GitHub Security Advisories](https://github.com/saolalab/clawforce/security/advisories)
