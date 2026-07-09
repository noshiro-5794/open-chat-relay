import { createServer } from "node:http";
import assert from "node:assert/strict";
import test from "node:test";

import {
  GatewaySessionRegistry,
  authenticateAccessToken,
  createGatewayServer,
  handleGatewayCommandStream,
  relayCommand,
  startWebTransportRuntime,
  validateGatewayStartupSettings,
} from "../src/server.js";

test("gateway health reports control-plane status", async () => {
  const server = await listen(createGatewayServer());
  try {
    const response = await fetch(new URL("/health", server.baseUrl));
    const body = await response.json();

    assert.equal(response.status, 200);
    assert.equal(body.service, "openchatrelay-webtransport-gateway");
    assert.equal(body.webtransport_runtime, "pending");
    assert.deepEqual(body.frame_protocol, {
      version: "ocr.realtime.frame.v1",
      encoding: "jsonl",
      content_type: "application/x-ndjson",
      delimiter: "\n",
      max_frame_bytes: 1048576,
    });
    assert.equal(body.active_sessions, 0);
  } finally {
    await close(server.instance);
  }
});

test("gateway readiness requires an internal token", async () => {
  const server = await listen(createGatewayServer({ gatewayInternalToken: null }));
  try {
    const response = await fetch(new URL("/ready", server.baseUrl));
    const body = await response.json();

    assert.equal(response.status, 503);
    assert.equal(body.status, "not_ready");
  } finally {
    await close(server.instance);
  }
});

test("webtransport runtime is disabled unless explicitly enabled", async () => {
  const runtime = await startWebTransportRuntime({
    config: { webtransportRuntimeEnabled: false },
    sessions: new GatewaySessionRegistry({ ttlSeconds: 3600 }),
  });

  assert.equal(runtime, null);
});

test("webtransport runtime requires certificate paths when enabled", async () => {
  await assert.rejects(
    () =>
      startWebTransportRuntime({
        config: { webtransportRuntimeEnabled: true },
        sessions: new GatewaySessionRegistry({ ttlSeconds: 3600 }),
      }),
    /WebTransport runtime requires/,
  );
});

test("production gateway rejects default internal token", () => {
  assert.throws(
    () =>
      validateGatewayStartupSettings({
        environment: "production",
        gatewayInternalToken: "change-this-local-gateway-token",
        webtransportRuntimeEnabled: false,
      }),
    /GATEWAY_INTERNAL_TOKEN/,
  );
});

test("production gateway rejects placeholder internal token", () => {
  assert.throws(
    () =>
      validateGatewayStartupSettings({
        environment: "production",
        gatewayInternalToken: "replace-with-generated-gateway-token",
        webtransportRuntimeEnabled: false,
      }),
    /GATEWAY_INTERNAL_TOKEN/,
  );
});

test("production gateway rejects incomplete webtransport runtime settings", () => {
  assert.throws(
    () =>
      validateGatewayStartupSettings({
        environment: "production",
        gatewayInternalToken: "production-gateway-token",
        webtransportRuntimeEnabled: true,
        webtransportCertPath: null,
        webtransportKeyPath: null,
        webtransportSecret: "change-this-local-webtransport-secret",
      }),
    /WEBTRANSPORT_CERT_PATH/,
  );
});

test("production gateway rejects placeholder webtransport secret", () => {
  assert.throws(
    () =>
      validateGatewayStartupSettings({
        environment: "production",
        gatewayInternalToken: "production-gateway-token",
        webtransportRuntimeEnabled: true,
        webtransportCertPath: "/certs/webtransport.crt",
        webtransportKeyPath: "/certs/webtransport.key",
        webtransportSecret: "replace-with-generated-webtransport-secret",
      }),
    /WEBTRANSPORT_SECRET/,
  );
});

