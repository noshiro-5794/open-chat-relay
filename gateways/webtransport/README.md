# WebTransport Gateway

This directory contains the first deployable WebTransport gateway boundary.
The service includes an HTTP control plane, a reusable session layer, and an
optional HTTP/3 WebTransport runtime backed by `@fails-components/webtransport`
and libquiche. It can run, report health, check API readiness, delegate user
access-token validation to the API, create gateway sessions, and relay command
frames by session id or WebTransport bidirectional streams.

The gateway must stay behind the same internal command/event protocol used by
the WebSocket implementation. It should not duplicate business logic from the
API service.

Initial responsibilities:

- authenticate sessions
- expose reliable command streams
- expose server event streams
- expose datagram signal lanes
- map protocol frames to OpenChatRelay command and event envelopes
- fall back cleanly through the SDK when WebTransport is unavailable

## Local commands

```bash
npm run check
npm test
npm start
```

## Endpoints

- `GET /health`: process health.
- `GET /ready`: checks gateway internal token configuration and API readiness,
  and returns the frame protocol metadata used by API capability probes.
- `POST /internal/authenticate`: delegates access-token validation to
  `/v1/internal/gateway/authenticate` on the API service.
- `POST /internal/commands`: delegates realtime command frames to
  `/v1/internal/gateway/commands` on the API service.
- `POST /internal/sessions`: authenticates an access token once and creates a
  short-lived gateway session.
- `POST /internal/sessions/{session_id}/commands`: relays command frames using
  the stored session credential.
- `POST /internal/sessions/{session_id}/streams`: internal NDJSON stream
  endpoint that exercises the same stream adapter intended for the future
  WebTransport runtime.
- `DELETE /internal/sessions/{session_id}`: closes a gateway session.
- `GET /v1/wt`: HTTP control-plane placeholder. Real browser WebTransport
  sessions use the same path over HTTP/3 when the runtime is enabled.

The session endpoints are intentionally internal control-plane endpoints. The
HTTP/3/WebTransport runtime calls the same session registry after the browser
session is established, rather than duplicating authentication or business
logic.
The advertised frame protocol includes `max_frame_bytes`; command stream
handlers enforce that limit and return a `frame_too_large` protocol error for
oversized frames.

The gateway also exposes an internal `handleGatewayCommandStream` runtime
adapter in code. It consumes newline-delimited JSON command frames from a
`ReadableStream`, relays them through the API, and writes newline-delimited
ack/event/error frames to a `WritableStream`. The HTTP/3 runtime plugs incoming
bidirectional streams into this adapter.

## Docker Compose

The gateway is behind the optional `webtransport` profile:

```bash
docker compose --profile webtransport up -d --build webtransport-gateway
```

By default the HTTP/3 runtime is disabled. To enable it, provide certificate and
key files and expose UDP for the gateway host port:

```env
OPEN_CHAT_RELAY_WEBTRANSPORT_ENABLED=true
OPEN_CHAT_RELAY_WEBTRANSPORT_URL=https://localhost:8081/v1/wt
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_RUNTIME_ENABLED=true
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_CERT_PATH=/certs/webtransport.crt
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_KEY_PATH=/certs/webtransport.key
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_SECRET=replace-with-random-secret
```

For local Docker testing, generate a development certificate and start the API
plus gateway profile with the runtime enabled:

```bash
python3 scripts/generate_webtransport_cert.py --host 127.0.0.1
OPEN_CHAT_RELAY_WEBTRANSPORT_ENABLED=true \
OPEN_CHAT_RELAY_WEBTRANSPORT_URL=https://127.0.0.1:8081/v1/wt \
OPEN_CHAT_RELAY_GATEWAY_WEBTRANSPORT_RUNTIME_ENABLED=true \
docker compose --profile webtransport up -d --build api webtransport-gateway
```

Then validate both the HTTP control plane and the HTTP/3 WebTransport runtime:

```bash
python3 scripts/smoke_all.py \
  --webtransport \
  --gateway-url http://127.0.0.1:8081 \
  --runtime-url https://127.0.0.1:8081/v1/wt
```

Inside this package, the runtime-only smoke can target either a temporary local
runtime or the Docker gateway:

```bash
npm run smoke:runtime
OPEN_CHAT_RELAY_RUNTIME_SMOKE_URL=https://127.0.0.1:8081/v1/wt npm run smoke:runtime
```
