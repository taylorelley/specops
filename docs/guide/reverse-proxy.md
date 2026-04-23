# Reverse Proxy

Run Clawforce behind an existing reverse proxy with a public subdomain, e.g. `https://clawforce.example.com`. TLS is terminated at the proxy; the container stays on loopback.

## Minimum working setup

Bind the container to `127.0.0.1` so only the proxy can reach it:

```bash
docker run -d --name clawforce --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v $HOME/.clawforce-data:/data \
  -e AGENT_STORAGE_HOST_PATH=$HOME/.clawforce-data \
  -e ADMIN_SETUP_USERNAME=admin \
  -e ADMIN_SETUP_PASSWORD='change-me-now' \
  -e CORS_ORIGINS=https://clawforce.example.com \
  ghcr.io/saolalab/clawforce:latest
```

Then point your proxy at it. Caddy is the shortest working example — it handles TLS and WebSocket upgrades automatically:

```caddy
clawforce.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

## docker-compose

Easier to redeploy and pin env separately:

```yaml
services:
  clawforce:
    image: ghcr.io/saolalab/clawforce:latest
    restart: unless-stopped
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      AGENT_STORAGE_HOST_PATH: /srv/clawforce/data
      ADMIN_SETUP_USERNAME: admin
      ADMIN_SETUP_PASSWORD: ${CLAWFORCE_ADMIN_PASSWORD}
      CORS_ORIGINS: https://clawforce.example.com
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - /srv/clawforce/data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

## Nginx

Nginx needs explicit headers for the features that silently break otherwise — WebSockets (control hub, terminal panel) and SSE (log tails):

```nginx
server {
    listen 443 ssl http2;
    server_name clawforce.example.com;
    # ssl_certificate ...; ssl_certificate_key ...;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;

        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket upgrade (control hub, per-agent terminals)
        proxy_set_header Upgrade    $http_upgrade;
        proxy_set_header Connection "upgrade";

        # SSE log streams / long-lived terminals
        proxy_buffering     off;
        proxy_read_timeout  1d;
        proxy_send_timeout  1d;
    }
}
```

## Environment variables

| Variable | Default | Notes |
|----------|---------|-------|
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:8080` | Comma-separated allowlist. Add your public URL. |
| `ADMIN_SETUP_USERNAME` | `admin` | Seeded on **first boot only**. |
| `ADMIN_SETUP_PASSWORD` | `admin` | Seeded on **first boot only** — rotate in the UI afterwards. |
| `AGENT_STORAGE_HOST_PATH` | unset | Must match the host path you mounted to `/data`, so sibling agent containers get the right workspace mount. |
| `ADMIN_PUBLIC_URL` | `http://host.docker.internal:8080` | URL agent containers use to reach the admin. See tradeoff below. |

## `ADMIN_PUBLIC_URL` tradeoff

Agent workers are **sibling containers** spawned via the Docker socket. They connect back to the admin at `ADMIN_PUBLIC_URL`. The default `http://host.docker.internal:8080` keeps this traffic on the Docker network — fast, private, no proxy round-trip.

**Don't override to the public HTTPS URL** unless you have to. Override cases:

- **Remote Docker daemon** (`DOCKER_HOST` pointing at another host) — set `ADMIN_PUBLIC_URL` to an IP/hostname reachable from that host.
- **Agents running off-host** — same idea.

If you do override to the public URL, ensure the proxy passes WebSocket upgrades (above) — agents connect via `/api/control/ws`.

## Multi-worker sticky sessions

When running `uvicorn --workers N > 1`, each worker holds its own WebSocket connections and activity registry. Pin per-client traffic to one worker so `/api/control/ws` and `/api/agents/*/logs` stay consistent:

```nginx
upstream clawforce_backend {
    ip_hash;
    server 127.0.0.1:8080;
    # add more workers / backends here
}

server {
    # ...
    location / {
        proxy_pass http://clawforce_backend;
        # + all the proxy_set_header / buffering lines above
    }
}
```

See [Configuration → 503 Agent Offline](/guide/configuration#troubleshooting-503-agent-offline) for related troubleshooting.

## TLS certificate verification

If agents talk to MCP servers or APIs with private CAs, see [Security → TLS Certificate Verification](/guide/security) for `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, and `CLAWFORCE_DISABLE_SSL_VERIFY`.

## Security notes

- **Docker socket = root-equivalent.** Anything that can reach this container controls Docker. Protect the vhost (auth, IP allowlist, or at least keep it behind a firewall).
- **Loopback bind.** `-p 127.0.0.1:8080:8080` keeps the API off the public interface; only the proxy can reach it.
- **First-run password.** `ADMIN_SETUP_PASSWORD` only seeds the initial admin user. Rotate via the UI immediately after first login.

## Verification checklist

Once the container is running and the proxy is configured:

1. `https://clawforce.example.com` loads the dashboard and accepts the admin login.
2. Open an agent's **Terminal** panel — proves WebSocket upgrade is working.
3. Tail agent **Logs** — proves SSE works (no buffering, no mid-stream disconnect).
4. Deploy an agent from the **Marketplace** — proves Docker socket mount and `AGENT_STORAGE_HOST_PATH` are correct.
5. `curl -I https://clawforce.example.com/api/health` returns `200 OK`.
