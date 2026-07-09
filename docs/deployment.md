# Deployment

OpenChatRelay is designed to run as a small self-hosted stack first, then scale
out behind a reverse proxy or container orchestrator as traffic grows.

## Public Surface

Expose only the API service to users and client applications:

- HTTP API
- WebSocket realtime endpoint
- SSE event streams
- Future WebTransport gateway

Keep infrastructure services private whenever possible:

- PostgreSQL
- Redis
- MinIO / S3-compatible object storage

The default Compose file binds PostgreSQL, Redis, and MinIO to `127.0.0.1` on
the host. They are reachable by containers through the Compose network, but not
from other machines unless you intentionally change the bind host.

## Configurable Host Ports

Container-internal ports stay stable, while host ports can be changed in `.env`.
This avoids conflicts with services already deployed on the same server.

```env
OPEN_CHAT_RELAY_API_BIND_HOST=0.0.0.0
OPEN_CHAT_RELAY_API_HOST_PORT=8000

OPEN_CHAT_RELAY_POSTGRES_BIND_HOST=127.0.0.1
OPEN_CHAT_RELAY_POSTGRES_HOST_PORT=5432

OPEN_CHAT_RELAY_REDIS_BIND_HOST=127.0.0.1
OPEN_CHAT_RELAY_REDIS_HOST_PORT=6379

OPEN_CHAT_RELAY_MINIO_BIND_HOST=127.0.0.1
OPEN_CHAT_RELAY_MINIO_HOST_PORT=9000
OPEN_CHAT_RELAY_MINIO_CONSOLE_BIND_HOST=127.0.0.1
OPEN_CHAT_RELAY_MINIO_CONSOLE_HOST_PORT=9001
```

For example, if port `8000` is already used:

```env
OPEN_CHAT_RELAY_API_HOST_PORT=18000
```

The API will then be reachable at:

```text
http://SERVER_IP:18000
```

## Production Baseline

Before deploying publicly, set:

```env
OPEN_CHAT_RELAY_ENVIRONMENT=production
OPEN_CHAT_RELAY_DEBUG=false
OPEN_CHAT_RELAY_DOCS_ENABLED=false
OPEN_CHAT_RELAY_JWT_SECRET_KEY=replace-with-a-long-random-secret
OPEN_CHAT_RELAY_CORS_ORIGINS=https://your-console.example.com,https://your-app.example.com
OPEN_CHAT_RELAY_RATE_LIMIT_BACKEND=redis
```

In production, the API validates unsafe settings at startup and refuses to boot
with the default JWT secret, debug mode, or wildcard CORS origins.

For a Docker-based production deployment, start from the production template:

```bash
cp .env.production.example .env
python3 scripts/generate_deployment_secrets.py
```

Copy the generated values into `.env`, then replace the public URL placeholders:

```env
OPEN_CHAT_RELAY_PUBLIC_API_URL=https://api.example.com
OPEN_CHAT_RELAY_CONSOLE_API_BASE_URL=https://api.example.com
OPEN_CHAT_RELAY_CORS_ORIGINS=https://console.example.com,https://app.example.com
OPEN_CHAT_RELAY_WEBTRANSPORT_URL=https://chat.example.com:18081/v1/wt
OPEN_CHAT_RELAY_S3_PUBLIC_ENDPOINT_URL=https://files.example.com
```

The template intentionally uses non-default host ports such as `18000`,
`15173`, `15432`, `16379`, `19000`, and `18081` so it can coexist with services
already running on the same server. Change those values in `.env` if your server
uses a different port plan.

## Reverse Proxy

For public HTTPS deployments, place a reverse proxy in front of the API,
console, and file endpoint:

```text
Internet
  -> Caddy / Nginx / Traefik
  -> OpenChatRelay API / console / MinIO containers
```

The proxy should forward:

- HTTP API requests
- WebSocket upgrade requests
- SSE responses without buffering
- large attachment uploads and downloads

A Caddy baseline for a single-server deployment:

```caddyfile
api.chat.example.com {
	reverse_proxy 127.0.0.1:18000
}

console.chat.example.com {
	reverse_proxy 127.0.0.1:15173
}

files.chat.example.com {
	request_body {
		max_size 500MB
	}
	reverse_proxy 127.0.0.1:19000
}
```

WebTransport is different from the normal HTTP services. Browser WebTransport
uses HTTP/3 over QUIC, so the public runtime needs UDP. The Docker production
template maps gateway TCP to `127.0.0.1:18081` for local health/smoke checks and
maps gateway UDP to `0.0.0.0:18081` for public WebTransport sessions. Do not put
the WebTransport runtime behind a normal HTTP reverse proxy unless that proxy is
explicitly configured to pass through compatible HTTP/3/QUIC traffic.