test("production gateway accepts hardened webtransport runtime settings", () => {
  assert.doesNotThrow(() =>
    validateGatewayStartupSettings({
      environment: "production",
      gatewayInternalToken: "production-gateway-token",
      webtransportRuntimeEnabled: true,
      webtransportCertPath: "/certs/webtransport.crt",
      webtransportKeyPath: "/certs/webtransport.key",
      webtransportSecret: "production-webtransport-secret",
    }),
  );
});

test("authenticateAccessToken delegates validation to the API", async () => {
  const api = await listen(
    createServer(async (request, response) => {
      assert.equal(request.method, "POST");
      assert.equal(request.url, "/v1/internal/gateway/authenticate");
      assert.equal(request.headers["x-openchatrelay-gateway-token"], "gateway-secret");

      const body = await readJson(request);
      assert.equal(body.access_token, "access-token");

      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          user_id: "00000000-0000-4000-8000-000000000001",
          token_expires_at: "2026-07-09T00:00:00Z",
        }),
      );
    }),
  );

  try {
    const result = await authenticateAccessToken({
      accessToken: "access-token",
      apiBaseUrl: api.baseUrl,
      gatewayInternalToken: "gateway-secret",
    });

    assert.equal(result.user_id, "00000000-0000-4000-8000-000000000001");
  } finally {
    await close(api.instance);
  }
});

test("relayCommand delegates command frames to the API", async () => {
  const api = await listen(
    createServer(async (request, response) => {
      assert.equal(request.method, "POST");
      assert.equal(request.url, "/v1/internal/gateway/commands");
      assert.equal(request.headers["x-openchatrelay-gateway-token"], "gateway-secret");

      const body = await readJson(request);
      assert.equal(body.access_token, "access-token");
      assert.deepEqual(body.command, {
        type: "room.subscribe",
        request_id: "sub-1",
        data: { room_id: "room-id" },
      });

      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ frames: [{ type: "ack", request_id: "sub-1" }] }));
    }),
  );

  try {
    const result = await relayCommand({
      accessToken: "access-token",
      apiBaseUrl: api.baseUrl,
      gatewayInternalToken: "gateway-secret",
      command: {
        type: "room.subscribe",
        request_id: "sub-1",
        data: { room_id: "room-id" },
      },
    });

    assert.deepEqual(result.frames, [{ type: "ack", request_id: "sub-1" }]);
  } finally {
    await close(api.instance);
  }
});

test("gateway command endpoint relays frames", async () => {
  const api = await listen(
    createServer(async (_request, response) => {
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ frames: [{ type: "ack", request_id: "msg-1" }] }));
    }),
  );
  const gateway = await listen(
    createGatewayServer({
      apiBaseUrl: api.baseUrl,
      gatewayInternalToken: "gateway-secret",
    }),
  );

  try {
    const response = await fetch(new URL("/internal/commands", gateway.baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        access_token: "access-token",
        command: { type: "message.send", request_id: "msg-1", data: {} },
      }),
    });
    const body = await response.json();

    assert.equal(response.status, 200);
    assert.deepEqual(body.frames, [{ type: "ack", request_id: "msg-1" }]);
  } finally {
    await close(gateway.instance);
    await close(api.instance);
  }
});

