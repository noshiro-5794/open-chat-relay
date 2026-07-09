# OpenChatRelay

Self-hosted adaptive realtime communication backend for apps, websites, bots,
agent systems, and internal tools.

OpenChatRelay is being built as a communication-first backend, not a chat UI.
Its long-term focus is durable messaging, ephemeral realtime signals, adaptive
transport negotiation, and WebTransport as a first-class communication lane.

## Current Status

Early product build. The repository currently contains the API service and the
core backend features for a self-hosted communication tool:

- FastAPI API service with uv workspace setup
- Health, readiness, and transport capability endpoints
- PostgreSQL, Redis, and MinIO Docker Compose services
- Alembic migrations that run automatically in the API container by default
- JWT auth with access tokens, rotating refresh-token sessions, and session revocation
- Workspaces, workspace members, rooms, and room members
- Workspace member role updates and removal with last-owner protection
- Room member role updates and removal with room-owner protection
- Durable messages, replies, reactions, read states, and room event streams
- WebSocket realtime commands for messages, presence, and typing signals
- SSE room event streaming
- Attachments with S3-compatible presigned uploads
- Attachment upload confirmation with object storage metadata verification
- Apps, bot actors, API keys, and incoming webhooks
- Workspace audit logs for administrative actions
- Event outbox records for durable events
- Outbox publisher worker with Redis fanout
- API Redis subscriber for multi-instance WebSocket fanout
- Redis-backed HTTP rate limiting for Docker deployments
- Redis-backed presence state for multi-instance online/status queries
- Redis-backed typing state and Redis signal bus for multi-instance ephemeral signals
- Transport negotiation contract for WebTransport -> WebSocket -> SSE fallback
- WebTransport gateway with optional HTTP/3 and QUIC runtime
- TypeScript SDK with server-driven WebTransport/WebSocket/SSE fallback
- React admin console for status, transport, config, users, and audit views
- Shared React chat demo for web and Windows desktop shells

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

The API container runs `alembic upgrade head` before starting by default. Set
`OPEN_CHAT_RELAY_RUN_MIGRATIONS=false` if migrations are handled separately.
The Compose stack also runs a one-shot MinIO initializer that creates the
configured S3 bucket before the API starts.

For production deployments, set `OPEN_CHAT_RELAY_ENVIRONMENT=production`, use a
unique `OPEN_CHAT_RELAY_JWT_SECRET_KEY`, keep `OPEN_CHAT_RELAY_DEBUG=false`,
and configure explicit CORS origins. API docs are disabled by default in
production unless `OPEN_CHAT_RELAY_DOCS_ENABLED=true` is set.

HTTP rate limiting is enabled by default with separate buckets for general API,
auth, incoming webhooks, and app API traffic. Docker Compose uses Redis-backed
rate limiting so multiple API instances can share the same buckets.

Deployment notes:

```text
docs/deployment.md
```

API docs:

```text
http://localhost:8000/docs
```

Health check:

```text
http://localhost:8000/health
```

Capabilities:

```text
http://localhost:8000/v1/capabilities
```

Run local Docker smoke tests after the stack is healthy:

```bash
python3 scripts/smoke_all.py
```

Run the WebTransport gateway and HTTP/3 runtime smoke checks after enabling the
gateway profile:

```bash
python3 scripts/smoke_all.py --webtransport --gateway-url http://127.0.0.1:8081
```

## Development

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload
```

Run tests:

```bash
uv run pytest
```

Run migrations locally:

```bash
cd apps/api
uv run alembic upgrade head
```

## Architecture Direction

```text
Clients
  -> SDK / adaptive transport negotiation
  -> REST / WebSocket / WebTransport / SSE / Webhook gateways
  -> Application Core
  -> PostgreSQL / Redis / Event Outbox
```

The WebTransport gateway is intentionally separated as a gateway boundary so it
can evolve with HTTP/3 and QUIC tooling without forcing business logic into a
specific protocol server.
The current gateway includes an optional HTTP/3 runtime and a frame protocol
compatible with the SDK fallback chain.

The TypeScript SDK lives in:

```text
packages/sdk-js
```

The web and Windows chat demo lives in:

```text
apps/chat-demo
```