Recommended DNS:

```text
api.chat.example.com      -> SERVER_IP
console.chat.example.com  -> SERVER_IP
files.chat.example.com    -> SERVER_IP
wt.chat.example.com       -> SERVER_IP
```

Recommended firewall:

```text
80/tcp, 443/tcp       reverse proxy TLS
18081/udp             WebTransport HTTP/3 runtime
18081/tcp             keep local-only if possible
```

Object storage public URLs must match the address clients can reach:

```env
OPEN_CHAT_RELAY_S3_PUBLIC_ENDPOINT_URL=https://files.example.com
```

For local Docker testing, the default remains:

```env
OPEN_CHAT_RELAY_S3_PUBLIC_ENDPOINT_URL=http://localhost:9000
```

## Readiness

Use `/health` for a lightweight liveness check and `/ready` for dependency
readiness.

```text
GET /health
GET /ready
```

`/ready` checks:

- database connectivity
- Redis connectivity

The Docker healthcheck uses `/ready`, so a healthy API container means the API
process is running and its core dependencies are reachable.

## Smoke Tests

The realtime smoke checks use the Python `websockets` package. On a deployment
server, create a small smoke-test virtual environment instead of installing
packages into the system Python:

```bash
python3 -m venv .smoke-venv
.smoke-venv/bin/python -m pip install -r scripts/requirements-smoke.txt
```

After the stack is running, first run the deployment check:

```bash
.smoke-venv/bin/python scripts/check_deployment.py
```

Optional targets can be set when ports or hosts differ:

```bash
OPEN_CHAT_RELAY_DEPLOY_API_URL=http://SERVER_IP:18000 \
OPEN_CHAT_RELAY_DEPLOY_CONSOLE_URL=http://SERVER_IP:15173 \
OPEN_CHAT_RELAY_DEPLOY_GATEWAY_URL=http://127.0.0.1:18081 \
.smoke-venv/bin/python scripts/check_deployment.py
```

Then run the functional smoke tests:

```bash
.smoke-venv/bin/python scripts/smoke_api.py
.smoke-venv/bin/python scripts/smoke_realtime.py
.smoke-venv/bin/python scripts/smoke_presence.py
.smoke-venv/bin/python scripts/smoke_typing.py
```

The first command verifies the core HTTP, auth, room, attachment, and message
flow. The second verifies REST-created messages flowing through outbox, Redis,
and WebSocket fanout. The third verifies Redis-backed presence state across the
WebSocket and HTTP API boundary. The fourth verifies Redis-backed typing state.

For deployment rehearsal, `smoke_all.py` runs the deployment check and the
functional smoke suite in the expected order:

```bash
.smoke-venv/bin/python scripts/smoke_all.py
```

When host ports differ, pass the externally reachable URLs directly:

```bash
.smoke-venv/bin/python scripts/smoke_all.py \
  --api-url http://SERVER_IP:18000 \
  --console-url http://SERVER_IP:15173
```

If the console is not deployed on that server, pass an empty console URL:

```bash
.smoke-venv/bin/python scripts/smoke_all.py --console-url ""
```

## WebTransport Deployment Position

WebTransport is the primary innovation path for OpenChatRelay. The gateway now
has an optional HTTP/3 runtime backed by `@fails-components/webtransport`
and libquiche. Keep it disabled until you provide certificates and expose UDP:

```env
OPEN_CHAT_RELAY_WEBTRANSPORT_ENABLED=false
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_RUNTIME_ENABLED=false
```

To enable the runtime:

```env
OPEN_CHAT_RELAY_WEBTRANSPORT_ENABLED=true
OPEN_CHAT_RELAY_WEBTRANSPORT_URL=https://chat.example.com:8081/v1/wt
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_RUNTIME_ENABLED=true
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_CERT_PATH=/certs/webtransport.crt
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_KEY_PATH=/certs/webtransport.key
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_SECRET=replace-with-random-secret
OPEN_CHAT_RELAY_WEBTRANSPORT_CERTS_DIR=./local/certs
```

The gateway container exposes both TCP and UDP on the configured gateway host
port. HTTP/3/WebTransport needs UDP to be reachable from clients. Mount the
certificate and key paths into the gateway container with a Compose override or
your orchestrator's secret mount mechanism.

For local Docker testing, generate a short-lived certificate:

```bash
python3 scripts/generate_webtransport_cert.py --host 127.0.0.1
```

The generated files are written to `local/certs`, which is ignored by git and
mounted into the gateway container by the default Compose file.