test("gateway session endpoints authenticate once and relay commands by session", async () => {
  const api = await listen(
    createServer(async (request, response) => {
      assert.equal(request.headers["x-openchatrelay-gateway-token"], "gateway-secret");

      if (request.url === "/v1/internal/gateway/authenticate") {
        const body = await readJson(request);
        assert.equal(body.access_token, "access-token");

        response.writeHead(200, { "Content-Type": "application/json" });
        response.end(
          JSON.stringify({
            user_id: "00000000-0000-4000-8000-000000000001",
            token_expires_at: "2027-07-09T00:00:00Z",
          }),
        );
        return;
      }

      if (request.url === "/v1/internal/gateway/commands") {
        const body = await readJson(request);
        assert.equal(body.access_token, "access-token");
        assert.deepEqual(body.command, {
          type: "room.subscribe",
          request_id: "sub-1",
          data: { room_id: "room-id" },
        });

        response.writeHead(200, { "Content-Type": "application/json" });
        response.end(JSON.stringify({ frames: [{ type: "ack", request_id: "sub-1" }] }));
        return;
      }

      response.writeHead(404, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ detail: "Not found." }));
    }),
  );
  const gateway = await listen(
    createGatewayServer({
      apiBaseUrl: api.baseUrl,
      gatewayInternalToken: "gateway-secret",
      sessionTtlSeconds: 3600,
    }),
  );

  try {
    const createResponse = await fetch(new URL("/internal/sessions", gateway.baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: "access-token" }),
    });
    const created = await createResponse.json();

    assert.equal(createResponse.status, 201);
    assert.equal(typeof created.session_id, "string");
    assert.equal(created.user_id, "00000000-0000-4000-8000-000000000001");
    assert.equal(created.token_expires_at, "2027-07-09T00:00:00Z");
    assert.equal(created.access_token, undefined);

    const commandResponse = await fetch(
      new URL(`/internal/sessions/${created.session_id}/commands`, gateway.baseUrl),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          command: {
            type: "room.subscribe",
            request_id: "sub-1",
            data: { room_id: "room-id" },
          },
        }),
      },
    );
    const commandBody = await commandResponse.json();

    assert.equal(commandResponse.status, 200);
    assert.deepEqual(commandBody.frames, [{ type: "ack", request_id: "sub-1" }]);

    const healthResponse = await fetch(new URL("/health", gateway.baseUrl));
    const health = await healthResponse.json();
    assert.equal(health.active_sessions, 1);

    const deleteResponse = await fetch(
      new URL(`/internal/sessions/${created.session_id}`, gateway.baseUrl),
      { method: "DELETE" },
    );
    assert.equal(deleteResponse.status, 204);
  } finally {
    await close(gateway.instance);
    await close(api.instance);
  }
});

test("gateway session stream endpoint relays ndjson command frames", async () => {
  const api = await listen(
    createServer(async (request, response) => {
      assert.equal(request.headers["x-openchatrelay-gateway-token"], "gateway-secret");

      if (request.url === "/v1/internal/gateway/authenticate") {
        response.writeHead(200, { "Content-Type": "application/json" });
        response.end(
          JSON.stringify({
            user_id: "00000000-0000-4000-8000-000000000001",
            token_expires_at: "2027-07-09T00:00:00Z",
          }),
        );
        return;
      }

      if (request.url === "/v1/internal/gateway/commands") {
        const body = await readJson(request);
        assert.equal(body.access_token, "access-token");
        assert.deepEqual(body.command, {
          type: "room.subscribe",
          request_id: "stream-sub-1",
          data: { room_id: "room-id" },
        });

        response.writeHead(200, { "Content-Type": "application/json" });
        response.end(
          JSON.stringify({
            frames: [
              { type: "ack", request_id: "stream-sub-1", status: "ok", event_id: null },
              { type: "message.created", event_id: "event-id" },
            ],
          }),
        );
        return;
      }

      response.writeHead(404, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ detail: "Not found." }));
    }),
  );
  const gateway = await listen(
    createGatewayServer({
      apiBaseUrl: api.baseUrl,
      gatewayInternalToken: "gateway-secret",
      sessionTtlSeconds: 3600,
    }),
  );

  try {
    const createResponse = await fetch(new URL("/internal/sessions", gateway.baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: "access-token" }),
    });
    const created = await createResponse.json();

    const streamResponse = await fetch(
      new URL(`/internal/sessions/${created.session_id}/streams`, gateway.baseUrl),
      {
        method: "POST",
        headers: { "Content-Type": "application/x-ndjson" },
        body: `${JSON.stringify({
          type: "room.subscribe",
          request_id: "stream-sub-1",
          data: { room_id: "room-id" },
        })}\n`,
      },
    );
    const frames = (await streamResponse.text()).trim().split("\n").map((line) => JSON.parse(line));

    assert.equal(streamResponse.status, 200);
    assert.equal(streamResponse.headers.get("content-type"), "application/x-ndjson");
    assert.deepEqual(frames, [
      { type: "ack", request_id: "stream-sub-1", status: "ok", event_id: null },
      { type: "message.created", event_id: "event-id" },
    ]);
  } finally {
    await close(gateway.instance);
    await close(api.instance);
  }
});

