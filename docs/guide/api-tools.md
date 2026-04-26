# API Tools

API Tools turn an OpenAPI 3 / Swagger 2 / Postman v2.1 spec into
agent-callable tools. The agent worker fetches the spec at startup,
filters down to the most relevant operations, generates one tool per
operation, and resolves credentials from the encrypted variable vault
at runtime.

This is the Phase 2 deliverable of the
[Agentspan idea adoption project](../adr/0001-agentspan-idea-adoption.md).

## How it works

1. **Catalog**: bundled entries (Stripe, GitHub, OpenAI) ship in
   [`marketplace/api-tools/catalog.yaml`](https://github.com/taylorelley/specops/blob/main/marketplace/api-tools/catalog.yaml).
   You can add your own via the **Add Custom** button on the API Tools
   tab in the Marketplace, or by `POST`ing to
   `/api/api-tools/custom`.
2. **Install**: pick an agent and supply the credential values listed
   under `required_env`. The values land in the agent's encrypted
   variable vault.
3. **At agent start**: the worker fetches the spec (cached on disk under
   `agents/<agent_id>/.config/api-tools/<spec_id>.json`), parses it,
   keeps the top-N operations (default 64), and registers one
   `GeneratedHttpTool` per operation.
4. **At tool call time**: `${VAR}` placeholders in the header template
   are substituted from the vault, the request is built and sent via
   `httpx` (with the same SSRF guard as `web_fetch`), and the response
   is returned to the LLM.

## Supported spec formats

| Dialect | Notes |
| --- | --- |
| OpenAPI 3.x | Path / query / header parameters; JSON request bodies. `$ref` resolution is best-effort — operations that depend on heavy schema chains may have less precise tool parameters. |
| Swagger 2.0 | `host` + `basePath` form the base URL. `body` parameters are promoted to a request body. |
| Postman 2.1 | Each item with a `request` becomes one tool. |

## Top-N filtering

Most LLMs degrade past ~64 tool definitions, and big specs (AWS,
Salesforce, Microsoft Graph) ship thousands of operations. The
generator caps at `max_tools` (default 64) using:

1. If `enabled_operations` is set, it wins (exact match by
   `operationId`).
2. Otherwise the operations are scored by token-set overlap between
   `tags + summary + path + description` and the agent's role
   description. Higher score wins.
3. Tiebreak: shorter `operationId` first.

A hard cap (`MAX_TOOLS_HARD_CAP = 64`) is enforced regardless of the
config.

## Replay safety

Generated tools default to `replay_safety = "checkpoint"` — the safe
choice for HTTP calls with side effects. If a particular operation is
read-only (`GET /things/{id}`), annotate it in the spec with the
extension `x-replay-safety: safe` so the durable execution journal
knows it's safe to re-run on resume.

```yaml
paths:
  /pets/{petId}:
    get:
      operationId: showPetById
      x-replay-safety: safe
      parameters:
        - name: petId
          in: path
          required: true
          schema: { type: string }
```

## Credential templating

Header values are templates with `${VAR}` placeholders, resolved at
request time:

```yaml
- id: stripe
  spec_url: https://api.stripe.com/openapi.json
  headers:
    Authorization: "Bearer ${STRIPE_KEY}"
  required_env:
    - STRIPE_KEY
```

The user supplies `STRIPE_KEY` once, at install time. It's stored
encrypted (Fernet) in the per-agent variable vault and never written
to disk in plaintext. If a placeholder has no matching value the
generated tool returns a clear error message rather than sending an
unauthenticated request.

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/api-tools/registry?q=…` | Search the catalog (bundled + custom). |
| `GET` | `/api/api-tools/registry/{id}` | Single entry. |
| `GET` | `/api/api-tools/custom` | List self-hosted entries. |
| `POST` | `/api/api-tools/custom` | Add a self-hosted entry. |
| `PUT` | `/api/api-tools/custom/{id}` | Update a self-hosted entry. |
| `DELETE` | `/api/api-tools/custom/{id}` | Remove a self-hosted entry. |
| `GET` | `/api/agents/{id}/api-tools` | List installed tools for an agent. |
| `POST` | `/api/agents/{id}/api-tools/install` | Install on an agent. |
| `DELETE` | `/api/agents/{id}/api-tools/{spec_id}` | Uninstall. |

## Limitations

- Authentication beyond bearer tokens / API keys (OAuth flows, AWS
  Sigv4) is not implemented; for those, use a dedicated MCP server.
- Operations that require multipart/form-data uploads are accepted by
  the parser but the generated tool only sends JSON bodies.
- The hand-rolled OpenAPI parser supports the 80% case; for very
  complex specs install the optional `prance` extra and the worker
  will use it transparently.