For production, mount a real certificate and private key at:

```text
/certs/webtransport.crt
/certs/webtransport.key
```

The certificate must be valid for the host in `OPEN_CHAT_RELAY_WEBTRANSPORT_URL`.
The gateway production startup check refuses to boot with the default internal
token, default WebTransport secret, or missing runtime certificate paths.

The gateway can still be run with the optional Compose profile to validate the
internal session and stream relay path:

```bash
docker compose --profile webtransport up -d webtransport-gateway
python3 scripts/smoke_webtransport_gateway.py
```

When the runtime is disabled, the gateway reports `webtransport_runtime:
pending`. When it is enabled and the API probe sees compatible frame protocol
metadata, `/v1/capabilities` can advertise WebTransport as available.

To enable and validate the local Docker runtime end to end:

```bash
python3 scripts/generate_webtransport_cert.py --host 127.0.0.1
OPEN_CHAT_RELAY_WEBTRANSPORT_ENABLED=true \
OPEN_CHAT_RELAY_WEBTRANSPORT_URL=https://127.0.0.1:8081/v1/wt \
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_RUNTIME_ENABLED=true \
docker compose --profile webtransport up -d --build api webtransport-gateway
.smoke-venv/bin/python scripts/smoke_all.py \
  --webtransport \
  --gateway-url http://127.0.0.1:8081 \
  --runtime-url https://127.0.0.1:8081/v1/wt
```

For a local end-to-end HTTP/3 runtime check against a running API:

```bash
cd gateways/webtransport
npm run smoke:runtime
```

This starts a temporary HTTP/3 WebTransport server with a short-lived local
certificate, connects with the Node WebTransport client, sends a command over a
bidirectional stream, and verifies the returned ack/event frames.

To target an already running Docker gateway instead of the temporary runtime:

```bash
OPEN_CHAT_RELAY_RUNTIME_SMOKE_URL=https://127.0.0.1:8081/v1/wt npm run smoke:runtime
```

If the deployment host does not have Node.js/npm installed, run the runtime
smoke with a temporary Node container from the repository root:

```bash
docker run --rm --network host \
  -v "$PWD/gateways/webtransport:/work" \
  -v "$PWD/local/certs:/certs:ro" \
  -w /work node:25-trixie-slim \
  sh -lc 'npm ci && OPEN_CHAT_RELAY_RUNTIME_SMOKE_API_URL=http://127.0.0.1:18000 OPEN_CHAT_RELAY_RUNTIME_SMOKE_URL=https://wt.chat.example.com:18081/v1/wt OPEN_CHAT_RELAY_RUNTIME_SMOKE_CERT_PATH=/certs/webtransport.crt npm run smoke:runtime'
```

## Docker Production Runbook

1. Prepare `.env`.

```bash
cp .env.production.example .env
python3 scripts/generate_deployment_secrets.py
```

2. Put the generated values into `.env`, then edit domains, CORS origins,
   public S3 URL, and host ports.

3. Prepare WebTransport certificates.

```bash
mkdir -p local/certs
# Copy your production certificate and key to:
# local/certs/webtransport.crt
# local/certs/webtransport.key
```

4. Build and start the stack.

```bash
docker compose --profile webtransport up -d --build
```

5. Check container health.

```bash
docker compose ps
```

6. Run the deployment smoke suite with your public or server-local URLs.

```bash
.smoke-venv/bin/python scripts/smoke_all.py \
  --webtransport \
  --api-url http://SERVER_IP:18000 \
  --console-url http://SERVER_IP:15173 \
  --gateway-url http://127.0.0.1:18081 \
  --runtime-url https://CHAT_HOST:18081/v1/wt
```

7. For repeat deploys after code changes.

```bash
docker compose --profile webtransport up -d --build api outbox-worker console webtransport-gateway
.smoke-venv/bin/python scripts/smoke_all.py --webtransport --gateway-url http://127.0.0.1:18081
```

## Demo Clients

The shared chat demo can be deployed as an optional web client:

```bash
OPEN_CHAT_RELAY_DEMO_API_BASE_URL=https://api.chat.example.com \
docker compose --profile demo up -d --build chat-demo
```

Expose it through a reverse proxy, for example:

```caddyfile
app.chat.example.com {
	reverse_proxy 127.0.0.1:15174
}
```

The Windows desktop demo uses the same React UI through Electron:

```bash
cd apps/chat-demo
npm install
VITE_OPEN_CHAT_RELAY_API_BASE_URL=https://api.chat.example.com npm run build:web
npm run package:windows
```

The generated Windows installer is written under `apps/chat-demo/release`.