test("gateway session registry expires sessions by token or ttl", () => {
  let now = new Date("2026-07-09T00:00:00.000Z");
  const sessions = new GatewaySessionRegistry({
    ttlSeconds: 60,
    now: () => now,
  });

  const session = sessions.create({
    accessToken: "access-token",
    userId: "user-id",
    tokenExpiresAt: "2026-07-09T00:10:00.000Z",
  });

  assert.equal(session.expiresAt, "2026-07-09T00:01:00.000Z");
  assert.equal(sessions.size, 1);

  now = new Date("2026-07-09T00:01:00.000Z");

  assert.equal(sessions.get(session.id), null);
  assert.equal(sessions.size, 0);
});

test("gateway command stream reassembles split command frames", async () => {
  const api = await listen(
    createServer(async (request, response) => {
      assert.equal(request.url, "/v1/internal/gateway/commands");
      assert.equal(request.headers["x-openchatrelay-gateway-token"], "gateway-secret");

      const body = await readJson(request);
      assert.equal(body.access_token, "access-token");
      assert.deepEqual(body.command, {
        type: "message.send",
        request_id: "msg-1",
        data: { room_id: "room-id", content: "hello" },
      });

      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          frames: [
            { type: "ack", request_id: "msg-1", status: "ok", event_id: "event-id" },
            { type: "message.created", event_id: "event-id" },
          ],
        }),
      );
    }),
  );
  const sessions = new GatewaySessionRegistry({ ttlSeconds: 3600 });
  const session = sessions.create({
    accessToken: "access-token",
    userId: "user-id",
    tokenExpiresAt: "2027-07-09T00:00:00Z",
  });
  const output = [];

  try {
    await handleGatewayCommandStream({
      sessionId: session.id,
      readable: readableFromStrings([
        '{"type":"message.send","request_id":"msg-1",',
        `"data":${JSON.stringify({
          room_id: "room-id",
          content: "hello",
        })}}\n`,
      ]),
      writable: writableToStrings(output),
      sessions,
      apiBaseUrl: api.baseUrl,
      gatewayInternalToken: "gateway-secret",
    });

    const frames = output.join("").trim().split("\n").map((line) => JSON.parse(line));
    assert.deepEqual(frames, [
      { type: "ack", request_id: "msg-1", status: "ok", event_id: "event-id" },
      { type: "message.created", event_id: "event-id" },
    ]);
  } finally {
    await close(api.instance);
  }
});

test("gateway command stream writes protocol error for invalid command frames", async () => {
  const sessions = new GatewaySessionRegistry({ ttlSeconds: 3600 });
  const session = sessions.create({
    accessToken: "access-token",
    userId: "user-id",
    tokenExpiresAt: "2027-07-09T00:00:00Z",
  });
  const output = [];

  await handleGatewayCommandStream({
    sessionId: session.id,
    readable: readableFromStrings(["not-json\n"]),
    writable: writableToStrings(output),
    sessions,
    apiBaseUrl: "http://127.0.0.1:1",
    gatewayInternalToken: "gateway-secret",
  });

  const frame = JSON.parse(output.join("").trim());
  assert.equal(frame.type, "error");
  assert.equal(frame.request_id, null);
  assert.equal(frame.code, "invalid_frame");
});

