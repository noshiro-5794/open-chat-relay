# OpenChatRelay TypeScript SDK

TypeScript client SDK for browser, Electron, and desktop shells that embed a web
runtime. It is the first client-facing layer of the OpenChatRelay communication
kernel.

The SDK reads `/v1/capabilities` and follows the server-provided transport
negotiation order:

```text
WebTransport -> WebSocket -> SSE
```

Current status:

- WebSocket transport: usable for bidirectional realtime commands.
- SSE transport: receive-only fallback.
- WebTransport transport: experimental bidirectional command streams using
  newline-delimited JSON frames. Browser runtime support and the deployed
  gateway still decide whether it is selected.
- High-level realtime methods: room subscribe/unsubscribe, message send,
  presence update, and typing update.
- Request/response correlation: commands resolve on `ack` and reject on
  protocol `error`.

Example:

```ts
import { OpenChatRelayClient } from "@openchatrelay/sdk";

const client = new OpenChatRelayClient("http://localhost:8000");

client.onEvent((event) => {
  console.log("event", event);
});

const connection = await client.connect({ token: accessToken });
console.log("connected over", connection.transport);
console.log("attempted", connection.attempted);
console.log("skipped", connection.skipped);

await client.subscribeRoom(roomId);
await client.updatePresence(roomId, "online");
await client.updateTyping(roomId, "started");
await client.sendMessage(roomId, "hello from the shared communication kernel");
await client.updateTyping(roomId, "stopped");

const notifications = await client.listNotifications({
  token: accessToken,
  unreadOnly: true,
});
const unread = await client.unreadNotificationCount(accessToken);

if (notifications[0]) {
  await client.markNotificationRead(accessToken, notifications[0].id);
}
```

Low-level commands remain available for advanced integrations:

```ts
await client.request({
  type: "room.subscribe",
  data: { room_id: roomId, last_event_seq: 42 },
});

client.send({
  type: "typing.update",
  data: { room_id: roomId, status: "started" },
});
```

Fallback behavior is server-driven. If WebTransport is unavailable or cannot
connect, the SDK tries WebSocket, then SSE for receive-only event streams.
`connect()` returns transport diagnostics so apps can surface why a session
fell back, for example an unhealthy WebTransport gateway or a runtime without
WebTransport support.

The SDK-side WebTransport frame codec is ready for command/response streams.
The repository still needs the real HTTP/3 gateway runtime before browsers can
use WebTransport end to end in production.
The frame codec is advertised by `/v1/capabilities` as
`ocr.realtime.frame.v1` with `application/x-ndjson` JSON Lines frames.

For local WebTransport testing with self-signed certificates, pass native
WebTransport options through the SDK:

```ts
const client = new OpenChatRelayClient("http://localhost:8000", {
  webTransportOptions: {
    serverCertificateHashes: [
      {
        algorithm: "sha-256",
        value: certificateHashBuffer,
      },
    ],
  },
});
```