test("gateway command stream rejects oversized command frames", async () => {
  const sessions = new GatewaySessionRegistry({ ttlSeconds: 3600 });
  const session = sessions.create({
    accessToken: "access-token",
    userId: "user-id",
    tokenExpiresAt: "2027-07-09T00:00:00Z",
  });
  const output = [];

  await handleGatewayCommandStream({
    sessionId: session.id,
    readable: readableFromStrings([`${JSON.stringify({ type: "message.send" })}\n`]),
    writable: writableToStrings(output),
    sessions,
    apiBaseUrl: "http://127.0.0.1:1",
    gatewayInternalToken: "gateway-secret",
    maxFrameBytes: 8,
  });

  assert.deepEqual(JSON.parse(output.join("").trim()), {
    type: "error",
    request_id: null,
    code: "frame_too_large",
    message: "Command frame exceeds 8 bytes.",
  });
});

test("gateway command stream relays newline-delimited command frames", async () => {
  const api = await listen(
    createServer(async (request, response) => {
      assert.equal(request.url, "/v1/internal/gateway/commands");
      assert.equal(request.headers["x-openchatrelay-gateway-token"], "gateway-secret");

      const body = await readJson(request);
      assert.equal(body.access_token, "access-token");
      assert.deepEqual(body.command, {
        type: "message.send",
        request_id: "msg-1",
        data: { room_id: "room-id", content: "hello" },
      });

      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          frames: [
            { type: "ack", request_id: "msg-1", status: "ok", event_id: "event-id" },
            { type: "message.created", event_id: "event-id" },
          ],
        }),
      );
    }),
  );
  const sessions = new GatewaySessionRegistry({ ttlSeconds: 3600 });
  const session = sessions.create({
    accessToken: "access-token",
    userId: "user-id",
    tokenExpiresAt: "2027-07-09T00:00:00Z",
  });
  const output = [];

  try {
    await handleGatewayCommandStream({
      sessionId: session.id,
      readable: readableFromStrings([
        `${JSON.stringify({
          type: "message.send",
          request_id: "msg-1",
          data: { room_id: "room-id", content: "hello" },
        })}\n`,
      ]),
      writable: writableToStrings(output),
      sessions,
      apiBaseUrl: api.baseUrl,
      gatewayInternalToken: "gateway-secret",
    });

    const frames = output.join("").trim().split("\n").map((line) => JSON.parse(line));
    assert.deepEqual(frames, [
      { type: "ack", request_id: "msg-1", status: "ok", event_id: "event-id" },
      { type: "message.created", event_id: "event-id" },
    ]);
  } finally {
    await close(api.instance);
  }
});

test("gateway command stream writes protocol error for missing session", async () => {
  const output = [];

  await handleGatewayCommandStream({
    sessionId: "missing-session",
    readable: readableFromStrings([]),
    writable: writableToStrings(output),
    sessions: new GatewaySessionRegistry({ ttlSeconds: 3600 }),
    apiBaseUrl: "http://127.0.0.1:1",
    gatewayInternalToken: "gateway-secret",
  });

  assert.deepEqual(JSON.parse(output.join("").trim()), {
    type: "error",
    request_id: null,
    code: "gateway_session_not_found",
    message: "Gateway session not found or expired.",
  });
});

test("webtransport endpoint is explicit about pending runtime", async () => {
  const server = await listen(createGatewayServer());
  try {
    const response = await fetch(new URL("/v1/wt", server.baseUrl));
    const body = await response.json();

    assert.equal(response.status, 501);
    assert.equal(body.fallback, "websocket");
  } finally {
    await close(server.instance);
  }
});

function listen(server) {
  return new Promise((resolve) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      resolve({
        instance: server,
        baseUrl: `http://127.0.0.1:${address.port}`,
      });
    });
  });
}

function close(server) {
  return new Promise((resolve, reject) => {
    server.close((error) => {
      if (error) {
        reject(error);
        return;
      }
      resolve();
    });
  });
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) {
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

function readableFromStrings(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(new TextEncoder().encode(chunk));
      }
      controller.close();
    },
  });
}

function writableToStrings(output) {
  return new WritableStream({
    write(chunk) {
      output.push(new TextDecoder().decode(chunk));
    },
  });
}
